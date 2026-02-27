"""
Settings API router
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user_required, require_permissions
from src.infra.settings.service import SettingsService, get_settings_service
from src.kernel.schemas.setting import (
    SettingItem,
    SettingResetResponse,
    SettingsResponse,
    SettingUpdate,
    SettingUpdateResponse,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    user: TokenPayload = Depends(get_current_user_required),
    service: SettingsService = Depends(get_settings_service),
):
    """Get settings (filtered by permission)"""
    # Check if user has settings:manage permission
    has_admin = "settings:manage" in (user.permissions or [])
    settings = await service.get_all(admin_mode=has_admin)
    return SettingsResponse(settings=settings)


@router.get("/{key}", response_model=SettingItem)
async def get_setting(
    key: str,
    _: TokenPayload = Depends(get_current_user_required),
    service: SettingsService = Depends(get_settings_service),
):
    """Get single setting by key"""
    setting = await service._storage.get(key)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@router.put("/{key}", response_model=SettingUpdateResponse)
async def update_setting(
    key: str,
    data: SettingUpdate,
    user: TokenPayload = Depends(require_permissions("settings:manage")),
    service: SettingsService = Depends(get_settings_service),
):
    """Update a setting (requires settings:manage permission)"""
    try:
        setting = await service.set(key, data.value, user.sub)
        if not setting:
            raise HTTPException(status_code=404, detail="Setting not found")

        requires_restart = SettingsService.requires_restart(key)

        return SettingUpdateResponse(
            setting=setting,
            message=(
                "Setting updated. Server restart required to take effect."
                if requires_restart
                else "Setting updated successfully."
            ),
            requires_restart=requires_restart,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/init", response_model=SettingResetResponse)
async def init_settings_from_env(
    _: TokenPayload = Depends(require_permissions("settings:manage")),
    service: SettingsService = Depends(get_settings_service),
):
    """Import settings from .env to database (only unset values)"""
    count = await service.init_from_env()
    return SettingResetResponse(
        message=f"Imported {count} settings from environment",
        reset_count=count,
    )


@router.post("/reset", response_model=SettingResetResponse)
async def reset_all_settings(
    _: TokenPayload = Depends(require_permissions("settings:manage")),
    service: SettingsService = Depends(get_settings_service),
):
    """Reset all settings to default values"""
    count = await service.reset()
    return SettingResetResponse(
        message="All settings reset to defaults",
        reset_count=count,
    )


@router.post("/reset/{key}", response_model=SettingResetResponse)
async def reset_setting(
    key: str,
    _: TokenPayload = Depends(require_permissions("settings:manage")),
    service: SettingsService = Depends(get_settings_service),
):
    """Reset single setting to default value"""
    count = await service.reset(key)
    if count == 0:
        raise HTTPException(status_code=404, detail="Setting not found")
    return SettingResetResponse(
        message=f"Setting {key} reset to default",
        reset_count=count,
    )

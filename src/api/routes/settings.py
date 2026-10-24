"""
Settings API router
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required, require_permissions
from src.api.server_timing import timed_server_phase
from src.infra.auth.delegation import authorize_role_assignment, require_capability
from src.infra.logging import get_logger
from src.infra.settings.service import SettingsService, get_settings_service
from src.infra.settings.storage import SETTING_DEFINITIONS
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.setting import (
    SettingItem,
    SettingResetResponse,
    SettingsResetRequest,
    SettingsResponse,
    SettingUpdate,
    SettingUpdateResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.settings_navigation import build_settings_navigation

router = APIRouter()
logger = get_logger(__name__)


def setting_write_permission(key: str) -> str:
    definition = SETTING_DEFINITIONS.get(key, {})
    category = definition.get("category")
    if definition.get("is_sensitive") or category in {
        "security",
        "oauth",
        "user",
        "email",
        "captcha",
    }:
        return "settings:security"
    return "settings:manage"


async def authorize_setting_write(user: TokenPayload, key: str, value) -> None:
    require_capability(user, setting_write_permission(key))
    if key in {"JWT_SECRET_KEY", "MCP_ENCRYPTION_SALT"}:
        require_capability(user, "system:admin")
    if key == "DEFAULT_USER_ROLE":
        if not isinstance(value, str) or not value.strip():
            raise AppError(ErrorCode.BAD_REQUEST)
        await authorize_role_assignment(user, [value])


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    user: TokenPayload = Depends(get_current_user_required),
    service: SettingsService = Depends(get_settings_service),
):
    """Get settings (filtered by permission)"""
    # Check if user has settings:manage permission
    has_admin = "settings:read" in (user.permissions or [])
    async with timed_server_phase("settings"):
        settings = await service.get_all(admin_mode=has_admin)
    return SettingsResponse(settings=settings, navigation=build_settings_navigation(settings))


@router.get("/{key}", response_model=SettingItem)
async def get_setting(
    key: str,
    _: TokenPayload = Depends(require_permissions("settings:read")),
    service: SettingsService = Depends(get_settings_service),
):
    """Get single setting by key"""
    setting = await service.get_item(key)
    if not setting:
        raise AppError(ErrorCode.SETTING_NOT_FOUND)
    return setting


@router.put("/{key}", response_model=SettingUpdateResponse)
async def update_setting(
    key: str,
    data: SettingUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    service: SettingsService = Depends(get_settings_service),
):
    """Update a setting (requires settings:manage permission)"""
    await authorize_setting_write(user, key, data.value)
    try:
        setting = await service.set(key, data.value, user.sub)
        if not setting:
            raise AppError(ErrorCode.SETTING_NOT_FOUND)

        requires_restart = SettingsService.requires_restart(key)
        logger.info("Setting updated actor=%s target=%s fields=value", user.sub, key)

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
        raise AppError(ErrorCode.BAD_REQUEST, message=str(e))


@router.post("/init", response_model=SettingResetResponse)
async def init_settings_from_env(
    _: TokenPayload = Depends(
        require_permissions("settings:reset", "settings:security", "system:admin")
    ),
    service: SettingsService = Depends(get_settings_service),
):
    """Import settings from .env to database (only unset values)"""
    count = await service.init_from_env()
    logger.info("Settings imported actor=%s count=%s", _.sub, count)
    return SettingResetResponse(
        message=f"Imported {count} settings from environment",
        reset_count=count,
    )


@router.post("/reset", response_model=SettingResetResponse)
async def reset_all_settings(
    data: SettingsResetRequest,
    _: TokenPayload = Depends(
        require_permissions("settings:reset", "settings:security", "system:admin")
    ),
    service: SettingsService = Depends(get_settings_service),
):
    """Reset all settings only after explicit client confirmation."""
    count = await service.reset()
    logger.warning("All settings reset actor=%s count=%s", _.sub, count)
    return SettingResetResponse(
        message="All settings reset to defaults",
        reset_count=count,
    )


@router.post("/reset/{key}", response_model=SettingResetResponse)
async def reset_setting(
    key: str,
    user: TokenPayload = Depends(require_permissions("settings:reset")),
    service: SettingsService = Depends(get_settings_service),
):
    """Reset single setting to default value"""
    definition = SETTING_DEFINITIONS.get(key, {})
    await authorize_setting_write(user, key, definition.get("default"))
    count = await service.reset(key)
    if count == 0:
        raise AppError(ErrorCode.SETTING_NOT_FOUND)
    logger.info("Setting reset actor=%s target=%s", user.sub, key)
    return SettingResetResponse(
        message=f"Setting {key} reset to default",
        reset_count=count,
    )

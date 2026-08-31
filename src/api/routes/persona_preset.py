"""Persona preset routes."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from src.api.deps import require_permissions
from src.infra.persona_preset.manager import PersonaPresetManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.exceptions import NotFoundError
from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetCreate,
    PersonaPresetListResponse,
    PersonaPresetPreferenceUpdate,
    PersonaPresetSnapshot,
    PersonaPresetUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def _is_admin(user: TokenPayload) -> bool:
    return "persona_preset:admin" in set(user.permissions or [])


def _manager() -> PersonaPresetManager:
    return PersonaPresetManager()


@router.get("/", response_model=PersonaPresetListResponse)
async def list_persona_presets(
    scope: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    favorite: bool | None = None,
    pinned: bool | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    user: TokenPayload = Depends(require_permissions("persona_preset:read")),
):
    """List visible persona presets."""
    presets = await _manager().list_presets(
        user_id=user.sub,
        is_admin=_is_admin(user),
        scope=scope,
        status=status,
        tag=tag,
        q=q,
        favorite=favorite,
        pinned=pinned,
        skip=skip,
        limit=limit,
    )
    total = await _manager().count_presets(
        user_id=user.sub,
        is_admin=_is_admin(user),
        scope=scope,
        status=status,
        tag=tag,
        q=q,
        favorite=favorite,
        pinned=pinned,
        skip=skip,
        limit=limit,
    )
    return PersonaPresetListResponse(
        presets=presets,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=PersonaPreset)
async def create_persona_preset(
    preset_data: PersonaPresetCreate,
    user: TokenPayload = Depends(require_permissions("persona_preset:write")),
):
    """Create a user preset or, for admins, a global preset."""
    return await _manager().create_preset(
        preset_data,
        user_id=user.sub,
        is_admin=_is_admin(user),
    )


@router.post("/batch", response_model=list[PersonaPreset])
async def batch_create_persona_presets(
    items: Annotated[list[PersonaPresetCreate], Body(max_length=500)],
    user: TokenPayload = Depends(require_permissions("persona_preset:write")),
):
    """Batch create persona presets."""
    return await _manager().batch_create_presets(
        items,
        user_id=user.sub,
        is_admin=_is_admin(user),
    )


@router.get("/{preset_id}", response_model=PersonaPreset)
async def get_persona_preset(
    preset_id: str,
    user: TokenPayload = Depends(require_permissions("persona_preset:read")),
):
    """Get a visible persona preset."""
    try:
        return await _manager().get_preset(
            preset_id,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)


@router.put("/{preset_id}", response_model=PersonaPreset)
async def update_persona_preset(
    preset_id: str,
    preset_data: PersonaPresetUpdate,
    user: TokenPayload = Depends(require_permissions("persona_preset:write")),
):
    """Update an editable persona preset."""
    try:
        return await _manager().update_preset(
            preset_id,
            preset_data,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)


@router.delete("/{preset_id}")
async def delete_persona_preset(
    preset_id: str,
    user: TokenPayload = Depends(require_permissions("persona_preset:write")),
):
    """Delete an editable persona preset."""
    try:
        await _manager().delete_preset(
            preset_id,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
        return {"status": "deleted"}
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)


@router.post("/{preset_id}/copy", response_model=PersonaPreset)
async def copy_persona_preset(
    preset_id: str,
    user: TokenPayload = Depends(require_permissions("persona_preset:write")),
):
    """Copy a visible preset into the current user's private presets."""
    try:
        return await _manager().copy_preset(
            preset_id,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)


@router.post("/{preset_id}/use", response_model=PersonaPresetSnapshot)
async def use_persona_preset(
    preset_id: str,
    user: TokenPayload = Depends(require_permissions("persona_preset:read")),
):
    """Resolve a persona preset into a runtime snapshot."""
    try:
        return await _manager().use_preset(
            preset_id,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)


@router.patch("/{preset_id}/preference", response_model=PersonaPreset)
async def update_persona_preset_preference(
    preset_id: str,
    preference: PersonaPresetPreferenceUpdate,
    user: TokenPayload = Depends(require_permissions("persona_preset:read")),
):
    """Update the current user's favorite/pinned state for a visible preset."""
    try:
        return await _manager().update_preference(
            preset_id,
            user_id=user.sub,
            is_admin=_is_admin(user),
            is_favorite=preference.is_favorite,
            is_pinned=preference.is_pinned,
        )
    except NotFoundError:
        raise AppError(ErrorCode.PERSONA_PRESET_NOT_FOUND)

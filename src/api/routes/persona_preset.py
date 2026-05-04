"""Persona preset routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import require_permissions
from src.infra.persona_preset.manager import PersonaPresetManager
from src.kernel.exceptions import AuthorizationError, NotFoundError
from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetCreate,
    PersonaPresetListResponse,
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
    skip: int = 0,
    limit: int = Query(default=100, le=200),
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
    try:
        return await _manager().create_preset(
            preset_data,
            user_id=user.sub,
            is_admin=_is_admin(user),
        )
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))


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
        raise HTTPException(status_code=404, detail="persona_preset_not_found")


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
        raise HTTPException(status_code=404, detail="persona_preset_not_found")
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))


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
        raise HTTPException(status_code=404, detail="persona_preset_not_found")
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))


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
        raise HTTPException(status_code=404, detail="persona_preset_not_found")


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
        raise HTTPException(status_code=404, detail="persona_preset_not_found")

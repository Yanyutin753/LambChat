"""Assistant marketplace and personal library routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required
from src.infra.assistant import (
    AssistantCreate,
    AssistantManager,
    AssistantResponse,
    AssistantSelectRequest,
    AssistantUpdate,
)
from src.infra.session.manager import SessionManager
from src.kernel.schemas.session import SessionUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def _is_admin(user: TokenPayload) -> bool:
    return "admin" in set(user.roles)


@lru_cache
def get_assistant_manager() -> AssistantManager:
    return AssistantManager()


def get_session_manager() -> SessionManager:
    return SessionManager()


async def _require_owned_or_public_admin_assistant(
    assistant_id: str,
    user: TokenPayload,
    manager: AssistantManager,
) -> AssistantResponse:
    assistant = await manager.get_assistant_for_user(
        assistant_id, user.sub, is_admin=_is_admin(user)
    )
    if assistant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    if assistant.scope == "private" and assistant.created_by != user.sub and not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if assistant.scope == "public" and not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return AssistantResponse.model_validate(assistant.model_dump())


@router.get("/", response_model=list[AssistantResponse])
async def list_assistants(
    scope: str = Query("public", pattern="^(public|mine|all)$"),
    search: str | None = Query(None),
    tags: str | None = Query(None),
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> list[AssistantResponse]:
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else None
    items = await manager.list_assistants(user.sub, scope=scope, search=search, tags=tag_list)
    return [AssistantResponse.model_validate(item.model_dump()) for item in items]


@router.get("/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(
    assistant_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> AssistantResponse:
    assistant = await manager.get_assistant_for_user(
        assistant_id, user.sub, is_admin=_is_admin(user)
    )
    if assistant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    return AssistantResponse.model_validate(assistant.model_dump())


@router.post("/", response_model=AssistantResponse, status_code=status.HTTP_201_CREATED)
async def create_assistant(
    data: AssistantCreate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> AssistantResponse:
    assistant = await manager.create_private_assistant(data, user.sub)
    return AssistantResponse.model_validate(assistant.model_dump())


@router.patch("/{assistant_id}", response_model=AssistantResponse)
async def update_assistant(
    assistant_id: str,
    data: AssistantUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> AssistantResponse:
    existing = await _require_owned_or_public_admin_assistant(assistant_id, user, manager)
    updated = await manager.update_assistant_for_user(
        existing.assistant_id,
        user.sub,
        data,
        is_admin=_is_admin(user),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return AssistantResponse.model_validate(updated.model_dump())


@router.delete("/{assistant_id}")
async def delete_assistant(
    assistant_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> dict[str, str]:
    existing = await _require_owned_or_public_admin_assistant(assistant_id, user, manager)
    deleted = await manager.delete_assistant_for_user(
        existing.assistant_id, user.sub, is_admin=_is_admin(user)
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return {"status": "deleted"}


@router.post("/{assistant_id}/clone", response_model=AssistantResponse)
async def clone_assistant(
    assistant_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> AssistantResponse:
    try:
        assistant = await manager.clone_public_assistant(assistant_id, user.sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AssistantResponse.model_validate(assistant.model_dump())


@router.post("/{assistant_id}/select")
async def select_assistant(
    assistant_id: str,
    request: AssistantSelectRequest,
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    try:
        snapshot = await manager.select_assistant_for_session(
            assistant_id, request.session_id, user.sub
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await session_manager.update_session(
        request.session_id,
        SessionUpdate(metadata=snapshot),
    )
    return snapshot

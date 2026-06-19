"""Scheduled task API routes — CRUD, pause/resume, manual trigger, run history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.deps import require_permissions
from src.api.routes.plugin_guard import plugin_unavailable_http_error
from src.infra.scheduler.service import ScheduledTaskService
from src.kernel.schemas.scheduled_task import (
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
    ScheduledTaskStatus,
    ScheduledTaskUpdate,
    TaskRunListResponse,
    TaskSessionListResponse,
    TaskSessionResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.extensions import PluginUnavailableError
from src.kernel.types import Permission

router = APIRouter()


def _get_service(request: Request) -> ScheduledTaskService:
    service = ScheduledTaskService()
    service.plugin_runtime = getattr(request.app.state, "plugin_runtime", None)
    plugin_settings_service = getattr(request.app.state, "plugin_settings_service", None)
    if plugin_settings_service is not None:
        service.plugin_settings_service = plugin_settings_service
    return service


async def _require_owned_task(
    task_id: str,
    user: TokenPayload,
    service: ScheduledTaskService,
) -> ScheduledTask:
    """Load task and verify ownership. Raises 404 if not found or forbidden."""
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.sub:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ── CRUD ────────────────────────────────────────────


@router.post("/", response_model=ScheduledTaskResponse, status_code=201)
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_WRITE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Create a new scheduled task."""
    try:
        task = await service.create_task(body, owner_id=user.sub)
    except PluginUnavailableError as exc:
        raise plugin_unavailable_http_error(None, exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await service.get_task_response(task)


@router.get("/", response_model=ScheduledTaskListResponse)
async def list_scheduled_tasks(
    status: ScheduledTaskStatus | None = None,
    source_session_id: str | None = None,
    created_by: str | None = Query(None, pattern="^(user|agent|api)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_READ.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """List scheduled tasks owned by the current user, with pagination."""
    items, total = await service.list_tasks_paginated(
        owner_id=user.sub,
        status=status,
        source_session_id=source_session_id,
        created_by=created_by,
        skip=skip,
        limit=limit,
    )
    return ScheduledTaskListResponse(items=items, total=total)


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: str,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_READ.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Get details of a single scheduled task."""
    task = await _require_owned_task(task_id, user, service)
    return await service.get_task_response(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: str,
    body: ScheduledTaskUpdate,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_WRITE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Update a scheduled task's configuration."""
    await _require_owned_task(task_id, user, service)
    try:
        updated = await service.update_task(task_id, body)
    except PluginUnavailableError as exc:
        raise plugin_unavailable_http_error(None, exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return await service.get_task_response(updated)


# ── Pause / Resume / Delete ─────────────────────────


@router.post("/{task_id}/pause", response_model=ScheduledTaskResponse)
async def pause_scheduled_task(
    task_id: str,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_WRITE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Pause a scheduled task (removes from scheduler, keeps config)."""
    await _require_owned_task(task_id, user, service)
    updated = await service.pause_task(task_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return await service.get_task_response(updated)


@router.post("/{task_id}/resume", response_model=ScheduledTaskResponse)
async def resume_scheduled_task(
    task_id: str,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_WRITE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Resume a paused scheduled task."""
    await _require_owned_task(task_id, user, service)
    updated = await service.resume_task(task_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return await service.get_task_response(updated)


@router.delete("/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_DELETE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Physically delete a scheduled task."""
    await _require_owned_task(task_id, user, service)
    await service.delete_task(task_id)


# ── Manual trigger ──────────────────────────────────


@router.post("/{task_id}/run", response_model=dict)
async def run_scheduled_task_now(
    task_id: str,
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_WRITE.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """Manually trigger a scheduled task execution."""
    await _require_owned_task(task_id, user, service)
    return await service.run_task_now(task_id)


# ── Run history ─────────────────────────────────────


@router.get("/{task_id}/runs", response_model=TaskRunListResponse)
async def list_task_runs(
    task_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_READ.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """View execution history for a scheduled task."""
    await _require_owned_task(task_id, user, service)
    runs, total = await service.get_task_runs(task_id, limit, offset)
    return TaskRunListResponse(items=runs, total=total)


# ── Task sessions ────────────────────────────────────


@router.get("/{task_id}/sessions", response_model=TaskSessionListResponse)
async def list_task_sessions(
    task_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions(Permission.SCHEDULED_TASK_READ.value)),
    service: ScheduledTaskService = Depends(_get_service),
):
    """List sessions (conversations) created by a scheduled task's executions."""
    await _require_owned_task(task_id, user, service)
    from src.infra.session.storage import SessionStorage

    storage = SessionStorage()
    sessions, total = await storage.list_sessions_for_task(
        scheduled_task_id=task_id,
        user_id=user.sub,
        skip=skip,
        limit=limit,
    )
    items = [
        TaskSessionResponse(
            id=s.id,
            name=s.name,
            agent_id=s.agent_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            is_active=s.is_active,
            metadata=s.metadata,
            unread_count=s.unread_count,
        )
        for s in sessions
    ]
    return TaskSessionListResponse(items=items, total=total)

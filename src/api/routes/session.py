"""
会话路由

所有会话操作都需要认证，用户只能访问自己的会话。
管理员可以访问所有会话。
"""

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.api.deps import get_current_user_required
from src.infra.extensions import get_plugin_settings_service
from src.infra.extensions.scoped_options import (
    plugin_options_with_settings,
    scoped_option_definition,
    scoped_option_manifest,
    scoped_plugin_is_executable,
    validate_scoped_plugin_option_value,
)
from src.infra.folder.storage import get_project_storage
from src.infra.logging import get_logger
from src.infra.session.favorites import is_session_favorite, normalize_session_metadata
from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage
from src.kernel.config import settings
from src.kernel.exceptions import NotFoundError, SessionError
from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS
from src.kernel.extensions.plugin_options import (
    plugin_options_from_metadata,
    with_plugin_option,
)
from src.kernel.extensions.runtime import PluginRuntime
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

# 支持的语言白名单
SUPPORTED_LANGUAGES = frozenset(["en", "zh", "ja", "ko"])
SESSION_EVENT_TYPE_FILTER_LIMIT = 100
SESSION_EVENT_RESPONSE_LIMIT_MAX = 10000
SESSION_RAW_TRACE_RESPONSE_LIMIT_MAX = 20
SESSION_RAW_TRACE_EVENTS_LIMIT_MAX = 200


class MessageCheckpointCreatePayload(BaseModel):
    name: str | None = None


class SessionPluginOptionUpdatePayload(BaseModel):
    value: Any = None


def _parse_event_types_filter(event_types: str | None) -> list[str] | None:
    if not event_types:
        return None
    parsed: list[str] = []
    seen = set()
    for raw_type in event_types.split(","):
        event_type = raw_type.strip()
        if not event_type or event_type in seen:
            continue
        seen.add(event_type)
        parsed.append(event_type)
        if len(parsed) >= SESSION_EVENT_TYPE_FILTER_LIMIT:
            break
    return parsed or None


def _is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试（429、网络错误等）"""
    error_str = str(error).lower()
    retryable_patterns = [
        "429",  # rate limit
        "503",  # service unavailable
        "502",  # bad gateway
        "504",  # gateway timeout
        "timeout",
        "connection",
        "overloaded",
        "网络错误",  # Chinese API proxy network error
        "network error",
    ]
    return any(pattern in error_str for pattern in retryable_patterns)


async def _ainvoke_with_retry(model, prompt: str, max_retries: int | None = None) -> Any:
    """带重试的 LLM 调用"""

    if max_retries is None:
        max_retries = getattr(settings, "LLM_MAX_RETRIES", 3)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await model.ainvoke(prompt)
        except Exception as e:
            last_error = e
            if _is_retryable_error(e) and attempt < max_retries - 1:
                delay = settings.LLM_RETRY_DELAY * (2**attempt)  # 指数退避
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise
    if last_error is None:
        raise RuntimeError("Unexpected state: no error but loop exhausted")
    raise last_error


def verify_session_ownership(session: Session, user: TokenPayload) -> None:
    """验证会话所有权，仅允许会话所有者访问"""
    if session.user_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此会话",
        )


async def _get_favorites_project_id(user_id: str) -> str | None:
    project_storage = get_project_storage()
    favorites_project = await project_storage.get_by_type(user_id, "favorites")
    return favorites_project.id if favorites_project else None


def _normalize_session(
    session: Session,
    favorites_project_id: str | None,
) -> Session:
    return session.model_copy(
        update={
            "metadata": normalize_session_metadata(
                session.metadata,
                favorites_project_id,
            )
        }
    )


def _get_plugin_runtime(request: Request) -> PluginRuntime:
    runtime = getattr(request.app.state, "plugin_runtime", None)
    if isinstance(runtime, PluginRuntime):
        return runtime
    return PluginRuntime(BUILTIN_PLUGIN_MANIFESTS, core_dependencies=("skill_core",))


def _get_plugin_settings_service(request: Request):
    return (
        getattr(request.app.state, "plugin_settings_service", None) or get_plugin_settings_service()
    )


def _session_option_definition(runtime: PluginRuntime, plugin_id: str, key: str):
    try:
        return scoped_option_definition(
            runtime,
            scope="session",
            plugin_id=plugin_id,
            key=key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _plugin_manifest(runtime: PluginRuntime, plugin_id: str):
    try:
        return scoped_option_manifest(runtime, plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _validate_session_plugin_option_value(option, value: Any) -> Any:
    try:
        return validate_scoped_plugin_option_value(option, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _plugin_is_executable(runtime: PluginRuntime, plugin_id: str) -> bool:
    return scoped_plugin_is_executable(runtime, plugin_id)


@router.get("")
async def list_sessions(
    skip: int = Query(0, ge=0, description="跳过的会话数量"),
    limit: int = Query(20, ge=1, le=100, description="返回的会话数量"),
    status: Optional[str] = Query(None, description="状态过滤: active 或 archived"),
    project_id: Optional[str] = Query(None, description="项目过滤: 项目ID 或 'none'(未分类)"),
    search: Optional[str] = Query(None, description="搜索关键词，模糊匹配会话名称"),
    favorites_only: bool = Query(False, description="仅返回已收藏会话"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出会话

    普通用户只能看到自己的会话，管理员可以看到所有会话。

    Args:
        project_id: 可选的项目过滤
                   - 不传: 返回所有会话
                   - "none": 返回未分类的会话
                   - 项目ID: 返回该项目内的会话

    Returns:
        {
            "sessions": [...],
            "total": 总数量,
            "skip": 跳过数量,
            "limit": 请求的限制,
            "has_more": 是否有更多数据
        }
    """
    manager = SessionManager()

    # 确定过滤条件
    is_active = None
    if status == "active":
        is_active = True
    elif status == "archived":
        is_active = False

    # 所有用户只能查看自己的会话
    filter_user_id = user.sub
    favorites_project_id = await _get_favorites_project_id(user.sub)

    sessions, total = await manager.list_sessions(
        user_id=filter_user_id,
        skip=skip,
        limit=limit,
        is_active=is_active,
        project_id=project_id,
        search=search,
        favorites_only=favorites_only,
        favorites_project_id=favorites_project_id,
    )

    return {
        "sessions": sessions,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(sessions)) < total,
    }


@router.post("/mark-all-read")
async def mark_all_sessions_read(
    project_id: Optional[str] = Query(None),
    scheduled_task_id: Optional[str] = Query(None),
    user: TokenPayload = Depends(get_current_user_required),
):
    """批量将会话标记为已读，支持按项目或定时任务过滤。"""
    manager = SessionManager()
    modified_count = await manager.mark_all_read(user.sub, project_id, scheduled_task_id)
    return {"status": "ok", "modified_count": modified_count}


@router.post("", response_model=Session)
async def create_session(
    session_data: SessionCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建会话

    会话自动关联到当前认证用户。
    """
    manager = SessionManager()
    return await manager.create_session(session_data, user_id=user.sub)


@router.get("/{session_id}/plugin-options")
async def get_session_plugin_options(
    session_id: str,
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Return plugin-scoped session options stored on this session."""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    verify_session_ownership(session, user)
    runtime = _get_plugin_runtime(request)
    plugin_options = await plugin_options_with_settings(
        runtime=runtime,
        service=_get_plugin_settings_service(request),
        scope="session",
        subject_id=session_id,
        plugin_options=plugin_options_from_metadata(session.metadata),
    )
    return {
        "session_id": session_id,
        "plugin_options": plugin_options,
        "storage": "session_metadata",
        "source": "session_metadata.plugin_options+plugin_settings",
    }


@router.put("/{session_id}/plugin-options/{plugin_id}/{key}")
async def update_session_plugin_option(
    session_id: str,
    plugin_id: str,
    key: str,
    payload: SessionPluginOptionUpdatePayload,
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Update one manifest-declared plugin session option without enabling the plugin."""
    runtime = _get_plugin_runtime(request)
    option = _session_option_definition(runtime, plugin_id, key)
    manifest = _plugin_manifest(runtime, plugin_id)
    value = _validate_session_plugin_option_value(option, payload.value)
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    verify_session_ownership(session, user)
    try:
        await _get_plugin_settings_service(request).set_setting(
            manifest,
            key=key,
            value=value,
            updated_by=user.sub,
            scope="session",
            subject_id=session_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    metadata = with_plugin_option(
        session.metadata,
        plugin_id=plugin_id,
        key=key,
        value=value,
    )
    metadata_update = {"plugin_options": metadata.get("plugin_options", {})}
    updated_session = await manager.update_session(
        session_id,
        SessionUpdate(metadata=metadata_update),
    )
    if not updated_session:
        raise HTTPException(status_code=500, detail="failed to update plugin session option")
    return {
        "session_id": session_id,
        "plugin_id": plugin_id,
        "key": key,
        "qualified_key": f"{plugin_id}.{key}",
        "value": value,
        "plugin_enabled": _plugin_is_executable(runtime, plugin_id),
        "effective": _plugin_is_executable(runtime, plugin_id),
        "plugin_options": plugin_options_from_metadata(updated_session.metadata),
        "storage": "session_metadata",
        "source": "session_metadata.plugin_options+plugin_settings",
    }


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话

    只能获取自己拥有的会话，管理员可以获取任意会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)
    favorites_project_id = await _get_favorites_project_id(user.sub)
    return _normalize_session(session, favorites_project_id)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除会话

    只能删除自己拥有的会话，管理员可以删除任意会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    success = await manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    # 清理延迟工具发现记录
    try:
        from src.infra.tool.deferred_manager import clear_discovered_tools

        await clear_discovered_tools(session_id)
    except Exception:
        pass

    return {"status": "deleted"}


@router.post("/{session_id}/mark-read")
async def mark_session_read(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """将会话标记为已读（清除未读计数）"""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    await manager.mark_read(session_id)
    return {"status": "ok"}


@router.get("/{session_id}/events")
async def get_session_events(
    session_id: str,
    event_types: Optional[str] = Query(
        None, description="事件类型过滤，逗号分隔，如: message,thinking,tool_use"
    ),
    run_id: Optional[str] = Query(None, description="Run ID 过滤（用于获取特定对话轮次的事件）"),
    exclude_run_id: Optional[str] = Query(
        None, description="排除的 Run ID（用于排除正在运行的 run）"
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=SESSION_EVENT_RESPONSE_LIMIT_MAX,
        description="最大返回事件数，不传则不限制",
    ),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话所有事件

    只能获取自己拥有的会话事件。

    Args:
        session_id: 会话 ID
        event_types: 可选的事件类型过滤（逗号分隔）
        run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
        exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
    """
    from src.infra.session.dual_writer import get_dual_writer

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()

    # 解析事件类型过滤
    types_list = _parse_event_types_filter(event_types)

    # 重要：completed_only=True，确保正在运行的 trace 中的事件不要被返回，而是单独去请求/stream接口，避免重复返回事件，导致前端消息重复显示。
    # 否则刷新页面时，当前 run 的 user:message 事件会丢失，导致消息合并
    events_probe_limit = (limit + 1) if limit is not None else None
    events = await dual_writer.read_session_events(
        session_id,
        types_list,
        run_id=run_id,
        exclude_run_id=exclude_run_id,
        completed_only=True,
        max_events=events_probe_limit,
    )
    events_limited = limit is not None and len(events) > limit
    if events_limited:
        events = events[:limit]

    # 获取 session 的 current_run_id 用于响应
    current_run_id = session.metadata.get("current_run_id") if session.metadata else None

    return {
        "events": events,
        "session_id": session_id,
        "run_id": run_id or current_run_id,
        "events_limited": events_limited,
        "events_limit": limit,
    }


@router.get("/{session_id}/runs")
async def get_session_runs(
    session_id: str,
    limit: int = Query(50, ge=1, le=100, description="最大返回数量"),
    trace_id: Optional[str] = Query(None, description="精确 trace ID 过滤"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的所有 runs（对话轮次）

    每个 run 代表一轮独立的对话。

    Args:
        session_id: 会话 ID
        limit: 最大返回数量
    """
    from src.infra.session.dual_writer import get_dual_writer
    from src.infra.session.trace_storage import get_trace_storage

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()
    trace_storage = get_trace_storage()

    async def build_run_summary(trace: dict[str, Any]) -> dict[str, Any]:
        run_id = trace.get("run_id")
        current_trace_id = trace.get("trace_id")
        user_message = None
        if run_id and current_trace_id:
            event = await trace_storage.get_first_trace_event(
                trace_id=current_trace_id,
                event_types=["user:message"],
            )
            data = event.get("data", {}) if event else {}
            user_message = data.get("content") or data.get("message") or ""
            if user_message and len(user_message) > 20:
                user_message = user_message[:17] + "..."

        return {
            "run_id": run_id,
            "trace_id": trace.get("trace_id"),
            "agent_id": trace.get("agent_id"),
            "started_at": trace.get("started_at"),
            "completed_at": trace.get("completed_at"),
            "status": trace.get("status"),
            "event_count": trace.get("event_count", 0),
            "user_message": user_message,
        }

    if trace_id:
        trace = await dual_writer.get_trace(trace_id)
        traces = [trace] if trace and trace.get("session_id") == session_id else []
        runs = [await build_run_summary(trace) for trace in traces]
    else:
        runs = await trace_storage.list_run_summaries(
            session_id=session_id,
            limit=limit,
            trace_id=trace_id,
        )

    return {
        "session_id": session_id,
        "runs": runs,
        "count": len(runs),
    }


@router.get("/{session_id}/traces")
async def get_session_traces(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的所有 traces（调试用）

    只能获取自己拥有的会话 traces。
    """
    from src.infra.session.dual_writer import get_dual_writer

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    dual_writer = get_dual_writer()
    traces = await dual_writer.list_traces(session_id=session_id, limit=100)

    return {"traces": traces, "session_id": session_id}


@router.get("/{session_id}/raw-traces")
async def get_session_raw_traces(
    session_id: str,
    limit: int = Query(
        20,
        ge=1,
        le=SESSION_RAW_TRACE_RESPONSE_LIMIT_MAX,
        description="最大返回 trace 数",
    ),
    events_limit: int = Query(
        200,
        ge=1,
        le=SESSION_RAW_TRACE_EVENTS_LIMIT_MAX,
        description="每个 trace 最多返回最近事件数",
    ),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取会话的原始 traces 数据（包含最近 events）
    """
    from src.infra.session.trace_storage import get_trace_storage

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    trace_storage = get_trace_storage()

    cursor = (
        trace_storage.collection.find(
            {"session_id": session_id},
            {"_id": 0, "events": {"$slice": -events_limit}},
        )
        .sort("started_at", -1)
        .limit(limit)
    )
    traces = await cursor.to_list(length=limit)

    return {
        "session_id": session_id,
        "traces": traces,
        "count": len(traces),
        "limit": limit,
        "events_limit": events_limit,
    }


@router.patch("/{session_id}/status")
async def update_session_status(
    session_id: str,
    status: str = Query(..., description="新状态: active 或 archived"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新会话状态

    只能更新自己拥有的会话状态。
    """
    if status not in ["active", "archived"]:
        raise HTTPException(status_code=400, detail="状态必须是 active 或 archived")

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    is_active = status == "active"
    updated_session = await manager.update_session(
        session_id,
        SessionUpdate(metadata={"is_active": is_active}),
    )
    if not updated_session:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"status": "updated", "session": updated_session}


@router.post("/{session_id}/clear-messages")
async def clear_session_messages(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    清空会话消息

    只能清空自己拥有的会话消息。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    released_attachments = await manager.clear_session_messages(session_id)
    return {"status": "cleared", "released_attachments": released_attachments}


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新会话信息（如名称）

    只能更新自己拥有的会话。
    """
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    updated_session = await manager.update_session(session_id, session_data)
    if not updated_session:
        raise HTTPException(status_code=500, detail="更新失败")
    favorites_project_id = await _get_favorites_project_id(user.sub)
    updated_session = _normalize_session(updated_session, favorites_project_id)
    return {"status": "updated", "session": updated_session}


@router.post("/{session_id}/messages/{message_id}/fork")
async def fork_session_from_message(
    session_id: str,
    message_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Create a new session forked from a specific message."""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    try:
        return await manager.fork_session_from_message(session_id, message_id, user.sub)
    except NotFoundError as exc:
        detail = "消息不存在" if "message" in str(exc) else "资源不存在"
        logger.warning("Fork 404: session=%s message=%s exc=%s", session_id, message_id, exc)
        raise HTTPException(status_code=404, detail=detail) from exc
    except SessionError as exc:
        logger.error("Fork 500: session=%s message=%s exc=%s", session_id, message_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{session_id}/messages/{message_id}/checkpoints")
async def create_message_checkpoint(
    session_id: str,
    message_id: str,
    payload: MessageCheckpointCreatePayload,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Create a checkpoint anchored on a specific message."""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    try:
        return await manager.create_message_checkpoint(
            session_id,
            message_id,
            user_id=user.sub,
            name=payload.name,
        )
    except NotFoundError as exc:
        detail = "消息不存在" if "message" in str(exc) else "资源不存在"
        raise HTTPException(status_code=404, detail=detail) from exc


@router.post("/{session_id}/checkpoints/{checkpoint_id}/fork")
async def fork_session_from_checkpoint(
    session_id: str,
    checkpoint_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Create a new session forked from a saved checkpoint."""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    try:
        return await manager.fork_session_from_checkpoint(
            session_id,
            checkpoint_id,
            user_id=user.sub,
        )
    except NotFoundError as exc:
        detail = "检查点不存在" if "checkpoint" in str(exc) else "资源不存在"
        logger.warning(
            "Fork checkpoint 404: session=%s checkpoint=%s exc=%s",
            session_id,
            checkpoint_id,
            exc,
        )
        raise HTTPException(status_code=404, detail=detail) from exc
    except SessionError as exc:
        logger.error(
            "Fork checkpoint 500: session=%s checkpoint=%s exc=%s",
            session_id,
            checkpoint_id,
            exc,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{session_id}/favorite")
async def toggle_session_favorite(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Toggle a session's favorite state without changing its project."""

    manager = SessionManager()
    storage = SessionStorage()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    favorites_project_id = await _get_favorites_project_id(user.sub)
    updated_session = await storage.toggle_favorite(
        session_id,
        user.sub,
        favorites_project_id=favorites_project_id,
    )
    if not updated_session:
        raise HTTPException(status_code=500, detail="收藏状态更新失败")

    updated_session = _normalize_session(updated_session, favorites_project_id)
    return {
        "status": "updated",
        "is_favorite": is_session_favorite(
            updated_session.metadata,
            favorites_project_id,
        ),
        "session": updated_session,
    }


@router.post("/{session_id}/generate-title")
async def generate_session_title(
    session_id: str,
    message: str = Query(..., description="用户消息内容，用于生成标题"),
    lang: str = Query("en", description="语言代码: en, zh, ja, ko"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    根据用户消息自动生成标题

    使用 LLM 根据用户消息生成一个简短的会话标题。
    支持通过 settings 自定义模型和提示词。
    """
    from src.infra.llm.client import LLMClient
    from src.infra.llm.models_service import resolve_model_reference

    # 验证语言参数白名单
    if lang not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language code: {lang}, falling back to 'en'")
        lang = "en"

    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)

    if not message or not message.strip():
        return {"title": "新对话", "session_id": session_id}

    title_model_id, title_model = await resolve_model_reference(settings.SESSION_TITLE_MODEL)
    prompt_template = settings.SESSION_TITLE_PROMPT

    # 使用 LLM 生成标题
    try:
        model_kwargs: dict[str, Any] = {
            "model_id": title_model_id,
            "max_retries": settings.LLM_MAX_RETRIES,
        }
        if title_model:
            model_kwargs["model"] = title_model
        model = await LLMClient.get_model(
            **model_kwargs,
        )
        prompt = prompt_template.replace("{lang}", lang).replace("{message}", message[:800])

        response = await _ainvoke_with_retry(model, prompt)
        logger.debug("LLM 生成标题响应: %s", response)

        # 提取标题，兼容新旧格式
        content = response.content
        if isinstance(content, list):
            # 新格式：content 是列表，提取 type 为 'text' 的部分
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    title = str(item.get("text", "")).strip()
                    break
            else:
                title = str(content[0]).strip() if content else ""
        else:
            # 旧格式：content 直接是字符串
            title = str(content).strip()

        title = title.strip('"').strip("'")

        # 限制标题长度
        if len(title) > 30:
            title = title[:27] + "..."

        # 更新 session 名称
        await manager.update_session(session_id, SessionUpdate(name=title))

        return {"title": title, "session_id": session_id}
    except Exception as e:
        # 如果生成失败，使用消息的前几个字作为标题
        fallback_title = message[:20]
        if len(message) > 20:
            fallback_title += "..."
        await manager.update_session(session_id, SessionUpdate(name=fallback_title))
        return {"title": fallback_title, "session_id": session_id, "error": str(e)}


@router.post("/{session_id}/move")
async def move_session(
    session_id: str,
    body: dict,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    移动会话到项目

    将会话移动到指定项目，或设置为未分类。

    Args:
        session_id: 会话ID
        body: {"project_id": "xxx" 或 null}

    Returns:
        {"status": "moved", "session": updated_session}
    """
    manager = SessionManager()
    storage = SessionStorage()

    # Verify session exists and belongs to user
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    verify_session_ownership(session, user)
    favorites_project_id = await _get_favorites_project_id(user.sub)
    was_favorite = is_session_favorite(session.metadata, favorites_project_id)

    # Get project_id from body
    project_id = body.get("project_id")

    # If project_id provided (not null), verify project exists and belongs to user
    if project_id is not None:
        project_storage = get_project_storage()
        project = await project_storage.get_by_id(project_id, user.sub)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

    # Move session
    updated_session = await storage.move_to_project(session_id, user.sub, project_id)
    if not updated_session:
        raise HTTPException(status_code=500, detail="移动失败")

    if was_favorite and not is_session_favorite(
        updated_session.metadata,
        favorites_project_id,
    ):
        updated_session = await storage.update(
            session_id,
            SessionUpdate(metadata={"is_favorite": True}),
        )
        if not updated_session:
            raise HTTPException(status_code=500, detail="移动后收藏状态同步失败")

    # Sync revealed files' project_id
    try:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        revealed_storage = get_revealed_file_storage()
        await revealed_storage.update_project_id_by_session(session_id, project_id)
    except Exception as e:
        logger.warning(f"Failed to sync revealed files project_id: {e}")

    updated_session = _normalize_session(updated_session, favorites_project_id)
    return {"status": "moved", "session": updated_session}

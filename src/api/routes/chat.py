"""
聊天路由

支持后台执行的聊天接口。
每次对话生成独立的 run_id，实现多轮对话隔离。
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.agents.core import resolve_agent_name
from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.auth.utils import _get_language
from src.api.routes.chat_validation import validate_team_agent_request
from src.api.routes.session import verify_session_ownership
from src.infra.async_utils import run_blocking_io
from src.infra.chat.user_message_timestamp import format_user_message_with_timestamp
from src.infra.goal import GoalSpec, coerce_goal_spec
from src.infra.logging import get_logger
from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.session.manager import SessionManager
from src.infra.task.cancellation import _close_agent_safely
from src.infra.task.concurrency import register_executor
from src.infra.task.manager import get_task_manager
from src.infra.task.status import TaskStatus
from src.kernel.config import settings
from src.kernel.exceptions import AuthorizationError, NotFoundError
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

CHAT_SSE_DATA_MAX_BYTES = 256 * 1024


def _model_profile_dict(model: ModelConfig) -> dict | None:
    if not model.profile:
        return None
    return (
        model.profile.model_dump() if hasattr(model.profile, "model_dump") else dict(model.profile)
    )


def _safe_model_config_dict(model: ModelConfig) -> dict:
    return model.model_copy(update={"api_key": None}).model_dump(mode="json")


def _estimated_json_data_bytes(data: object) -> int:
    if data is None or isinstance(data, (bool, int, float)):
        return len(json.dumps(data, default=str).encode("utf-8"))
    if isinstance(data, str):
        return len(data.encode("utf-8")) + 2
    if isinstance(data, dict):
        total = 2
        for index, (key, value) in enumerate(data.items()):
            if index:
                total += 1
            total += len(str(key).encode("utf-8")) + 3
            total += _estimated_json_data_bytes(value)
        return total
    if isinstance(data, (list, tuple)):
        total = 2
        for index, item in enumerate(data):
            if index:
                total += 1
            total += _estimated_json_data_bytes(item)
        return total
    return len(str(data).encode("utf-8")) + 2


def _chat_sse_payload_too_large_event(event_id: object | None) -> str:
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f'event: error\ndata: {{"error":"event_payload_too_large"}}\n{id_line}\n'


def _json_dumps_chat_sse_data_limited(data: object) -> str | None:
    if _estimated_json_data_bytes(data) > CHAT_SSE_DATA_MAX_BYTES:
        return None

    encoder = json.JSONEncoder(ensure_ascii=False, default=str)
    chunks: list[str] = []
    total = 0
    for chunk in encoder.iterencode(data):
        total += len(chunk.encode("utf-8"))
        if total > CHAT_SSE_DATA_MAX_BYTES:
            return None
        chunks.append(chunk)
    return "".join(chunks)


def _format_sse_event(event: dict) -> str:
    event_data = event["data"]
    if isinstance(event_data, dict) and event.get("timestamp"):
        event_data = {**event_data, "_timestamp": event["timestamp"]}
    data_str = _json_dumps_chat_sse_data_limited(event_data)
    if data_str is None:
        return _chat_sse_payload_too_large_event(event.get("id"))
    return f"event: {event['event_type']}\ndata: {data_str}\nid: {event['id']}\n\n"


async def _attach_resolved_model_options(agent_options: dict, model: ModelConfig) -> None:
    """Persist resolved model details in request options to avoid repeated DB lookups."""
    agent_options["model_id"] = model.id
    agent_options["model"] = model.value
    agent_options["_resolved_model_config"] = _safe_model_config_dict(model)
    agent_options["_resolved_supports_vision"] = bool(
        getattr(model.profile, "supports_vision", False)
    )
    agent_options["_resolved_image_url_to_base64"] = bool(
        getattr(model.profile, "image_url_to_base64", False)
    )
    if model.api_key:
        from src.infra.llm.models_service import set_cached_api_key

        set_cached_api_key(model.value, model.api_key)

    fallback_value = None
    if model.fallback_model:
        from src.infra.agent.model_storage import get_model_storage

        try:
            fallback = await get_model_storage().get(model.fallback_model)
            if fallback and fallback.enabled:
                fallback_value = fallback.value
        except Exception as e:
            logger.warning("Failed to resolve fallback model %s: %s", model.fallback_model, e)
    agent_options["_resolved_fallback_model"] = fallback_value
    agent_options["_resolved_model_profile"] = _model_profile_dict(model)


async def validate_agent_model_access(
    agent_options: dict | None,
    user: TokenPayload,
) -> None:
    """Validate per-request model selection against enabled models and role access."""
    if agent_options is None:
        agent_options = {}

    model_id = agent_options.get("model_id")
    selected_model = agent_options.get("model")

    from src.infra.agent.model_storage import get_model_storage

    storage = get_model_storage()
    from src.infra.agent.model_access import resolve_user_allowed_model_ids

    allowed_model_ids = await resolve_user_allowed_model_ids(user)

    if not model_id and not selected_model:
        if allowed_model_ids is None:
            return
        for allowed_model_id in allowed_model_ids:
            model = await storage.get(allowed_model_id)
            if not model:
                model = await storage.get_by_value(allowed_model_id)
            if model and model.enabled:
                await _attach_resolved_model_options(agent_options, model)
                return
        raise AuthorizationError("model_disabled")

    model = None
    if isinstance(model_id, str) and model_id:
        model = await storage.get(model_id)
    elif isinstance(selected_model, str) and selected_model:
        model = await storage.get_by_value(selected_model)

    if not model or not model.enabled:
        raise AuthorizationError("model_disabled")

    allowed_model_set = set(allowed_model_ids or [])
    if allowed_model_ids is not None and (
        model.id not in allowed_model_set and model.value not in allowed_model_set
    ):
        raise AuthorizationError("model_not_allowed")

    await _attach_resolved_model_options(agent_options, model)


async def _update_session_config(
    session_id: str,
    run_id: str,
    agent_id: str,
    request: AgentRequest,
    language: str,
    trace_id: str | None = None,
) -> None:
    """Update session metadata with conversation configuration."""
    session_manager = SessionManager()
    conversation_config = build_conversation_config(
        session_id=session_id,
        run_id=run_id,
        agent_id=agent_id,
        request=request,
        language=language,
        trace_id=trace_id,
    )
    await session_manager.update_session_metadata(session_id, conversation_config)


def resolve_goal_for_request(
    request: AgentRequest,
    existing_metadata: dict | None,
) -> tuple[GoalSpec | None, str]:
    """Resolve the run-scoped goal for this request without session inheritance."""
    _ = existing_metadata
    active_goal = coerce_goal_spec(request.goal)
    request.goal = active_goal
    return active_goal, request.message


def _persona_enabled_skills_from_snapshot(
    snapshot: PersonaPresetSnapshot,
) -> list[str] | None:
    """Return a whitelist only when the persona has usable skills."""
    if snapshot.skill_names:
        return snapshot.skill_names
    return None


def build_conversation_config(
    run_id: str,
    agent_id: str,
    request: AgentRequest,
    language: str,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> dict:
    """Build session metadata for conversation configuration."""
    conversation_config = {
        "current_run_id": run_id,
        "agent_id": agent_id,
        "executor_key": "agent_stream",
        "agent_options": request.agent_options or {},
        "disabled_tools": request.disabled_tools or [],
        "disabled_skills": request.disabled_skills or [],
        "enabled_skills": request.enabled_skills,
        "disabled_mcp_tools": request.disabled_mcp_tools or [],
        "language": language,
    }
    if trace_id:
        conversation_config["trace_id"] = trace_id
    if request.persona_preset_id:
        conversation_config["persona_preset_id"] = request.persona_preset_id
    if request.persona_preset_id and request.persona_snapshot:
        conversation_config["persona_preset_name"] = request.persona_snapshot.name
        conversation_config["persona_snapshot"] = request.persona_snapshot.model_dump()
        if request.persona_snapshot.avatar:
            conversation_config["persona_avatar"] = request.persona_snapshot.avatar
    if request.project_id:
        conversation_config["project_id"] = request.project_id
    if request.user_timezone:
        conversation_config["user_timezone"] = request.user_timezone
    if agent_id == "team" and request.team_id:
        conversation_config["team_id"] = request.team_id
    return conversation_config


async def resolve_persona_request(
    request: AgentRequest,
    user: TokenPayload,
    manager: PersonaPresetManager | None = None,
) -> None:
    """Resolve persona preset data and drop any client-supplied prompt injection."""
    request.persona_snapshot = None
    request.persona_system_prompt = None

    if not request.persona_preset_id:
        return

    persona_manager = manager or PersonaPresetManager()
    snapshot = await persona_manager.use_preset(
        request.persona_preset_id,
        user_id=user.sub,
        is_admin="persona_preset:admin" in (user.permissions or []),
    )
    request.persona_snapshot = snapshot
    request.enabled_skills = _persona_enabled_skills_from_snapshot(snapshot)
    request.persona_system_prompt = snapshot.system_prompt


async def _execute_agent_stream(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter=None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
    attachments: list[dict] | None = None,
    disabled_skills: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    persona_system_prompt: str | None = None,
    disabled_mcp_tools: list[str] | None = None,
    team_id: str | None = None,
    active_goal: dict | None = None,
    recommendation_input: str | None = None,
):
    """执行 Agent 并流式输出事件（供 TaskManager 调用）"""
    from src.infra.task.manager import TaskInterruptedError

    run_id = presenter.run_id if presenter else None

    started_at: str | None = None
    goal_end_emitted = False
    if active_goal is not None:
        started_at = datetime.now(timezone.utc).isoformat()
        yield {"event": "goal:start", "data": {"goal": active_goal, "started_at": started_at}}

    try:
        agent = await AgentFactory.get(agent_id)
        async for event in agent.stream(
            message,
            session_id,
            user_id=user_id,
            presenter=presenter,
            disabled_tools=disabled_tools,
            agent_options=agent_options,
            attachments=attachments,
            disabled_skills=disabled_skills,
            enabled_skills=enabled_skills,
            persona_system_prompt=persona_system_prompt,
            disabled_mcp_tools=disabled_mcp_tools,
            team_id=team_id,
            active_goal=active_goal,
            goal_started_at=started_at,
            recommendation_input=recommendation_input,
        ):
            if event.get("event") == "goal:end":
                goal_end_emitted = True
            yield event

        if active_goal is not None and not goal_end_emitted:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
    except (asyncio.CancelledError, TaskInterruptedError):
        # 取消/中断时，调用 agent.close 清理资源
        if run_id:
            await _close_agent_safely(agent, run_id)
        # agent 的 finally 块可能已发 goal:end，此处再 yield 确保不遗漏（Presenter 有去重）
        if active_goal is not None and not goal_end_emitted:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
        raise


# Register the default agent-stream executor so any worker can dispatch queued tasks
register_executor("agent_stream", _execute_agent_stream)


@router.post("/stream")
async def chat_stream(
    request: AgentRequest,
    http_request: Request,
    agent_id: str = "search",
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    """
    提交聊天任务，立即返回 session_id 和 run_id

    任务在后台执行，前端可通过 SSE 或轮询获取结果。
    支持基于角色的并发限制：达到上限时排队等待，队列满时返回 429。

    Args:
        request: 包含 message 和 session_id
        agent_id: 要使用的 Agent ID（默认: search）

    Returns:
        session_id: 会话 ID
        run_id: 当前对话轮次的运行 ID
        trace_id: 追踪 ID
        status: 任务状态 (pending / queued)
        queue_position: 排队位置（仅排队时返回）
    """
    from src.infra.task.concurrency import ConcurrencyResult, get_concurrency_limiter
    from src.infra.task.manager import _generate_run_id

    session_id = request.session_id or str(uuid.uuid4())
    validate_team_agent_request(agent_id, request)

    # 如果用户传入了 session_id，验证所有权
    existing_metadata: dict = {}
    existing_session = None
    if request.session_id:
        session_manager = SessionManager()
        existing_session = await session_manager.get_session(session_id)
        if existing_session:
            verify_session_ownership(existing_session, user)
            existing_metadata = existing_session.metadata or {}
    if request.retry_user_message and not request.session_id:
        raise HTTPException(status_code=400, detail="retry_user_message requires session_id")
    if request.retry_user_message and not existing_session:
        raise HTTPException(status_code=404, detail="session not found")

    active_goal, agent_message = resolve_goal_for_request(request, existing_metadata)
    active_goal_data = active_goal.model_dump() if active_goal else None
    formatted_message = format_user_message_with_timestamp(
        agent_message,
        request.user_timezone,
    )
    write_user_message = not request.retry_user_message
    user_message_written = request.retry_user_message

    task_manager = get_task_manager()
    preferred_language = _get_language(http_request)

    try:
        await resolve_persona_request(request, user)
        if request.agent_options is None:
            request.agent_options = {}
        await validate_agent_model_access(request.agent_options, user)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="角色预设不存在")
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # 生成 run_id（不管是否排队都需要唯一 ID）
    run_id = _generate_run_id()

    # Prepare attachments (needed for both queued and direct paths)
    attachments_data = (
        [a.model_dump() for a in request.attachments] if request.attachments else None
    )

    # Build task context for queued dispatch (stored in Redis, multi-worker safe)
    # trace_id is generated early so it can be passed to the executor for trace reuse
    from src.infra.writer.present import Presenter, PresenterConfig

    _pre_presenter = Presenter(
        PresenterConfig(
            session_id=session_id,
            agent_id=agent_id,
            agent_name=resolve_agent_name(agent_id),
            user_id=user.sub,
            run_id=run_id,
            enable_storage=False,
        )
    )
    trace_id = _pre_presenter.trace_id

    task_context = {
        "executor_key": "agent_stream",
        "agent_id": agent_id,
        "message": formatted_message,
        "display_message": request.message,
        "disabled_tools": request.disabled_tools,
        "agent_options": request.agent_options,
        "attachments": attachments_data,
        "trace_id": trace_id,
        "user_message_written": True,
        "disabled_skills": request.disabled_skills,
        "enabled_skills": request.enabled_skills,
        "persona_system_prompt": request.persona_system_prompt,
        "disabled_mcp_tools": request.disabled_mcp_tools,
        "team_id": request.team_id,
        "active_goal": active_goal_data,
        "recommendation_input": request.message,
    }

    # 检查并发限制
    limiter = get_concurrency_limiter()
    concurrency_result = await limiter.acquire(
        user_id=user.sub,
        roles=user.roles,
        run_id=run_id,
        session_id=session_id,
        task_context=task_context,
    )

    if concurrency_result.result == ConcurrencyResult.REJECTED_QUEUE:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "too_many_requests",
                "message": f"排队已满，当前活跃 {concurrency_result.active_count}/{concurrency_result.max_concurrent}，排队 {concurrency_result.queue_length}",
                "active": concurrency_result.active_count,
                "max_concurrent": concurrency_result.max_concurrent,
                "queue_length": concurrency_result.queue_length,
            },
        )

    if concurrency_result.result == ConcurrencyResult.QUEUED:
        # Task context already stored in Redis queue entry by acquire().
        # Ensure executor is initialized and create session immediately.
        if task_manager._executor is None:
            from src.infra.task.executor import TaskExecutor

            task_manager._executor = TaskExecutor(
                task_manager.storage, task_manager._run_info, task_manager._heartbeat
            )
        # Create session record immediately (don't wait for dequeue)
        await task_manager._executor.ensure_session(
            session_id, agent_id, user.sub, project_id=request.project_id
        )
        await task_manager._executor._update_session_status(
            session_id, TaskStatus.QUEUED, run_id=run_id
        )

        # Write user:message event to MongoDB immediately so page refresh can load it
        presenter = Presenter(
            PresenterConfig(
                session_id=session_id,
                agent_id=agent_id,
                agent_name=resolve_agent_name(agent_id),
                user_id=user.sub,
                run_id=run_id,
                trace_id=trace_id,
                enable_storage=True,
            )
        )
        await presenter._ensure_trace()
        if write_user_message:
            await presenter.emit_user_message(
                request.message,
                attachments=[a.model_dump() for a in request.attachments]
                if request.attachments
                else None,
            )

        # Mark user message as already written so executor skips re-emitting
        task_manager._run_info[run_id] = {
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": user.sub,
            "trace_id": trace_id,
            "user_message_written": True,
        }

        # 更新 session metadata，存储完整的对话配置（排队状态）
        await _update_session_config(
            session_id,
            run_id,
            agent_id,
            request,
            preferred_language,
            trace_id=trace_id,
        )

        return {
            "session_id": session_id,
            "run_id": run_id,
            "status": "queued",
            "queue_position": concurrency_result.queue_position,
            "max_concurrent": concurrency_result.max_concurrent,
        }

    if settings.TASK_BACKEND == "arq":
        _, _ = await task_manager.submit_arq(
            session_id=session_id,
            agent_id=agent_id,
            message=formatted_message,
            user_id=user.sub,
            executor_key="agent_stream",
            disabled_tools=request.disabled_tools,
            agent_options=request.agent_options,
            attachments=attachments_data,
            run_id=run_id,
            project_id=request.project_id,
            disabled_skills=request.disabled_skills,
            enabled_skills=request.enabled_skills,
            persona_system_prompt=request.persona_system_prompt,
            disabled_mcp_tools=request.disabled_mcp_tools,
            display_message=request.message,
            recommendation_input=request.message,
            trace_id=trace_id,
            team_id=request.team_id,
            active_goal=active_goal_data,
            user_message_written=user_message_written,
            write_user_message_immediately=write_user_message,
        )
    else:
        # STARTED — 正常提交后台任务
        _, _ = await task_manager.submit(
            session_id=session_id,
            agent_id=agent_id,
            message=formatted_message,
            user_id=user.sub,
            executor=_execute_agent_stream,
            disabled_tools=request.disabled_tools,
            agent_options=request.agent_options,
            attachments=attachments_data,
            run_id=run_id,
            project_id=request.project_id,
            disabled_skills=request.disabled_skills,
            enabled_skills=request.enabled_skills,
            persona_system_prompt=request.persona_system_prompt,
            disabled_mcp_tools=request.disabled_mcp_tools,
            display_message=request.message,
            recommendation_input=request.message,
            team_id=request.team_id,
            trace_id=trace_id,
            active_goal=active_goal_data,
            user_message_written=user_message_written,
            write_user_message_immediately=write_user_message,
        )

    # 更新 session metadata，存储完整的对话配置
    await _update_session_config(
        session_id,
        run_id,
        agent_id,
        request,
        preferred_language,
        trace_id=trace_id,
    )

    return {
        "session_id": session_id,
        "run_id": run_id,
        "status": "pending",
    }


@router.get("/sessions/{session_id}/stream")
async def session_stream(
    session_id: str,
    run_id: str = Query(..., description="Run ID for isolating conversation turns"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    SSE 流式读取特定 run 的事件

    从 Redis Stream 读取。
    run_id: 对话轮次 ID，用于隔离多轮对话。
    流会在收到 complete 或 error 事件后自动结束。
    """
    from src.infra.logging import get_logger
    from src.infra.session.dual_writer import get_dual_writer

    logger = get_logger(__name__)

    # 验证用户对该 session 的所有权
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    logger.info(f"[SSE] New connection: session={session_id}, run_id={run_id}")

    dual_writer = get_dual_writer()

    async def event_generator():
        logger.info(f"[SSE] Generator started for session={session_id}, run_id={run_id}")
        try:
            # 使用 run_id 读取特定轮次的事件
            event_count = 0
            async for event in dual_writer.read_from_redis(
                session_id,
                run_id=run_id,
            ):
                # 心跳事件：发送 SSE 注释（: 开头的行被 EventSource 忽略）
                # 这样能检测到客户端断开，同时不干扰前端逻辑
                if event["event_type"] == "heartbeat":
                    yield ": heartbeat\n\n"
                    continue

                event_count += 1
                yield await run_blocking_io(_format_sse_event, event)

            logger.info(f"[SSE] Stream ended after {event_count} events")

        except Exception as e:
            logger.error(f"[SSE] Generator error: {e}")
            yield 'event: error\ndata: {"error": "An internal error occurred"}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/sessions/{session_id}/status")
async def get_session_status(
    session_id: str,
    run_id: str = Query(None, description="Run ID (optional, defaults to current run)"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取任务状态

    Args:
        session_id: 会话 ID
        run_id: 运行 ID（可选，默认为当前 run）
    """
    # 验证用户对该 session 的所有权
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    task_manager = get_task_manager()

    if run_id:
        status = await task_manager.get_run_status(session_id, run_id)
        error = await task_manager.get_run_error(run_id)
    else:
        status = await task_manager.get_status(session_id)
        error = await task_manager.get_error(session_id)

    return {
        "session_id": session_id,
        "run_id": run_id,
        "status": status.value,
        "error": error,
    }


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    取消正在运行的任务（包括排队中的任务）

    Args:
        session_id: 会话 ID

    Returns:
        success: 是否成功设置取消信号
        cancelled_locally: 是否在本地实例取消
        run_id: 被取消的运行 ID
        message: 状态信息
    """
    # 验证用户对该 session 的所有权
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    task_manager = get_task_manager()
    result = await task_manager.cancel(session_id, user_id=user.sub)

    # 如果本地没有取消到，尝试从排队队列中移除
    if not result.get("cancelled_locally"):
        try:
            from src.infra.task.concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            removed = await limiter.remove_from_queue(user.sub, session_id)
            if removed:
                result["message"] = f"已从排队中移除 ({removed} 个任务)"
        except Exception as e:
            logger.warning(f"Failed to remove from queue: {e}")

    return result


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    Resume an interrupted task from the latest checkpoint for this session.
    """
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    task_manager = get_task_manager()
    return await task_manager.resume_session(session_id)

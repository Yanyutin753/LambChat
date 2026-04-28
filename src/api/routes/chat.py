"""
聊天路由

支持后台执行的聊天接口。
每次对话生成独立的 run_id，实现多轮对话隔离。
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.auth.utils import _get_language
from src.api.routes.session import verify_session_ownership
from src.infra.chat.user_message_timestamp import format_user_message_with_timestamp
from src.infra.logging import get_logger
from src.infra.session.manager import SessionManager
from src.infra.task.concurrency import register_executor
from src.infra.task.manager import get_task_manager
from src.infra.task.status import TaskStatus
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.session import SessionUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)


async def _update_session_config(
    session_id: str,
    run_id: str,
    agent_id: str,
    request: AgentRequest,
    language: str,
) -> None:
    """Update session metadata with conversation configuration."""
    session_manager = SessionManager()
    conversation_config = {
        "current_run_id": run_id,
        "agent_id": agent_id,
        "executor_key": "agent_stream",
        "agent_options": request.agent_options or {},
        "disabled_tools": request.disabled_tools or [],
        "disabled_skills": request.disabled_skills or [],
        "disabled_mcp_tools": request.disabled_mcp_tools or [],
        "language": language,
    }
    if request.project_id:
        conversation_config["project_id"] = request.project_id
    await session_manager.update_session(
        session_id,
        SessionUpdate(metadata=conversation_config),
    )


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
    disabled_mcp_tools: list[str] | None = None,
):
    """执行 Agent 并流式输出事件（供 TaskManager 调用）"""
    from src.infra.task.manager import TaskInterruptedError

    agent = await AgentFactory.get(agent_id)
    run_id = presenter.run_id if presenter else None

    try:
        async for event in agent.stream(
            message,
            session_id,
            user_id=user_id,
            presenter=presenter,
            disabled_tools=disabled_tools,
            agent_options=agent_options,
            attachments=attachments,
            disabled_skills=disabled_skills,
            disabled_mcp_tools=disabled_mcp_tools,
        ):
            yield event
    except (asyncio.CancelledError, TaskInterruptedError):
        # 取消/中断时，调用 agent.close 清理资源
        if run_id:
            await agent.close(run_id)
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
    formatted_message = format_user_message_with_timestamp(
        request.message,
        request.user_timezone,
    )

    # 如果用户传入了 session_id，验证所有权
    if request.session_id:
        session_manager = SessionManager()
        existing_session = await session_manager.get_session(session_id)
        if existing_session:
            verify_session_ownership(existing_session, user)

    task_manager = get_task_manager()
    preferred_language = _get_language(http_request)

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
        "disabled_tools": request.disabled_tools,
        "agent_options": request.agent_options,
        "attachments": attachments_data,
        "trace_id": trace_id,
        "user_message_written": True,
        "disabled_skills": request.disabled_skills,
        "disabled_mcp_tools": request.disabled_mcp_tools,
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
            session_id, TaskStatus.PENDING, run_id=run_id
        )

        # Write user:message event to MongoDB immediately so page refresh can load it
        presenter = Presenter(
            PresenterConfig(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user.sub,
                run_id=run_id,
                trace_id=trace_id,
                enable_storage=True,
            )
        )
        await presenter._ensure_trace()
        await presenter.emit_user_message(
            formatted_message,
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
        )

        return {
            "session_id": session_id,
            "run_id": run_id,
            "status": "queued",
            "queue_position": concurrency_result.queue_position,
            "max_concurrent": concurrency_result.max_concurrent,
        }

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
        disabled_mcp_tools=request.disabled_mcp_tools,
    )

    # 更新 session metadata，存储完整的对话配置
    await _update_session_config(
        session_id,
        run_id,
        agent_id,
        request,
        preferred_language,
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
                # Include timestamp in the data payload for deduplication
                event_data = event["data"]
                if isinstance(event_data, dict) and event.get("timestamp"):
                    # Create a copy to avoid modifying the original
                    event_data = {**event_data, "_timestamp": event["timestamp"]}
                yield f"event: {event['event_type']}\ndata: {json.dumps(event_data, ensure_ascii=False)}\nid: {event['id']}\n\n"

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

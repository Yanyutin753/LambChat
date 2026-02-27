"""
聊天路由

支持后台执行的聊天接口。
每次对话生成独立的 run_id，实现多轮对话隔离。
"""

import asyncio
import json
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.session import verify_session_ownership
from src.infra.session.manager import SessionManager
from src.infra.task.manager import get_task_manager
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = logging.getLogger(__name__)
async def _execute_agent_stream(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter=None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
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
        ):
            yield event
    except (asyncio.CancelledError, TaskInterruptedError):
        # 取消/中断时，调用 agent.close 清理资源
        if run_id:
            await agent.close(run_id)
        raise


@router.post("/stream")
async def chat_stream(
    request: AgentRequest,
    agent_id: str = "search",
    user: TokenPayload = Depends(require_permissions("chat:write")),
):
    """
    提交聊天任务，立即返回 session_id 和 run_id

    任务在后台执行，前端可通过 SSE 或轮询获取结果。

    Args:
        request: 包含 message 和 session_id
        agent_id: 要使用的 Agent ID（默认: search）

    Returns:
        session_id: 会话 ID
        run_id: 当前对话轮次的运行 ID
        trace_id: 追踪 ID
        status: 任务状态
    """
    session_id = request.session_id or str(uuid.uuid4())
    logger.info(f"[chat_stream] Received disabled_tools request: {request.disabled_tools}")

    # 如果用户传入了 session_id，验证所有权
    if request.session_id:
        session_manager = SessionManager()
        existing_session = await session_manager.get_session(session_id)
        if existing_session:
            verify_session_ownership(existing_session, user)

    # 提交后台任务，获取 run_id
    task_manager = get_task_manager()
    run_id, _ = await task_manager.submit(
        session_id=session_id,
        agent_id=agent_id,
        message=request.message,
        user_id=user.sub,
        executor=_execute_agent_stream,
        disabled_tools=request.disabled_tools,  # 传递用户禁用的工具
        agent_options=request.agent_options,  # 传递 agent 选项
    )

    # 获取 trace_id（任务启动后会有）
    trace_id = task_manager.get_trace_id(run_id)

    return {
        "session_id": session_id,
        "run_id": run_id,
        "trace_id": trace_id,
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
    import logging

    from src.infra.session.dual_writer import get_dual_writer

    logger = logging.getLogger(__name__)

    # 验证用户对该 session 的所有权
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    logger.info(
        f"[SSE] New connection: session={session_id}, run_id={run_id}"
    )

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
                event_count += 1
                # logger.info(f"[SSE] Yielding event #{event_count}: {event['event_type']}")
                # Include timestamp in the data payload for deduplication
                event_data = event["data"]
                if isinstance(event_data, dict) and event.get("timestamp"):
                    # Create a copy to avoid modifying the original
                    event_data = {**event_data, "_timestamp": event["timestamp"]}
                yield f"event: {event['event_type']}\ndata: {json.dumps(event_data, ensure_ascii=False)}\nid: {event['id']}\n\n"

            logger.info(f"[SSE] Stream ended after {event_count} events")

        except Exception as e:
            logger.error(f"[SSE] Generator error: {e}")
            yield f'event: error\ndata: {{"error": "{e}"}}\n\n'

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
    取消正在运行的任务

    Args:
        session_id: 会话 ID

    Returns:
        success: 是否成功取消
        message: 状态信息
    """
    # 验证用户对该 session 的所有权
    session_manager = SessionManager()
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    verify_session_ownership(session, user)

    task_manager = get_task_manager()
    success = await task_manager.cancel(session_id)

    if success:
        return {"success": True, "message": "任务已取消"}
    else:
        return {"success": False, "message": "没有正在运行的任务"}

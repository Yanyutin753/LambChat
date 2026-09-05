"""steer × ask_human 挂起的中断处理（从 chat.py 拆出，守住 1000 行红线）。

ask_human interrupt 模式下图挂在 interrupt 上，插话永远等不到下一次
模型调用——此时插话视为打断：终止挂起 run、关闭挂起审批、补终态事件，
前端把状态行「工作中」切为「已停止」后，插话内容作为新 run 的普通
消息发送（复用未送达插话的补发机制）。
"""

from src.api.deps import TokenPayload
from src.infra.logging import get_logger
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.session import Session

logger = get_logger(__name__)


async def steer_interrupt_waiting_human(
    session_id: str,
    session: Session,
    user: TokenPayload,
    message_id: str,
    task_manager,
) -> dict:
    """插话打断 ask_human 挂起：终止挂起 run、关闭挂起审批、写封存事件。

    挂起 run 的执行器协程已返回（graph 停在 interrupt），普通取消路径
    不会替它写终态——这里显式落 CANCELLED 状态、补 user:cancel(reason=steer)
    + done 事件（前端据此把状态行「工作中」切为「已停止」），并关闭挂起
    审批避免卡片残留。
    """
    from src.infra.session.dual_writer import get_dual_writer
    from src.infra.storage.mongodb import get_approval_storage
    from src.infra.task.hitl import (
        _acquire_resume_lock,
        _release_resume_lock,
        is_interrupt_approval,
    )
    from src.infra.task.steer import purge_stale_steers
    from src.infra.utils.datetime import utc_now_iso

    metadata = getattr(session, "metadata", None) or {}
    run_id = str(metadata.get("current_run_id") or "")
    trace_id = str(metadata.get("trace_id") or "") or None

    # 挂起审批先抢恢复锁：与「回答审批」的恢复提交互斥。抢锁失败说明
    # 恢复正在别的请求里启动，插话按会话不可插话冲突返回；抢到锁后
    # 对方的 submit_hitl_resume_run 会因会话已离开 WAITING_HUMAN 跳过。
    approvals = [
        approval
        for approval in await get_approval_storage().list_pending(session_id=session_id, limit=20)
        if is_interrupt_approval(approval)
    ]
    held_locks: list[tuple[str, str]] = []
    try:
        for approval in approvals:
            token = await _acquire_resume_lock(approval.id)
            if token is None:
                raise AppError(
                    ErrorCode.STEER_SESSION_NOT_RUNNING,
                    args={"status": TaskStatus.WAITING_HUMAN.value},
                )
            held_locks.append((approval.id, token))

        await task_manager.cancel(session_id, user_id=user.sub)
        # cancel_run 不改 task_status（挂起 run 无执行器协程写终态），
        # 显式落 CANCELLED：恢复方、后续 steer 与普通发送都以状态机为准。
        if task_manager._executor is None:
            from src.infra.task.executor import TaskExecutor

            task_manager._executor = TaskExecutor(
                task_manager.storage, task_manager._run_info, task_manager._heartbeat
            )
        await task_manager._executor._update_session_status(
            session_id, TaskStatus.CANCELLED, "Interrupted by steer", run_id=run_id or None
        )

        dual_writer = get_dual_writer()
        for approval in approvals:
            # cancelled 而非 approved/rejected：不携带恢复值，纯关卡片
            await get_approval_storage().update_status(approval.id, "cancelled")
            await dual_writer.write_event(
                session_id=session_id,
                event_type="approval_resolved",
                data={
                    "id": approval.id,
                    "tool_call_id": (getattr(approval, "metadata", None) or {}).get("tool_call_id"),
                    "interrupt_id": (getattr(approval, "metadata", None) or {}).get("interrupt_id"),
                    "status": "cancelled",
                    "success": False,
                    "result": {"status": "cancelled", "message": "已被新插话打断"},
                    "timestamp": utc_now_iso(),
                },
                run_id=run_id or None,
                trace_id=trace_id,
            )

        # 封存旧消息：user:cancel 带 reason=steer（前端不追加已取消胶囊，
        # 只切状态行文字），done 关闭流让前端把插话补发为普通消息
        await dual_writer.write_event(
            session_id=session_id,
            event_type="user:cancel",
            data={
                "user_id": user.sub,
                "run_id": run_id,
                "timestamp": utc_now_iso(),
                "reason": "steer",
            },
            run_id=run_id or None,
            trace_id=trace_id,
        )
        await dual_writer.write_event(
            session_id=session_id,
            event_type="done",
            data={
                "status": "cancelled",
                "run_id": run_id,
                "timestamp": utc_now_iso(),
            },
            run_id=run_id or None,
            trace_id=trace_id,
        )
        if run_id:
            await task_manager._executor._expire_terminal_stream(session_id, run_id, dual_writer)

        # 挂起前残留在插话队列的条目一并清空：新 run 不应把它们当插话注入
        try:
            await purge_stale_steers(session_id)
        except Exception as e:
            logger.warning(f"Failed to purge stale steers on interrupt: {e}")
    finally:
        for approval_id, token in held_locks:
            await _release_resume_lock(approval_id, token)

    return {
        "status": "interrupted",
        "outcome": "interrupted",
        "session_id": session_id,
        "message_id": message_id,
        "queued": False,
    }

"""steer × ask_human 挂起的中断处理（从 chat.py 拆出，守住 1000 行红线）。

ask_human interrupt 模式下图挂在 interrupt 上，插话永远等不到下一次
模型调用——此时插话视为打断：终止挂起 run、关闭挂起审批、补终态事件，
前端把状态行「工作中」切为「已停止」后，插话内容作为新 run 的普通
消息发送（复用未送达插话的补发机制）。
"""

from src.api.deps import TokenPayload
from src.api.routes.hitl_interrupt_cleanup import (
    pending_interrupt_approvals,
    seal_suspended_run,
)
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
    # 挂起审批先抢恢复锁：与「回答审批」的恢复提交互斥。抢锁失败说明
    # 恢复正在别的请求里启动，插话按会话不可插话冲突返回；抢到锁后
    # 对方的 submit_hitl_resume_run 会因会话已离开 WAITING_HUMAN 跳过。
    from src.infra.task.hitl import _acquire_resume_lock, _release_resume_lock
    from src.infra.task.steer import purge_stale_steers

    approvals = await pending_interrupt_approvals(session_id)
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

        await seal_suspended_run(
            session=session,
            task_manager=task_manager,
            user_id=user.sub,
            approvals=approvals,
            cancel_reason="steer",
            resolved_message="已被新插话打断",
            status_error="Interrupted by steer",
        )

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

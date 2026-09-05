"""ask_human 挂起 run 的统一封存（steer 打断与普通取消共用）。

挂起 run 的执行器协程已返回（图停在 interrupt 上），普通取消路径不会替它
写终态——run 被取消后会话离开 WAITING_HUMAN，挂起审批既无法恢复（
submit_hitl_resume_run 校验状态直接跳过）也没人关闭，前端审批卡永远
pending、输入框被隐藏，会话彻底卡死（2026-09-05 生产事故）。

封存动作：落 CANCELLED 状态、关闭挂起审批（cancelled 而非
approved/rejected——不携带恢复值）、补 approval_resolved + user:cancel +
done 终态事件、过期实时流。与「回答审批」的恢复提交靠恢复锁互斥。
"""

from src.infra.logging import get_logger
from src.infra.task.status import TaskStatus

logger = get_logger(__name__)


async def pending_interrupt_approvals(session_id: str) -> list:
    """列出会话所有挂起中的 interrupt 审批。"""
    from src.infra.storage.mongodb import get_approval_storage
    from src.infra.task.hitl import is_interrupt_approval

    approvals = await get_approval_storage().list_pending(session_id=session_id, limit=20)
    return [approval for approval in approvals if is_interrupt_approval(approval)]


def approvals_bound_to_run(approvals: list, run_id: str) -> list:
    """过滤出绑定当前 run 的审批；未绑定 run 的残留审批一并纳入。"""
    bound = []
    for approval in approvals:
        approval_run = str((getattr(approval, "metadata", None) or {}).get("run_id") or "")
        if not approval_run or not run_id or approval_run == run_id:
            bound.append(approval)
    return bound


async def seal_suspended_run(
    *,
    session,
    task_manager,
    user_id: str,
    approvals: list,
    cancel_reason: str | None,
    resolved_message: str,
    status_error: str,
) -> None:
    """封存挂起 run（调用方需已持有各审批的恢复锁）。

    落 CANCELLED、关闭审批卡片、写 user:cancel + done 终态事件、过期流。
    approvals 为空时仍封存 run 本身（WAITING_HUMAN 残留态自愈）。
    """
    from src.infra.session.dual_writer import get_dual_writer
    from src.infra.storage.mongodb import get_approval_storage
    from src.infra.utils.datetime import utc_now_iso

    session_id = getattr(session, "session_id", None) or (
        getattr(approvals[0], "session_id", None) if approvals else None
    )
    if not session_id:
        return
    metadata = getattr(session, "metadata", None) or {}
    run_id = str(metadata.get("current_run_id") or "")
    trace_id = str(metadata.get("trace_id") or "") or None

    # cancel_run 不改 task_status（挂起 run 无执行器协程写终态），
    # 显式落 CANCELLED：恢复方、后续 steer 与普通发送都以状态机为准。
    if task_manager._executor is None:
        from src.infra.task.executor import TaskExecutor

        task_manager._executor = TaskExecutor(
            task_manager.storage, task_manager._run_info, task_manager._heartbeat
        )
    await task_manager._executor._update_session_status(
        session_id, TaskStatus.CANCELLED, status_error, run_id=run_id or None
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
                "result": {"status": "cancelled", "message": resolved_message},
                "timestamp": utc_now_iso(),
            },
            run_id=run_id or None,
            trace_id=trace_id,
        )

    # 封存旧消息：普通取消不带 reason（前端追加「已取消」胶囊）；
    # steer 带 reason=steer（前端只切状态行文字，不追加胶囊）。
    cancel_data = {"user_id": user_id, "run_id": run_id, "timestamp": utc_now_iso()}
    if cancel_reason:
        cancel_data["reason"] = cancel_reason
    await dual_writer.write_event(
        session_id=session_id,
        event_type="user:cancel",
        data=cancel_data,
        run_id=run_id or None,
        trace_id=trace_id,
    )
    await dual_writer.write_event(
        session_id=session_id,
        event_type="done",
        data={"status": "cancelled", "run_id": run_id, "timestamp": utc_now_iso()},
        run_id=run_id or None,
        trace_id=trace_id,
    )
    if run_id:
        await task_manager._executor._expire_terminal_stream(session_id, run_id, dual_writer)


async def reconcile_cancelled_hitl_approvals(
    session_id: str,
    *,
    user_id: str,
    task_manager,
) -> bool:
    """普通取消后的调和：关闭竞态残留的挂起 interrupt 审批并封存 run。

    覆盖两种竞态形态（都会让审批永 pending 而无法恢复）：
    ① 取消到达时 run 已挂起：cancel 把 WAITING_HUMAN 覆写成 CANCELLED；
    ② 取消与挂起同时发生：run 在取消宽限窗口内挂起，状态同样被覆写。
    只处理绑定当前 run 的审批；恢复锁被「回答审批」请求持有时整单跳过
    （恢复后的 run 由取消中断信号走正常终止路径写终态事件）。
    """
    from src.infra.session.storage import SessionStorage
    from src.infra.task.hitl import _acquire_resume_lock, _release_resume_lock

    approvals = await pending_interrupt_approvals(session_id)
    if not approvals:
        return False

    session = await SessionStorage().get_by_session_id(session_id)
    if session is None:
        return False
    run_id = str((getattr(session, "metadata", None) or {}).get("current_run_id") or "")
    approvals = approvals_bound_to_run(approvals, run_id)
    if not approvals:
        return False

    held_locks: list[tuple[str, str]] = []
    try:
        for approval in approvals:
            token = await _acquire_resume_lock(approval.id)
            if token is None:
                # 恢复提交正在进行：不动状态、不关审批、不写事件，
                # 由恢复后的 run 走正常取消路径。
                return False
            held_locks.append((approval.id, token))

        await seal_suspended_run(
            session=session,
            task_manager=task_manager,
            user_id=user_id,
            approvals=approvals,
            cancel_reason=None,
            resolved_message="运行已取消",
            status_error="Task cancelled",
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to reconcile cancelled HITL approvals: {e}")
        return False
    finally:
        for approval_id, token in held_locks:
            await _release_resume_lock(approval_id, token)

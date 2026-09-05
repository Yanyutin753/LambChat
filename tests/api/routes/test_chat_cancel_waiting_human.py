"""POST /chat/sessions/{id}/cancel × ask_human 挂起（WAITING_HUMAN）。

生产事故（2026-09-05）：用户点「停止」的瞬间 run 恰好挂在 ask_human interrupt 上。
挂起 run 的执行器协程已返回，取消路径只把 task_status 覆写成 CANCELLED、trace 打成
error，却不关闭挂起审批、不补 user:cancel/done 终态事件——前端审批卡永远 pending、
输入框被隐藏、审批又因会话已离开 WAITING_HUMAN 被拒绝恢复，会话彻底卡死。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.api.routes.chat import cancel_session
from src.infra.task.status import TaskStatus


def _user(sub="user-1"):
    return SimpleNamespace(sub=sub)


class _CancelHarness:
    def __init__(self, *, status_after_cancel: str = "cancelled") -> None:
        self.cancel_calls: list[tuple[str, str | None]] = []
        self.status_calls: list[tuple[str, TaskStatus]] = []
        self.expired_streams: list[str] = []
        self.written_events: list[tuple[str, dict]] = []
        self.approval_updates: list[tuple[str, str]] = []
        self.lock_fail_ids: set[str] = set()
        self.held_locks: list[str] = []
        self.session_status = "waiting_human"
        self._status_after_cancel = status_after_cancel

    def session(self):
        harness = self
        return SimpleNamespace(
            user_id="user-1",
            session_id="session-1",
            metadata={
                "current_run_id": "run-9",
                "trace_id": "trace-9",
                "agent_id": "fast",
                "task_status": harness.session_status,
            },
        )

    def task_manager(self) -> SimpleNamespace:
        harness = self

        class _Executor:
            async def _update_session_status(
                self, session_id, task_status, error=None, run_id=None
            ):
                harness.status_calls.append((session_id, task_status))
                harness.session_status = task_status.value

            async def _expire_terminal_stream(self, session_id, run_id, dual_writer):
                harness.expired_streams.append(run_id)

        class _Manager:
            _executor = _Executor()

            async def cancel(self, session_id, user_id=None):
                harness.cancel_calls.append((session_id, user_id))
                # 真实 manager.cancel_run 在中断信号设置成功后无条件覆写 CANCELLED
                harness.session_status = harness._status_after_cancel
                return {
                    "success": True,
                    "cancelled_locally": False,
                    "run_id": "run-9",
                    "message": "取消信号已发送",
                }

        return _Manager()

    def approval_storage(self, approvals: list) -> SimpleNamespace:
        harness = self

        async def _list_pending(session_id=None, user_id=None, limit=100):
            return approvals

        async def _update_status(approval_id, status, response=None):
            harness.approval_updates.append((approval_id, status))
            return True

        return SimpleNamespace(list_pending=_list_pending, update_status=_update_status)

    def dual_writer(self) -> SimpleNamespace:
        harness = self

        async def _write_event(session_id, event_type, data, run_id=None, trace_id=None):
            harness.written_events.append((event_type, data))

        return SimpleNamespace(write_event=_write_event)

    def wire(self, monkeypatch, approvals: list) -> None:
        import src.infra.task.hitl as hitl

        harness = self

        class _SessionManager:
            async def get_session(self, session_id):
                return harness.session()

        monkeypatch.setattr("src.api.routes.chat.SessionManager", _SessionManager)
        monkeypatch.setattr("src.api.routes.chat.get_task_manager", lambda: harness.task_manager())
        monkeypatch.setattr(
            "src.infra.storage.mongodb.get_approval_storage",
            lambda: harness.approval_storage(approvals),
        )
        monkeypatch.setattr(
            "src.infra.session.storage.SessionStorage",
            lambda: SimpleNamespace(
                get_by_session_id=AsyncMock(side_effect=lambda _: harness.session())
            ),
        )
        monkeypatch.setattr(
            "src.infra.session.dual_writer.get_dual_writer",
            lambda: harness.dual_writer(),
        )

        async def _acquire(approval_id: str):
            if approval_id in harness.lock_fail_ids:
                return None
            harness.held_locks.append(approval_id)
            return f"token-{approval_id}"

        async def _release(approval_id: str, token: str) -> None:
            if approval_id in harness.held_locks:
                harness.held_locks.remove(approval_id)

        monkeypatch.setattr(hitl, "_acquire_resume_lock", _acquire)
        monkeypatch.setattr(hitl, "_release_resume_lock", _release)
        # 队列移除兜底：本地未取消到时会调用，测试中不关心
        monkeypatch.setattr(
            "src.infra.task.concurrency.get_concurrency_limiter",
            lambda: SimpleNamespace(remove_from_queue=AsyncMock(return_value=0)),
        )


def _interrupt_approval(approval_id="appr-1", run_id="run-9"):
    return SimpleNamespace(
        id=approval_id,
        session_id="session-1",
        user_id="user-1",
        status="pending",
        message="要继续吗？",
        metadata={"mode": "interrupt", "run_id": run_id, "trace_id": "trace-9"},
    )


async def test_cancel_waiting_human_closes_approval_and_writes_terminal_events(
    monkeypatch,
) -> None:
    """挂起中取消：关闭挂起审批、补 approval_resolved + user:cancel + done、过期流。"""
    harness = _CancelHarness()
    harness.wire(monkeypatch, [_interrupt_approval()])

    result = await cancel_session("session-1", user=_user())

    assert result["success"] is True
    assert harness.cancel_calls == [("session-1", "user-1")]
    assert harness.approval_updates == [("appr-1", "cancelled")]
    assert harness.held_locks == []
    event_types = [event_type for event_type, _ in harness.written_events]
    assert "approval_resolved" in event_types
    assert event_types[-2] == "user:cancel"
    assert event_types[-1] == "done"
    cancel_data = harness.written_events[-2][1]
    assert cancel_data["run_id"] == "run-9"
    assert cancel_data["user_id"] == "user-1"
    # 普通取消：不带 steer reason，前端追加「已取消」胶囊
    assert cancel_data.get("reason") != "steer"
    assert harness.written_events[-1][1]["status"] == "cancelled"
    assert harness.expired_streams == ["run-9"]
    assert harness.session_status == "cancelled"


async def test_cancel_race_after_status_clobbered_still_reconciles(monkeypatch) -> None:
    """竞态形态：cancel 已把 task_status 盖成 cancelled、审批仍 pending → 同样调和。"""
    harness = _CancelHarness()
    harness.session_status = "cancelled"  # 取消请求到达前状态已被覆写
    harness.wire(monkeypatch, [_interrupt_approval()])

    await cancel_session("session-1", user=_user())

    assert harness.approval_updates == [("appr-1", "cancelled")]
    event_types = [event_type for event_type, _ in harness.written_events]
    assert event_types[-2:] == ["user:cancel", "done"]


async def test_cancel_skips_approval_locked_by_inflight_resume(monkeypatch) -> None:
    """取消与「回答审批」同时到达：恢复锁被占的审批不动，由恢复后的 run 走正常取消。"""
    harness = _CancelHarness()
    harness.lock_fail_ids = {"appr-1"}
    harness.wire(monkeypatch, [_interrupt_approval()])

    result = await cancel_session("session-1", user=_user())

    assert result["success"] is True
    assert harness.approval_updates == []
    assert harness.written_events == []
    assert harness.expired_streams == []


async def test_cancel_ignores_approvals_of_other_runs(monkeypatch) -> None:
    """只关闭属于当前 run 的挂起审批，历史 run 的残留不动。"""
    harness = _CancelHarness()
    harness.wire(monkeypatch, [_interrupt_approval(run_id="run-old")])

    await cancel_session("session-1", user=_user())

    assert harness.approval_updates == []
    assert harness.written_events == []


async def test_cancel_running_session_without_approvals_unchanged(monkeypatch) -> None:
    """普通运行中取消（无挂起审批）：不写任何补偿事件，行为与之前一致。"""
    harness = _CancelHarness()
    harness.session_status = "running"
    harness.wire(monkeypatch, [])

    result = await cancel_session("session-1", user=_user())

    assert result["success"] is True
    assert harness.approval_updates == []
    assert harness.written_events == []
    assert harness.expired_streams == []

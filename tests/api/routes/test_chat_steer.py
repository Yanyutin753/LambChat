"""POST /chat/sessions/{id}/steer 端点测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.chat import SteerRequest, list_pending_steers, steer_running_agent
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError


def _user(sub="user-1"):
    return SimpleNamespace(sub=sub)


def _session(user_id="user-1"):
    return SimpleNamespace(user_id=user_id, session_id="session-1")


@pytest.fixture(autouse=True)
def queue():
    import src.infra.task.steer as steer

    q = steer.SteerQueue(redis=None)
    previous = steer._steer_queue
    steer._steer_queue = q
    yield q
    steer._steer_queue = previous
    # 清理本地测试队列；每个测试使用独立实例，不触碰共享 Redis。
    q._pending.clear()


async def test_steer_enqueues_message_for_running_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    from src.infra.task.steer import get_steer_queue

    result = await steer_running_agent(
        "session-1", SteerRequest(message="中途插话", message_id="client-1"), user=_user()
    )

    assert result["status"] == "queued"
    assert result["message_id"] == "client-1"
    assert await get_steer_queue().drain("session-1") == ["中途插话"]


async def test_steer_retry_with_same_id_does_not_duplicate(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    first = await steer_running_agent(
        "session-1", SteerRequest(message="重复安全", message_id="same-id"), user=_user()
    )
    second = await steer_running_agent(
        "session-1", SteerRequest(message="重复安全", message_id="same-id"), user=_user()
    )
    assert first["message_id"] == second["message_id"] == "same-id"
    assert second["queued"] == 1
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().drain("session-1")


async def test_steer_accepts_attachments(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    from src.infra.task.steer import get_steer_queue

    result = await steer_running_agent(
        "session-1",
        SteerRequest(
            message="分析这个文件",
            message_id="with-file",
            attachments=[
                {
                    "id": "file-1",
                    "key": "uploads/file-1",
                    "name": "报告.pdf",
                    "type": "document",
                    "mimeType": "application/pdf",
                    "size": 100,
                    "url": "/api/files/file-1",
                }
            ],
        ),
        user=_user(),
    )

    assert result["outcome"] == "accepted"
    item = (await get_steer_queue().drain_items("session-1"))[0]
    assert item.attachments[0]["name"] == "报告.pdf"
    await get_steer_queue().ack_items("session-1")


async def test_cancel_with_unknown_id_does_not_remove_same_text_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    from src.infra.task.steer import SteerItem, get_steer_queue

    queue = get_steer_queue()
    await queue.enqueue_item("session-1", SteerItem(id="real-id", content="同文本"))
    from src.api.routes.chat import cancel_steered_message

    result = await cancel_steered_message(
        "session-1",
        SteerRequest(message="同文本", message_id="missing-id"),
        user=_user(),
    )
    assert result["status"] == "not_found"
    assert [item.id for item in await queue.drain_items("session-1")] == ["real-id"]


async def test_pending_steers_can_be_restored_after_refresh(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    from src.infra.task.steer import SteerItem, get_steer_queue

    queue = get_steer_queue()
    await queue.enqueue_item("session-refresh", SteerItem(id="restore-id", content="刷新后还在"))
    result = await list_pending_steers("session-refresh", user=_user())
    assert result["items"][0]["message_id"] == "restore-id"
    await queue.drain("session-refresh")


async def test_steer_rejects_when_task_not_running(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.COMPLETED)),
    )

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="hi"), user=_user())
    assert exc_info.value.error_code.code == "steer_session_not_running"
    assert exc_info.value.http_status == 409


class _InterruptHarness:
    """steer × WAITING_HUMAN（ask_human 挂起）中断路径的公共桩件。"""

    def __init__(self) -> None:
        self.cancel_calls: list[tuple[str, str | None]] = []
        self.status_calls: list[tuple[str, TaskStatus]] = []
        self.expired_streams: list[str] = []
        self.written_events: list[tuple[str, dict]] = []
        self.approval_updates: list[tuple[str, str]] = []
        self.lock_fail_ids: set[str] = set()
        self.held_locks: list[str] = []

    def task_manager(self, status: TaskStatus) -> SimpleNamespace:
        harness = self

        class _Executor:
            async def _update_session_status(self, session_id, task_status, error=None, run_id=None):
                harness.status_calls.append((session_id, task_status))

            async def _expire_terminal_stream(self, session_id, run_id, dual_writer):
                harness.expired_streams.append(run_id)

        class _Manager:
            _executor = _Executor()

            async def get_status(self, session_id):
                return status

            async def cancel(self, session_id, user_id=None):
                harness.cancel_calls.append((session_id, user_id))
                return {
                    "success": True,
                    "cancelled_locally": False,
                    "run_id": "run-9",
                    "message": "ok",
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

    def lock_modules(self, monkeypatch) -> None:
        import src.infra.task.hitl as hitl
        from src.infra.utils.datetime import utc_now_iso

        harness = self

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
        monkeypatch.setattr(
            "src.infra.session.dual_writer.get_dual_writer",
            lambda: harness.dual_writer(),
        )
        # done 事件时间戳与真实实现一致走 utc_now_iso
        assert utc_now_iso()  # 仅确认可导入


def _waiting_session(user_id="user-1"):
    return SimpleNamespace(
        user_id=user_id,
        session_id="session-1",
        metadata={
            "current_run_id": "run-9",
            "trace_id": "trace-9",
            "agent_id": "fast",
        },
    )


def _interrupt_approval(approval_id="appr-1"):
    return SimpleNamespace(
        id=approval_id,
        session_id="session-1",
        user_id="user-1",
        status="pending",
        message="要继续吗？",
        metadata={"mode": "interrupt", "run_id": "run-9", "trace_id": "trace-9"},
    )


def _wire_waiting_human(monkeypatch, harness, approvals):
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_waiting_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: harness.task_manager(TaskStatus.WAITING_HUMAN),
    )
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_approval_storage",
        lambda: harness.approval_storage(approvals),
    )
    harness.lock_modules(monkeypatch)


async def test_steer_waiting_human_interrupts_suspended_run(monkeypatch) -> None:
    """ask_human 挂起中的插话 = 中断挂起 run：关审批、写封存事件、返回 interrupted。"""
    harness = _InterruptHarness()
    _wire_waiting_human(monkeypatch, harness, [_interrupt_approval()])

    result = await steer_running_agent(
        "session-1", SteerRequest(message="换个方向", message_id="client-9"), user=_user()
    )

    assert result["outcome"] == "interrupted"
    assert result["status"] == "interrupted"
    assert result["message_id"] == "client-9"
    # 挂起 run 被取消，会话状态机落 CANCELLED（cancel_run 不写 task_status）
    assert harness.cancel_calls == [("session-1", "user-1")]
    assert ("session-1", TaskStatus.CANCELLED) in harness.status_calls
    # 挂起审批被关闭（cancelled，非 approved/rejected——不触发恢复）
    assert harness.approval_updates == [("appr-1", "cancelled")]
    assert harness.held_locks == []  # 锁已释放
    # 终态事件：审批关闭 + 封存旧消息（user:cancel reason=steer + done）
    event_types = [event_type for event_type, _ in harness.written_events]
    assert "approval_resolved" in event_types
    assert event_types[-2] == "user:cancel"
    assert event_types[-1] == "done"
    cancel_data = harness.written_events[-2][1]
    assert cancel_data["reason"] == "steer"
    assert cancel_data["run_id"] == "run-9"
    # 流过期，避免重连重放已封存的 run
    assert harness.expired_streams == ["run-9"]
    # 不进入插话队列（消息由前端作为新 run 普通发送）
    from src.infra.task.steer import get_steer_queue

    assert await get_steer_queue().list_items("session-1") == []


async def test_steer_waiting_human_without_approvals_still_interrupts(monkeypatch) -> None:
    """WAITING_HUMAN 但无挂起审批（响应后恢复失败的残留态）：同样中断自愈。"""
    harness = _InterruptHarness()
    _wire_waiting_human(monkeypatch, harness, [])

    result = await steer_running_agent(
        "session-1", SteerRequest(message="继续"), user=_user()
    )

    assert result["outcome"] == "interrupted"
    assert ("session-1", TaskStatus.CANCELLED) in harness.status_calls
    assert harness.approval_updates == []
    event_types = [event_type for event_type, _ in harness.written_events]
    assert "user:cancel" in event_types and "done" in event_types


async def test_steer_waiting_human_resume_race_returns_conflict(monkeypatch) -> None:
    """插话与「回答审批」同时到达：恢复锁被占时插话按 409 冲突返回。"""
    harness = _InterruptHarness()
    harness.lock_fail_ids = {"appr-1"}
    _wire_waiting_human(monkeypatch, harness, [_interrupt_approval()])

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="hi"), user=_user())
    assert exc_info.value.error_code.code == "steer_session_not_running"
    # 冲突时不动取消/审批/事件
    assert harness.cancel_calls == []
    assert harness.approval_updates == []
    assert harness.written_events == []
    assert ("session-1", TaskStatus.CANCELLED) not in harness.status_calls


async def test_steer_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=None)),
    )

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="hi"), user=_user())
    assert exc_info.value.error_code.code == "session_not_found"
    assert exc_info.value.http_status == 404


async def test_steer_rejects_other_users_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session(user_id="user-2"))),
    )

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="hi"), user=_user("user-1"))
    assert exc_info.value.error_code.code == "session_access_denied"
    assert exc_info.value.http_status == 403


async def test_steer_rejects_empty_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="   "), user=_user())
    assert exc_info.value.error_code.code == "steer_content_required"
    assert exc_info.value.http_status == 422


async def test_new_chat_submit_purges_stale_pending_steers(queue) -> None:
    """新 run 提交时清空残留插话：旧插话已被前端补发为普通消息，不能再次注入。"""
    await queue.enqueue("session-1", "残留插话")

    from src.infra.task.steer import purge_stale_steers

    await purge_stale_steers("session-1")

    assert await queue.list_items("session-1") == []


async def test_purge_failure_does_not_break_submit(monkeypatch) -> None:
    """清队列失败只记日志，不能让正常提交失败。"""
    import src.infra.task.steer as steer

    class _BrokenQueue:
        async def clear_session(self, session_id):
            raise RuntimeError("redis down")

    monkeypatch.setattr(steer, "_steer_queue", _BrokenQueue())

    from src.infra.task.steer import purge_stale_steers

    await purge_stale_steers("session-1")  # 不抛错即通过


def test_chat_stream_wires_steer_purge() -> None:
    """chat_stream 必须在生成 run_id 后调用清理，防止残留插话注入新 run。"""
    import inspect

    from src.api.routes import chat as chat_module

    source = inspect.getsource(chat_module.chat_stream)
    assert "purge_stale_steers(" in source
    assert "_generate_run_id()" in source

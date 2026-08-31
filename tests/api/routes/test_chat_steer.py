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
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.WAITING_HUMAN)),
    )

    with pytest.raises(AppError) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="hi"), user=_user())
    assert exc_info.value.error_code.code == "steer_session_not_running"
    assert exc_info.value.http_status == 409


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

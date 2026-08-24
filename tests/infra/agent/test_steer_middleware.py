"""SteerMiddleware（运行中插话注入）单元测试。"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.steer import SteerMiddleware


class _Request:
    """模拟 ModelRequest：记录 override 调用。"""

    def __init__(self, messages=None):
        self.messages = messages if messages is not None else [HumanMessage(content="原消息")]
        self.override_calls: list[dict] = []

    def override(self, **kwargs):
        self.override_calls.append(kwargs)
        return _Request(messages=kwargs.get("messages", self.messages))


class _Response:
    """模拟 ModelResponse。"""


async def test_pending_message_is_injected_and_persisted() -> None:
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("middleware-session-1", "中途插话")

    middleware = SteerMiddleware(session_id="middleware-session-1")
    request = _Request()
    seen_requests: list[_Request] = []

    async def handler(req):
        seen_requests.append(req)
        return _Response()

    result = await middleware.awrap_model_call(request, handler)

    # 模型看到了插话消息（追加在历史之后）
    assert len(seen_requests) == 1
    contents = [m.content for m in seen_requests[0].messages]
    assert contents == ["原消息", "中途插话"]

    # 结果携带 Command(update) 把插话消息持久化进图状态
    command = getattr(result, "command", None)
    update = getattr(command, "update", None)
    assert update is not None
    injected = update.get("messages")
    assert isinstance(injected, list) and len(injected) == 1
    assert isinstance(injected[0], HumanMessage)
    assert injected[0].content == "中途插话"

    # 注入后队列被清空（不会重复注入下一次调用）
    assert await get_steer_queue().drain("middleware-session-1") == []


async def test_no_pending_message_passes_through_untouched() -> None:
    middleware = SteerMiddleware(session_id="session-clean")
    request = _Request()
    sentinel = _Response()

    async def handler(_req):
        return sentinel

    result = await middleware.awrap_model_call(request, handler)

    assert result is sentinel
    assert request.override_calls == []


async def test_multiple_pending_messages_inject_in_order() -> None:
    from src.infra.task.steer import get_steer_queue

    queue = get_steer_queue()
    await queue.enqueue("session-2", "插话一")
    await queue.enqueue("session-2", "插话二")

    middleware = SteerMiddleware(session_id="session-2")
    seen: list[_Request] = []

    async def handler(req):
        seen.append(req)
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    contents = [m.content for m in seen[0].messages]
    assert contents == ["原消息", "插话一", "插话二"]


async def test_other_session_messages_are_not_injected() -> None:
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-other", "别的会话")

    middleware = SteerMiddleware(session_id="session-mine")
    sentinel = _Response()

    async def handler(_req):
        return sentinel

    result = await middleware.awrap_model_call(_Request(), handler)

    assert result is sentinel
    # 别的会话消息仍在队列中，未被消费
    assert await get_steer_queue().drain("session-other") == ["别的会话"]


async def test_failed_model_call_requeues_messages() -> None:
    """模型调用整体失败时，插话消息重新入队，等待下次运行送达（不丢失）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-fail", "重要插话")

    middleware = SteerMiddleware(session_id="session-fail")

    async def handler(_req):
        raise RuntimeError("model down")

    with pytest.raises(RuntimeError):
        await middleware.awrap_model_call(_Request(), handler)

    # 失败后消息回到队列最前（保持 FIFO：先到的插话先送达）
    assert await get_steer_queue().drain("session-fail") == ["重要插话"]


async def test_steer_event_persisted_before_model_call_runs() -> None:
    """steer:message 事件在模型调用开始前写出。

    事件必须先于本次调用的输出事件进入 Redis/MongoDB，实时 SSE 与
    历史回放中插话才会排在回答之前（而不是落在 run 尾部）。
    """
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-order", "插话")

    saved: list[dict] = []

    class _FakePresenter:
        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-order", presenter=_FakePresenter())
    observed_save_counts: list[int] = []

    async def handler(_req):
        observed_save_counts.append(len(saved))
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert observed_save_counts == [1]
    assert saved[0]["event"] == "steer:message"
    assert saved[0]["data"]["content"] == "插话"


async def test_steer_event_carries_created_at_send_time() -> None:
    """事件附带 created_at（用户发送时刻），前端用它作为消息时间戳。"""
    from datetime import datetime, timezone

    from src.infra.task.steer import SteerItem, get_steer_queue

    sent_at = datetime(2026, 8, 22, 15, 14, 55, tzinfo=timezone.utc)
    await get_steer_queue().enqueue_item(
        "session-created-at",
        SteerItem(id="steer-ts", content="插话", created_at=sent_at),
    )

    saved: list[dict] = []

    class _FakePresenter:
        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-created-at", presenter=_FakePresenter())

    async def handler(_req):
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert saved[0]["data"]["created_at"] == "2026-08-22T15:14:55+00:00"


async def test_failed_model_call_keeps_injected_event_and_requeues() -> None:
    """调用失败时注入事件已按注入时刻写出（消息确已发送）；消息原 ID 回队重试。"""
    from src.infra.task.steer import SteerItem, get_steer_queue

    await get_steer_queue().enqueue_item(
        "session-fail-order",
        SteerItem(id="steer-retry-me", content="重要插话"),
    )

    saved: list[dict] = []

    class _FakePresenter:
        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-fail-order", presenter=_FakePresenter())

    async def handler(_req):
        raise RuntimeError("model down")

    with pytest.raises(RuntimeError):
        await middleware.awrap_model_call(_Request(), handler)

    assert [event["data"]["message_id"] for event in saved] == ["steer-retry-me"]
    requeued = await get_steer_queue().drain("session-fail-order")
    assert requeued == ["重要插话"]


async def test_successful_injection_persists_via_presenter(monkeypatch) -> None:
    """注入成功后经 presenter.save_event 写独立 steer:message 事件（归属当前 run 的 trace）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-p", "要持久化的插话")

    saved: list[dict] = []

    class _FakePresenter:
        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-p", presenter=_FakePresenter())

    async def handler(_req):
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert len(saved) == 1
    assert saved[0]["event"] == "steer:message"
    assert saved[0]["data"]["content"] == "要持久化的插话"
    assert str(saved[0]["data"]["message_id"]).startswith("steer-")


async def test_successful_injection_preserves_client_message_id() -> None:
    from src.infra.task.steer import SteerItem, get_steer_queue

    await get_steer_queue().enqueue_item(
        "session-id", SteerItem(id="client-123", content="按这个方向")
    )
    saved: list[dict] = []

    class _FakePresenter:
        run_id = "run-123"

        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-id", presenter=_FakePresenter())

    async def handler(_req):
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)
    assert saved[0]["data"]["message_id"] == "client-123"
    assert saved[0]["data"]["run_id"] == "run-123"


async def test_queued_steer_survives_hitl_pause_and_uses_same_resumed_run() -> None:
    """挂起前已接收的 steer 在同 Run 恢复后仍只注入、持久化一次。"""
    from datetime import datetime, timezone

    from src.infra.task.steer import SteerItem, get_steer_queue

    queue = get_steer_queue()
    sent_at = datetime(2026, 8, 22, 15, 0, 0, tzinfo=timezone.utc)
    await queue.enqueue_item(
        "session-hitl",
        SteerItem(id="steer-before-pause", content="继续时按这个方向", created_at=sent_at),
    )

    saved: list[dict] = []

    class _ResumedPresenter:
        run_id = "run-same"

        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-hitl", presenter=_ResumedPresenter())
    seen: list[_Request] = []

    async def handler(req):
        seen.append(req)
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert [message.content for message in seen[0].messages] == [
        "原消息",
        "继续时按这个方向",
    ]
    assert saved == [
        {
            "event": "steer:message",
            "data": {
                "content": "继续时按这个方向",
                "message_id": "steer-before-pause",
                "attachments": [],
                "created_at": "2026-08-22T15:00:00+00:00",
                "run_id": "run-same",
            },
        }
    ]
    assert await queue.drain_items("session-hitl") == []


async def test_successful_injection_falls_back_to_dual_writer(monkeypatch) -> None:
    """无 presenter 时回退 dual_writer 直写（实时 SSE 兜底）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-p2", "兜底的插话")

    written: list[dict] = []

    class _FakeWriter:
        async def write_event(self, **kwargs):
            written.append(kwargs)

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: _FakeWriter())

    middleware = SteerMiddleware(session_id="session-p2")

    async def handler(_req):
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert len(written) == 1
    assert written[0]["event_type"] == "steer:message"
    assert written[0]["data"]["content"] == "兜底的插话"


async def test_persist_failure_does_not_break_injection(monkeypatch) -> None:
    """事件写入失败不影响注入本身（尽力而为）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-pp", "插话")

    def broken_writer():
        raise RuntimeError("dual writer down")

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", broken_writer)

    middleware = SteerMiddleware(session_id="session-pp")
    sentinel = _Response()

    async def handler(_req):
        return sentinel

    result = await middleware.awrap_model_call(_Request(), handler)

    assert getattr(result, "command", None) is not None  # 注入仍成功


def test_imports_match_langchain_middleware_shape() -> None:
    from langchain.agents.middleware.types import AgentMiddleware

    assert issubclass(SteerMiddleware, AgentMiddleware)
    assert isinstance(AIMessage(content="ok"), AIMessage)

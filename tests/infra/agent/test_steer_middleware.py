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

    await get_steer_queue().enqueue("session-1", "中途插话")

    middleware = SteerMiddleware(session_id="session-1")
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
    assert await get_steer_queue().drain("session-1") == []


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


async def test_successful_injection_persists_user_message_events(monkeypatch) -> None:
    """注入成功后写 user:message 事件（SSE 实时 + 历史持久化）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-p", "要持久化的插话")

    written: list[dict] = []

    class _FakeWriter:
        async def write_event(self, **kwargs):
            written.append(kwargs)


    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: _FakeWriter()
    )

    middleware = SteerMiddleware(session_id="session-p")

    async def handler(_req):
        return _Response()

    await middleware.awrap_model_call(_Request(), handler)

    assert len(written) == 1
    assert written[0]["session_id"] == "session-p"
    assert written[0]["event_type"] == "user:message"
    assert written[0]["data"]["content"] == "要持久化的插话"
    assert str(written[0]["data"]["message_id"]).startswith("steer-")


async def test_persist_failure_does_not_break_injection(monkeypatch) -> None:
    """事件写入失败不影响注入本身（尽力而为）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-pp", "插话")

    def broken_writer():
        raise RuntimeError("dual writer down")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", broken_writer
    )

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

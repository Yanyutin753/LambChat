"""SteerMiddleware（运行中插话注入）单元测试。"""

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)

from src.infra.agent.middleware.steer import SteerMiddleware

try:  # deepagents 为这些 agent 提供真实的 messages 通道 reducer
    from deepagents._messages_reducer import _messages_delta_reducer
except ImportError:  # pragma: no cover - 环境缺 deepagents 时跳过 reducer 级断言
    _messages_delta_reducer = None


def _tool_call(call_id: str = "call_1", name: str = "ls") -> dict:
    return {"name": name, "args": {}, "id": call_id, "type": "tool_call"}


def _tool_response_adjacent(messages: list) -> bool:
    """OpenAI 协议不变量：每个带 tool_calls 的 AI 消息后紧跟其全部 ToolMessage。"""
    pending: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            if pending:
                return False
            pending = {tc["id"] for tc in m.tool_calls}
        elif isinstance(m, ToolMessage):
            pending.discard(m.tool_call_id)
        elif pending:
            return False
    return True


async def test_injected_message_lands_before_model_response() -> None:
    """回归（2026-09-08 生产 400）：插话必须先于模型响应进入图状态。

    旧实现经 ``Command(update)`` 在模型节点完成后追加插话，一旦该次响应
    携带 tool_calls，tools 节点写回的 ToolMessage 落在插话之后，下一次
    模型调用因 "insufficient tool messages following tool_calls message"
    被 DeepSeek/OpenAI 拒绝。注入改到 ``before_model`` 钩子后，插话先落
    state、模型响应后落，顺序恒为 [插话, AI(tool_calls), ToolMessage]。
    """
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("middleware-session-1", "中途插话")

    middleware = SteerMiddleware(session_id="middleware-session-1")
    state = {
        "messages": [
            HumanMessage(content="原消息"),
            AIMessage(content="看下目录", tool_calls=[_tool_call()]),
            ToolMessage(content="No files found", name="ls", tool_call_id="call_1"),
        ]
    }

    update = await middleware.abefore_model(state, None)

    assert update is not None

    injected = [m for m in update["messages"] if not isinstance(m, RemoveMessage)]
    assert [m.content for m in injected] == ["中途插话"]

    if _messages_delta_reducer is not None:
        # 模拟框架时序：before_model 更新先提交，随后模型响应与工具结果追加
        after_update = _messages_delta_reducer(state["messages"], [update["messages"]])
        final = _messages_delta_reducer(
            after_update,
            [
                [AIMessage(content="", tool_calls=[_tool_call("call_2", "write_file")])],
                [ToolMessage(content="ok", name="write_file", tool_call_id="call_2")],
            ],
        )
        assert _tool_response_adjacent(final)
        # 插话在 AI(tool_calls) 之前（模型是对插话做出的响应）
        contents = [m.content for m in final]
        assert contents.index("中途插话") < len(final) - 2


async def test_no_pending_message_returns_none() -> None:
    middleware = SteerMiddleware(session_id="session-clean")

    assert await middleware.abefore_model({"messages": []}, None) is None


async def test_multiple_pending_messages_inject_in_order() -> None:
    from src.infra.task.steer import get_steer_queue

    queue = get_steer_queue()
    await queue.enqueue("session-2", "插话一")
    await queue.enqueue("session-2", "插话二")

    middleware = SteerMiddleware(session_id="session-2")
    update = await middleware.abefore_model({"messages": []}, None)

    injected = [m for m in update["messages"] if not isinstance(m, RemoveMessage)]
    assert [m.content for m in injected] == ["插话一", "插话二"]
    assert await queue.drain("session-2") == []


async def test_other_session_messages_are_not_injected() -> None:
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-other", "别的会话")

    middleware = SteerMiddleware(session_id="session-mine")

    assert await middleware.abefore_model({"messages": []}, None) is None
    # 别的会话消息仍在队列中，未被消费
    assert await get_steer_queue().drain("session-other") == ["别的会话"]


async def test_misordered_history_is_healed_on_injection() -> None:
    """存量坏会话自愈：历史里 AI(tool_calls) 与 ToolMessage 之间夹了消息时重排。

    旧 bug 已在生产写出 [AI(tool_calls), Human, ToolMessage] 形态的 state，
    不自愈则该会话每次调用都 400。重排把夹中间的消息后移到 ToolMessage 之后。
    """
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-heal", "新插话")

    middleware = SteerMiddleware(session_id="session-heal")
    state = {
        "messages": [
            HumanMessage(content="原消息"),
            AIMessage(content="", tool_calls=[_tool_call("call_a", "search_tools")]),
            HumanMessage(content="旧插话"),
            ToolMessage(content="found", name="search_tools", tool_call_id="call_a"),
        ]
    }

    update = await middleware.abefore_model(state, None)

    messages = update["messages"]
    assert isinstance(messages[0], RemoveMessage)  # 整表重写
    healed = messages[1:]
    assert [type(m).__name__ for m in healed] == [
        "HumanMessage",  # 原消息
        "AIMessage",  # AI(tool_calls)
        "ToolMessage",  # 其响应紧跟
        "HumanMessage",  # 旧插话后移
        "HumanMessage",  # 新插话在末尾
    ]
    if _messages_delta_reducer is not None:
        final = _messages_delta_reducer(state["messages"], [messages])
        assert _tool_response_adjacent(final)


async def test_clean_history_injects_without_full_rewrite() -> None:
    """顺序合法时不整表重写（避免每次调用都写全量消息）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-clean-hist", "插话")

    middleware = SteerMiddleware(session_id="session-clean-hist")
    state = {
        "messages": [
            HumanMessage(content="原消息"),
            AIMessage(content="", tool_calls=[_tool_call()]),
            ToolMessage(content="ok", name="ls", tool_call_id="call_1"),
        ]
    }

    update = await middleware.abefore_model(state, None)

    assert not any(isinstance(m, RemoveMessage) for m in update["messages"])
    assert [m.content for m in update["messages"]] == ["插话"]


def _reorder(messages: list) -> list | None:
    from src.infra.agent.middleware.steer import _reorder_tool_response_adjacency

    return _reorder_tool_response_adjacency(messages)


def test_reorder_multi_tool_calls_keep_all_responses_adjacent() -> None:
    """一条 AI 消息带多个 tool_calls：全部响应必须紧跟其后，夹层消息后移。"""
    reordered = _reorder(
        [
            HumanMessage(content="原消息"),
            AIMessage(
                content="",
                tool_calls=[_tool_call("c1"), _tool_call("c2", "grep")],
            ),
            HumanMessage(content="夹层插话"),
            ToolMessage(content="r1", name="ls", tool_call_id="c1"),
            ToolMessage(content="r2", name="grep", tool_call_id="c2"),
        ]
    )

    assert reordered is not None
    assert [type(m).__name__ for m in reordered] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "ToolMessage",
        "HumanMessage",
    ]
    assert reordered[4].content == "夹层插话"


def test_reorder_holds_messages_between_partial_tool_responses() -> None:
    """多响应之间也夹了消息：响应聚合完之前不得放行夹层。"""
    reordered = _reorder(
        [
            AIMessage(content="", tool_calls=[_tool_call("c1"), _tool_call("c2", "grep")]),
            ToolMessage(content="r1", name="ls", tool_call_id="c1"),
            HumanMessage(content="夹层"),
            ToolMessage(content="r2", name="grep", tool_call_id="c2"),
        ]
    )

    assert reordered is not None
    assert [type(m).__name__ for m in reordered] == [
        "AIMessage",
        "ToolMessage",
        "ToolMessage",
        "HumanMessage",
    ]


def test_reorder_dangling_tool_calls_left_untouched() -> None:
    """悬空 tool_calls（始终无响应）不重排：留给 PatchToolCallsMiddleware 补合成响应。"""
    messages = [
        HumanMessage(content="原消息"),
        AIMessage(content="", tool_calls=[_tool_call("c-never")]),
        HumanMessage(content="插话A"),
        AIMessage(content="done"),
    ]

    assert _reorder(messages) is None


def test_reorder_ai_without_tool_calls_does_not_hold() -> None:
    """无 tool_calls 的 AI 消息不开启响应等待，后续消息顺序原样保留。"""
    messages = [
        HumanMessage(content="问题"),
        AIMessage(content="回答"),
        HumanMessage(content="追问"),
        AIMessage(content="", tool_calls=[_tool_call("c9")]),
        ToolMessage(content="ok", name="ls", tool_call_id="c9"),
    ]

    assert _reorder(messages) is None


def test_reorder_consecutive_broken_pairs_all_healed() -> None:
    """多处乱序一次全部修复，且原始相对顺序（除后移外）保持稳定。"""
    reordered = _reorder(
        [
            HumanMessage(content="q1"),
            AIMessage(content="", tool_calls=[_tool_call("a1")]),
            HumanMessage(content="s1"),
            ToolMessage(content="r1", name="ls", tool_call_id="a1"),
            HumanMessage(content="q2"),
            AIMessage(content="", tool_calls=[_tool_call("a2")]),
            HumanMessage(content="s2"),
            ToolMessage(content="r2", name="ls", tool_call_id="a2"),
        ]
    )

    assert reordered is not None
    assert [(type(m).__name__, m.content) for m in reordered] == [
        ("HumanMessage", "q1"),
        ("AIMessage", ""),
        ("ToolMessage", "r1"),
        ("HumanMessage", "s1"),
        ("HumanMessage", "q2"),
        ("AIMessage", ""),
        ("ToolMessage", "r2"),
        ("HumanMessage", "s2"),
    ]
    assert _tool_response_adjacent(reordered)


async def test_steer_event_persisted_before_model_call_runs() -> None:
    """steer:message 事件在注入时写出（before_model 节点先于模型节点执行）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-order", "插话")

    saved: list[dict] = []

    class _FakePresenter:
        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-order", presenter=_FakePresenter())

    await middleware.abefore_model({"messages": []}, None)

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

    await middleware.abefore_model({"messages": []}, None)

    assert saved[0]["data"]["created_at"] == "2026-08-22T15:14:55+00:00"


async def test_injection_persists_via_presenter_with_run_id() -> None:
    """注入经 presenter.save_event 写独立 steer:message 事件（归属当前 run 的 trace）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-p", "要持久化的插话")

    saved: list[dict] = []

    class _FakePresenter:
        run_id = "run-123"

        async def save_event(self, event):
            saved.append(event)

    middleware = SteerMiddleware(session_id="session-p", presenter=_FakePresenter())

    await middleware.abefore_model({"messages": []}, None)

    assert len(saved) == 1
    assert saved[0]["event"] == "steer:message"
    assert saved[0]["data"]["content"] == "要持久化的插话"
    assert str(saved[0]["data"]["message_id"]).startswith("steer-")
    assert saved[0]["data"]["run_id"] == "run-123"


async def test_injection_falls_back_to_dual_writer(monkeypatch) -> None:
    """无 presenter 时回退 dual_writer 直写（实时 SSE 兜底）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-p2", "兜底的插话")

    written: list[dict] = []

    class _FakeWriter:
        async def write_event(self, **kwargs):
            written.append(kwargs)

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: _FakeWriter())

    middleware = SteerMiddleware(session_id="session-p2")

    update = await middleware.abefore_model({"messages": []}, None)

    assert len(written) == 1
    assert written[0]["event_type"] == "steer:message"
    assert written[0]["data"]["content"] == "兜底的插话"
    assert update is not None  # 事件失败不影响注入本身


async def test_persist_failure_does_not_break_injection(monkeypatch) -> None:
    """事件写入失败不影响注入本身（尽力而为）。"""
    from src.infra.task.steer import get_steer_queue

    await get_steer_queue().enqueue("session-pp", "插话")

    def broken_writer():
        raise RuntimeError("dual writer down")

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", broken_writer)

    middleware = SteerMiddleware(session_id="session-pp")

    update = await middleware.abefore_model({"messages": []}, None)

    assert update is not None  # 注入仍成功


async def test_drained_message_is_delivered_via_state_not_requeue() -> None:
    """drain 即送达：更新经 before_model 节点提交 checkpoint，模型调用失败也不回队。

    消息已在图状态里持久化，失败后新 run 从 state 续跑仍能看到插话；
    再回队反而会在下次注入时重复。
    """
    from src.infra.task.steer import SteerItem, get_steer_queue

    await get_steer_queue().enqueue_item(
        "session-fail", SteerItem(id="steer-1", content="重要插话")
    )

    middleware = SteerMiddleware(session_id="session-fail")

    update = await middleware.abefore_model({"messages": []}, None)

    injected = [m for m in update["messages"] if not isinstance(m, RemoveMessage)]
    assert [m.content for m in injected] == ["重要插话"]
    assert await get_steer_queue().drain("session-fail") == []


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

    first = await middleware.abefore_model({"messages": []}, None)
    # 恢复后再次进入 before_model：队列已空，不重复注入
    second = await middleware.abefore_model({"messages": []}, None)

    assert first is not None
    assert second is None
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


def test_imports_match_langchain_middleware_shape() -> None:
    from langchain.agents.middleware.types import AgentMiddleware

    assert issubclass(SteerMiddleware, AgentMiddleware)
    assert isinstance(AIMessage(content="ok"), AIMessage)

"""SteerMiddleware 与真实 langchain agent 图的集成测试。

用 MemorySaver + 假模型跑完整的 model→tools→before_model 循环，验证
插话注入后发给模型的消息序列满足 OpenAI 协议不变量（带 tool_calls 的
assistant 消息后紧跟对应 ToolMessage），以及存量乱序会话的自愈。
"""

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from src.infra.agent.middleware.steer import SteerMiddleware


class _RecordingModel(FakeMessagesListChatModel):
    """按脚本顺序返回响应，并记录每次调用收到的消息序列。"""

    received: list[list[AnyMessage]] = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self.received.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(self, tools, **kwargs: Any):  # noqa: ARG002
        """脚本响应已含 tool_calls，绑定为空操作。"""
        return self


def _assert_tool_response_adjacent(messages: list[AnyMessage]) -> None:
    """OpenAI 协议不变量：AI(tool_calls) 后必须紧跟其全部 ToolMessage。"""
    pending: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            assert not pending, (
                f"AI(tool_calls) 后存在未回应的调用 {pending}：{[m.type for m in messages]}"
            )
            pending = {tc["id"] for tc in message.tool_calls}
        elif isinstance(message, ToolMessage):
            pending.discard(message.tool_call_id)
        else:
            assert not pending, (
                f"AI(tool_calls) 与其 ToolMessage 之间夹了 {message.type} 消息："
                f"{[m.type for m in messages]}"
            )


class _SilentPresenter:
    run_id = "run-integration"

    async def save_event(self, event: dict) -> None:
        pass


async def test_mid_run_steer_keeps_request_order_valid() -> None:
    """工具执行期间插话：后续所有模型调用收到的序列必须协议合法。

    回归场景（2026-09-08 生产）：插话注入后模型以 tool_calls 响应插话，
    旧实现经 Command(update) 在模型节点完成后追加插话，导致 ToolMessage
    落在插话之后，下一次模型调用被 DeepSeek 拒绝（400）。
    """
    from src.infra.task.steer import get_steer_queue

    session_id = "integration-mid-run"
    queue = get_steer_queue()

    async def enqueue_steer() -> str:
        """模拟用户在工具执行期间插话：把消息放入 steer 队列。"""
        await queue.enqueue(session_id, "中途插话")
        return "ok"

    model = _RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "enqueue_steer", "args": {}, "id": "call_1", "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="按插话的方向处理",
                tool_calls=[
                    {"name": "enqueue_steer", "args": {}, "id": "call_2", "type": "tool_call"}
                ],
            ),
            AIMessage(content="完成"),
        ]
    )
    graph = create_agent(
        model,
        tools=[enqueue_steer],
        middleware=[SteerMiddleware(session_id=session_id, presenter=_SilentPresenter())],
        checkpointer=MemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="原消息")]},
        config={"configurable": {"thread_id": "t-mid-run"}},
    )

    assert "完成" in str(result["messages"][-1].content)
    assert len(model.received) == 3

    for received in model.received:
        _assert_tool_response_adjacent(received)

    # 插话注入后的那次调用：插话在已完成的 ToolMessage 之后、模型响应之前
    second = model.received[1]
    assert [m.content for m in second if isinstance(m, HumanMessage)] == ["原消息", "中途插话"]
    assert isinstance(second[-1], HumanMessage) and second[-1].content == "中途插话"


async def test_previously_broken_thread_is_healed_on_next_run() -> None:
    """旧 bug 写出的乱序 state（AI(tool_calls) 与 ToolMessage 之间夹消息）自愈。"""
    from src.infra.task.steer import get_steer_queue

    session_id = "integration-heal"
    queue = get_steer_queue()
    config = {"configurable": {"thread_id": "t-heal"}}

    model = _RecordingModel(responses=[AIMessage(content="已恢复")])
    graph = create_agent(
        model,
        tools=[],
        middleware=[SteerMiddleware(session_id=session_id, presenter=_SilentPresenter())],
        checkpointer=MemorySaver(),
    )

    # 复现旧 bug 写入的 state：插话夹在 AI(tool_calls) 与 ToolMessage 之间
    await graph.aupdate_state(
        config,
        {
            "messages": [
                HumanMessage(content="原消息"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "search_tools", "args": {}, "id": "call_x", "type": "tool_call"}
                    ],
                ),
                HumanMessage(content="旧插话"),
                ToolMessage(content="found 1 tool", name="search_tools", tool_call_id="call_x"),
            ]
        },
    )

    await queue.enqueue(session_id, "新插话")
    await graph.ainvoke({"messages": []}, config=config)

    assert len(model.received) == 1
    received = model.received[0]
    _assert_tool_response_adjacent(received)
    types = [m.type for m in received]
    assert types == ["human", "ai", "tool", "human", "human"]
    assert received[3].content == "旧插话"
    assert received[4].content == "新插话"


async def test_failed_model_call_after_injection_resumes_without_duplicate() -> None:
    """注入后模型调用失败：新 run 从 state 续跑，插话恰好送达一次。

    before_model 更新已随 checkpoint 提交（drain 即送达），失败后插话仍在
    图状态里；再次 ainvoke（模拟新 run）不得重复注入、序列仍协议合法。
    """
    from src.infra.task.steer import get_steer_queue

    session_id = "integration-fail-resume"
    queue = get_steer_queue()

    class _FlakyModel(_RecordingModel):
        """第一次调用抛错，之后恢复正常（模拟模型故障后新 run 恢复）。"""

        fail_first: bool = True

        def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
            if self.fail_first:
                self.fail_first = False
                raise RuntimeError("model down")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    model = _FlakyModel(
        responses=[AIMessage(content="恢复完成")],
    )
    graph = create_agent(
        model,
        tools=[],
        middleware=[SteerMiddleware(session_id=session_id, presenter=_SilentPresenter())],
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-fail-resume"}}

    # 模拟用户在模型故障前插话，注入成功但模型调用失败
    await queue.enqueue(session_id, "故障前插话")
    with pytest.raises(RuntimeError, match="model down"):
        await graph.ainvoke({"messages": [HumanMessage(content="原消息")]}, config=config)

    # 故障后不回队（drain 即送达），队列视角干净
    assert await queue.list_items(session_id) == []

    # 新 run 续跑：插话仍在 state，恰好一次；序列协议合法
    result = await graph.ainvoke({"messages": []}, config=config)

    assert "恢复完成" in str(result["messages"][-1].content)
    # 故障调用不计入 received（父类只在成功路径记录）；续跑调用恰好一次
    assert len(model.received) == 1
    for received in model.received:
        _assert_tool_response_adjacent(received)
    humans = [m.content for m in model.received[0] if isinstance(m, HumanMessage)]
    assert humans == ["原消息", "故障前插话"]


async def test_multiple_steers_across_model_calls_each_injected_once() -> None:
    """两次不同时点的插话，分别注入各自的下一次模型调用，顺序与协议都合法。"""
    from src.infra.task.steer import get_steer_queue

    session_id = "integration-multi-steer"
    queue = get_steer_queue()

    async def steer_one() -> str:
        "用户第一段插话"
        await queue.enqueue(session_id, "插话一")
        return "ok"

    async def steer_two() -> str:
        "用户第二段插话"
        await queue.enqueue(session_id, "插话二")
        return "ok"

    model = _RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "steer_one", "args": {}, "id": "c1", "type": "tool_call"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "steer_two", "args": {}, "id": "c2", "type": "tool_call"}],
            ),
            AIMessage(content="两段插话都已处理"),
        ]
    )
    graph = create_agent(
        model,
        tools=[steer_one, steer_two],
        middleware=[SteerMiddleware(session_id=session_id, presenter=_SilentPresenter())],
        checkpointer=MemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="原消息")]},
        config={"configurable": {"thread_id": "t-multi"}},
    )

    assert "两段插话都已处理" in str(result["messages"][-1].content)
    assert len(model.received) == 3
    for received in model.received:
        _assert_tool_response_adjacent(received)
        humans = [m.content for m in received if isinstance(m, HumanMessage)]
        assert humans.count("插话一") <= 1 and humans.count("插话二") <= 1
    # 第二次调用看到插话一、第三次调用看到插话一+插话二（state 累积）
    assert [m.content for m in model.received[1] if isinstance(m, HumanMessage)] == [
        "原消息",
        "插话一",
    ]
    assert [m.content for m in model.received[2] if isinstance(m, HumanMessage)] == [
        "原消息",
        "插话一",
        "插话二",
    ]


async def test_deepagents_graph_mid_run_steer_keeps_protocol() -> None:
    """生产栈形态（deepagents create_deep_agent，Fast Agent 同款）下的插话回归。

    deepagents 在 langchain create_agent 外再包了 filesystem/subagents 等
    中间件与自带的 messages reducer；插话注入与乱序自愈必须在该栈下同样
    成立（协议不变量 + 插话先于响应）。
    """
    from deepagents import create_deep_agent

    from src.infra.task.steer import get_steer_queue

    session_id = "integration-deepagents"
    queue = get_steer_queue()

    async def enqueue_steer() -> str:
        "用户在工具执行期间插话"
        await queue.enqueue(session_id, "deepagents 栈下的插话")
        return "ok"

    model = _RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "enqueue_steer", "args": {}, "id": "d1", "type": "tool_call"}],
            ),
            AIMessage(content="deepagents 栈处理完成"),
        ]
    )
    graph = create_deep_agent(
        model,
        [enqueue_steer],
        system_prompt="You are a test agent.",
        middleware=[SteerMiddleware(session_id=session_id, presenter=_SilentPresenter())],
        checkpointer=MemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="原消息")]},
        config={"configurable": {"thread_id": "t-deepagents"}},
    )

    assert "deepagents 栈处理完成" in str(result["messages"][-1].content)
    assert len(model.received) == 2
    for received in model.received:
        _assert_tool_response_adjacent(received)
    humans = [m.content for m in model.received[1] if isinstance(m, HumanMessage)]
    assert humans == ["原消息", "deepagents 栈下的插话"]

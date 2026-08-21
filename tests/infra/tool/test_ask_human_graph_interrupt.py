"""ask_human interrupt 模式端到端测试（issue #218）。

用真实 deepagents 图 + 脚本化模型 + 内存 checkpointer 验证完整链路：
1. 主代理调用 ask_human → interrupt() 挂起（工具零副作用）；
2. 编排层（fast_agent_node 挂起后）从 interrupt payload 物化审批记录；
3. 子代理调用 ask_human → interrupt 跨子图传播并挂起整个运行；
4. Command(resume=...) 恢复：断点续跑、审批不重复创建、
   工具拿到 resume 值并返回标准结果；
5. 恢复后新的 ask_human（另一次提问）再次挂起并可再次物化/恢复。
"""

import json
from types import SimpleNamespace
from typing import Any, List

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import src.infra.task.hitl as hitl_mod
import src.infra.tool.human_tool.tool as tool_mod
from src.infra.task.hitl import materialize_ask_human_approvals
from src.infra.tool.human_tool.runtime import hitl_interrupt_supported
from src.kernel.config import settings


class ScriptedModel(GenericFakeChatModel):
    """按脚本顺序返回消息的假模型（支持 bind_tools）。"""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


class ApprovalRecorder:
    """记录编排层物化的审批，并让 list_pending 返回可配置的 pending 集合。"""

    def __init__(self) -> None:
        self.created: List[dict] = []
        self.sse: List[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_create_approval(**kwargs):
            self.created.append(kwargs)
            return SimpleNamespace(
                id=f"approval-{len(self.created)}",
                message=kwargs.get("message", ""),
                type="form",
            )

        async def fake_send_sse(approval, fields, session_id, run_id):
            self.sse.append(approval.id)

        fake_storage = SimpleNamespace(
            list_pending=self._list_pending,
        )

        monkeypatch.setattr("src.api.routes.human.create_approval", fake_create_approval)
        monkeypatch.setattr(hitl_mod, "_send_approval_sse", fake_send_sse)
        monkeypatch.setattr("src.infra.storage.mongodb.get_approval_storage", lambda: fake_storage)

    async def _list_pending(self, session_id=None, user_id=None, limit=100):
        return [
            SimpleNamespace(message=kw["message"], metadata=kw.get("metadata"))
            for kw in self.created
        ]


@pytest.fixture
def interrupt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HITL_MODE", "interrupt", raising=False)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> ApprovalRecorder:
    rec = ApprovalRecorder()
    rec.install(monkeypatch)
    return rec


def _ask_tool() -> tool_mod.AskHumanTool:
    return tool_mod.AskHumanTool(session_id="session-1")


async def _run(graph: Any, graph_input: Any, config: dict) -> None:
    async for _ in graph.astream(graph_input, config, stream_mode="values"):
        pass


async def _materialize(graph: Any, config: dict, recorder: ApprovalRecorder) -> None:
    """模拟 fast_agent_node 挂起后的编排层动作。"""
    snapshot = await graph.aget_state(config)
    await materialize_ask_human_approvals(
        snapshot, session_id="session-1", run_id="run-1", user_id="user-1"
    )


def _tool_json(message: str) -> dict:
    return json.loads(message)


async def test_main_agent_ask_human_suspend_and_resume(
    interrupt_mode: None, recorder: ApprovalRecorder
) -> None:
    model = ScriptedModel(
        messages=iter(
            [
                _tool_call(
                    "ask_human",
                    {"message": "需要确认", "choices": ["a", "b"]},
                    "call-1",
                ),
                AIMessage(content="已确认，继续执行"),
            ]
        )
    )
    graph = create_deep_agent(
        model=model,
        tools=[_ask_tool()],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-main"}}
    resume_value = {"approved": True, "values": {"choice": "a"}}

    token_supported = hitl_interrupt_supported.set(True)
    try:
        # 第一次执行：挂起，工具零副作用
        await _run(graph, {"messages": [HumanMessage("请确认")]}, config)
        state = await graph.aget_state(config)
        assert state.next, "图应在 ask_human interrupt 处挂起"
        assert recorder.created == [], "挂起前工具不应创建审批"

        # 编排层物化审批（无超时）
        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 1
        assert recorder.created[0]["metadata"]["mode"] == "interrupt"
        assert recorder.created[0]["ttl"] is None
        assert recorder.sse == ["approval-1"]
        # 重复物化（重放/重复挂起）不重复创建
        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 1

        # 恢复：Command(resume) 断点续跑
        final_state = await graph.ainvoke(Command(resume=resume_value), config)
    finally:
        hitl_interrupt_supported.reset(token_supported)

    assert len(recorder.created) == 1, "恢复重放不应重复创建审批"
    ask_results = [
        _tool_json(m.content)
        for m in final_state["messages"]
        if m.type == "tool" and m.content.strip().startswith("{")
    ]
    assert any(
        r.get("status") == "success" and r.get("values", {}).get("choice") == "a"
        for r in ask_results
    ), f"ask_human 应返回 resume 值: {ask_results}"
    assert "已确认" in final_state["messages"][-1].text


async def test_subagent_ask_human_suspend_and_resume(
    interrupt_mode: None, recorder: ApprovalRecorder
) -> None:
    sub_model = ScriptedModel(
        messages=iter(
            [
                _tool_call(
                    "ask_human",
                    {"message": "子代理需要确认", "choices": ["x", "y"]},
                    "call-sub-1",
                ),
                AIMessage(content="子代理已获得确认"),
            ]
        )
    )
    main_model = ScriptedModel(
        messages=iter(
            [
                _tool_call(
                    "task",
                    {"description": "去问用户", "subagent_type": "helper"},
                    "call-task-1",
                ),
                AIMessage(content="主代理收到子代理结果"),
            ]
        )
    )
    graph = create_deep_agent(
        model=main_model,
        tools=[],
        subagents=[
            {
                "name": "helper",
                "description": "向用户提问的子代理",
                "system_prompt": "你负责向用户提问。",
                "model": sub_model,
                "tools": [_ask_tool()],
            }
        ],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-sub"}}
    resume_value = {"approved": True, "values": {"choice": "y"}}

    token_supported = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("让子代理问我")]}, config)
        state = await graph.aget_state(config)
        assert state.next, "子代理中的 interrupt 应挂起整个运行"

        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 1
        assert recorder.created[0]["message"] == "子代理需要确认"

        final_state = await graph.ainvoke(Command(resume=resume_value), config)
    finally:
        hitl_interrupt_supported.reset(token_supported)

    assert len(recorder.created) == 1, "子代理重放不应重复创建审批"
    texts = [m.text for m in final_state["messages"] if hasattr(m, "text")]
    assert any("主代理收到子代理结果" in t for t in texts)


async def test_new_ask_after_resume_suspends_again(
    interrupt_mode: None, recorder: ApprovalRecorder
) -> None:
    """恢复后模型发起新的 ask_human：再次挂起、可再次物化与恢复。"""
    model = ScriptedModel(
        messages=iter(
            [
                _tool_call(
                    "ask_human",
                    {"message": "第一个问题", "choices": ["a"]},
                    "call-1",
                ),
                _tool_call(
                    "ask_human",
                    {"message": "第二个问题", "choices": ["c"]},
                    "call-2",
                ),
                AIMessage(content="两次都确认了"),
            ]
        )
    )
    graph = create_deep_agent(
        model=model,
        tools=[_ask_tool()],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-twice"}}

    token_supported = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("问两次")]}, config)
        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 1

        # 第一次恢复 → 第二次 ask_human 挂起
        await _run(graph, Command(resume={"approved": True, "values": {"choice": "a"}}), config)
        state = await graph.aget_state(config)
        assert state.next, "第二个 ask_human 应再次挂起"
        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 2
        assert recorder.created[1]["message"] == "第二个问题"

        final_state = await graph.ainvoke(Command(resume={"approved": False, "values": {}}), config)
    finally:
        hitl_interrupt_supported.reset(token_supported)

    assert len(recorder.created) == 2
    assert "两次都确认了" in final_state["messages"][-1].text
    results = [
        _tool_json(m.content)
        for m in final_state["messages"]
        if m.type == "tool" and m.content.strip().startswith("{")
    ]
    assert [r["status"] for r in results if "status" in r] == ["success", "rejected"]


async def test_same_message_interrupts_materialize_as_distinct_approvals(
    interrupt_mode: None, recorder: ApprovalRecorder
) -> None:
    snapshot = SimpleNamespace(
        tasks=(
            SimpleNamespace(
                interrupts=(
                    SimpleNamespace(
                        id="interrupt-a",
                        value={
                            "kind": "ask_human",
                            "message": "same",
                            "fields": [],
                            "tool_call_id": "call-a",
                        },
                    ),
                )
            ),
            SimpleNamespace(
                interrupts=(
                    SimpleNamespace(
                        id="interrupt-b",
                        value={
                            "kind": "ask_human",
                            "message": "same",
                            "fields": [],
                            "tool_call_id": "call-b",
                        },
                    ),
                )
            ),
        )
    )

    created = await materialize_ask_human_approvals(
        snapshot,
        session_id="session-1",
        run_id="run-1",
        trace_id="trace-1",
        user_id="user-1",
    )

    assert created == 2
    assert [item["metadata"]["interrupt_id"] for item in recorder.created] == [
        "interrupt-a",
        "interrupt-b",
    ]
    assert [item["metadata"]["tool_call_id"] for item in recorder.created] == [
        "call-a",
        "call-b",
    ]
    assert {item["metadata"]["trace_id"] for item in recorder.created} == {"trace-1"}


async def test_parallel_ask_human_interrupts_resume_by_id(
    interrupt_mode: None, recorder: ApprovalRecorder
) -> None:
    model = ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "ask_human",
                            "args": {"message": "same", "choices": ["a", "b"]},
                            "id": "call-a",
                            "type": "tool_call",
                        },
                        {
                            "name": "ask_human",
                            "args": {"message": "same", "choices": ["x", "y"]},
                            "id": "call-b",
                            "type": "tool_call",
                        },
                    ],
                ),
                AIMessage(content="两个回答都已收到"),
            ]
        )
    )
    graph = create_deep_agent(
        model=model,
        tools=[_ask_tool()],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-parallel"}}

    token_supported = hitl_interrupt_supported.set(True)
    try:
        await _run(graph, {"messages": [HumanMessage("并行问两个问题")]}, config)
        snapshot = await graph.aget_state(config)
        interrupts = hitl_mod.extract_ask_human_interrupts(snapshot)
        assert len(interrupts) == 2

        await _materialize(graph, config, recorder)
        assert len(recorder.created) == 2
        assert {item["metadata"]["tool_call_id"] for item in recorder.created} == {
            "call-a",
            "call-b",
        }

        first_id = interrupts[0]["interrupt_id"]
        second_id = interrupts[1]["interrupt_id"]
        await _run(
            graph,
            Command(resume={first_id: {"approved": True, "values": {"choice": "a"}}}),
            config,
        )
        after_first = await graph.aget_state(config)
        assert after_first.next, "另一个 interrupt 未回答时图必须继续挂起"

        final_state = await graph.ainvoke(
            Command(resume={second_id: {"approved": True, "values": {"choice": "y"}}}),
            config,
        )
    finally:
        hitl_interrupt_supported.reset(token_supported)

    assert "两个回答都已收到" in final_state["messages"][-1].text

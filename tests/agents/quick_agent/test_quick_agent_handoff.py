"""Quick and Search share one durable user turn while switching executors."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from src.agents.core.base import GraphBuilder
from src.agents.quick_agent.graph import QuickAgent
from src.agents.quick_agent.nodes import quick_agent_node


class RoutingModel:
    def __init__(self, *, delegate=True, tool_name="handoff_to_search"):
        self.delegate = delegate
        self.tool_name = tool_name
        self.tools = []
        self.messages = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages, **kwargs):
        self.messages = messages
        if self.delegate:
            return AIMessage(
                content="",
                tool_calls=[{"name": self.tool_name, "args": {}, "id": "route-1"}],
            )
        return AIMessage(content="你好")


class GraphModel(BaseChatModel):
    delegate: bool = True
    tool_name: str = "handoff_to_search"
    unavailable: bool = False

    @property
    def _llm_type(self):
        return "handoff-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        response = AIMessage(
            content="" if self.delegate else "已完成",
            tool_calls=(
                [{"name": self.tool_name, "args": {}, "id": "route-1"}] if self.delegate else []
            ),
            usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
        return ChatResult(generations=[ChatGeneration(message=response)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs: Any):
        if self.unavailable:
            import httpx

            raise httpx.ReadTimeout("Primary unavailable")
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": self.tool_name, "args": "{", "id": "route-1", "index": 0}
                ],
            )
        )
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": None, "args": "}", "id": None, "index": 0}],
                usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            )
        )


def patch_model(monkeypatch, model):
    async def get_model(**kwargs):
        return model

    monkeypatch.setattr("src.agents.quick_agent.nodes.LLMClient.get_model", get_model)


@pytest.mark.parametrize("tool_name", ["handoff_to_search", "execute", "write_file"])
async def test_handoff_preserves_history_without_writing_current_turn_twice(monkeypatch, tool_name):
    model = RoutingModel(tool_name=tool_name)
    patch_model(monkeypatch, model)
    checkpointer = MemorySaver()
    builder = GraphBuilder(QuickAgent().state_class)
    QuickAgent().build_graph(builder)
    graph = builder.compile(checkpointer=checkpointer)
    config = {
        "configurable": {
            "thread_id": "handoff-history",
            "allow_search_handoff": True,
            "agent_options": {"_resolved_fallback_model": None},
        }
    }
    await graph.aupdate_state(config, {"messages": [HumanMessage("预算一千元"), AIMessage("收到")]})
    result = await graph.ainvoke(
        {"input": "查一下现在有哪些选择", "session_id": "handoff-history"}, config
    )
    assert result["agent_handoff"]["agent_id"] == "search"
    assert [message.content for message in result["messages"]] == [
        "预算一千元",
        "收到",
        "查一下现在有哪些选择",
    ]
    assert result["messages"][-1].id == result["agent_handoff"]["message_id"]
    assert [message.content for message in model.messages[1:]] == [
        "预算一千元",
        "收到",
        "查一下现在有哪些选择",
    ]
    assert model.tools
    assert not any(getattr(message, "tool_calls", []) for message in result["messages"])

    # Search's real inner graph replaces the same ID instead of appending a duplicate.
    search = create_deep_agent(model=GraphModel(delegate=False), checkpointer=checkpointer)
    continued = await search.ainvoke(
        {
            "messages": [
                HumanMessage("查一下现在有哪些选择", id=result["agent_handoff"]["message_id"])
            ]
        },
        config,
    )
    assert sum(message.content == "查一下现在有哪些选择" for message in continued["messages"]) == 1
    assert [message.content for message in continued["messages"][:3]] == [
        "预算一千元",
        "收到",
        "查一下现在有哪些选择",
    ]


async def test_direct_answer_clears_previous_handoff(monkeypatch):
    patch_model(monkeypatch, RoutingModel(delegate=False))
    result = await quick_agent_node(
        {"input": "你好", "messages": [], "agent_handoff": "search"},
        {
            "configurable": {
                "allow_search_handoff": True,
                "agent_options": {"_resolved_fallback_model": None},
            }
        },
    )
    assert "agent_handoff" in result and result["agent_handoff"] is None
    assert [message.content for message in result["messages"]] == ["你好", "你好"]


async def test_unavailable_search_does_not_expose_handoff(monkeypatch):
    model = RoutingModel(delegate=False)
    patch_model(monkeypatch, model)
    result = await quick_agent_node(
        {"input": "你好", "messages": []},
        {"configurable": {"agent_options": {"_resolved_fallback_model": None}}},
    )
    assert not model.tools
    assert result["output"] == "你好"


@pytest.mark.parametrize("tool_name", ["handoff_to_search", "execute", "write_file"])
async def test_tool_response_cannot_handoff_without_search_access(monkeypatch, tool_name):
    from src.kernel.errors import AppError

    model = RoutingModel(tool_name=tool_name)
    patch_model(monkeypatch, model)
    with pytest.raises(AppError):
        await quick_agent_node(
            {"input": "生成报告", "messages": []},
            {"configurable": {"agent_options": {"_resolved_fallback_model": None}}},
        )
    assert not model.tools


@pytest.mark.parametrize("tool_name", ["handoff_to_search", "execute", "write_file"])
@pytest.mark.parametrize("use_fallback", [False, True])
async def test_real_stream_handoff_has_usage_but_no_early_done_or_goal_end(
    monkeypatch, tool_name, use_fallback
):
    from src.infra.writer.present import Presenter, PresenterConfig
    from src.kernel.config import settings

    model = GraphModel(tool_name=tool_name)
    get_model = AsyncMock(
        side_effect=[GraphModel(unavailable=True), model] if use_fallback else [model]
    )
    monkeypatch.setattr("src.agents.quick_agent.nodes.LLMClient.get_model", get_model)
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(
        "src.agents.quick_agent.nodes.resolve_model_image_url_mode", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("src.infra.task.manager.BackgroundTaskManager.check_interrupt", AsyncMock())
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt_fast", lambda _: False
    )
    monkeypatch.setattr(
        "src.infra.agent.events.processor.compute_usage_cost", AsyncMock(return_value=None)
    )
    agent = QuickAgent()
    builder = GraphBuilder(agent.state_class)
    agent.build_graph(builder)
    agent._graph = builder.compile(checkpointer=MemorySaver())
    agent._initialized = True
    presenter = Presenter(PresenterConfig(agent_id="quick", enable_storage=False))
    monkeypatch.setattr(presenter, "build_langsmith_metadata", AsyncMock(return_value={}))
    saved = []
    monkeypatch.setattr(presenter, "emit", AsyncMock(side_effect=saved.append))
    events = [
        event
        async for event in agent.stream(
            "核实最新信息",
            "handoff-stream",
            presenter=presenter,
            allow_search_handoff=True,
            agent_options={"_resolved_fallback_model": "fallback" if use_fallback else None},
            active_goal={"objective": "查证"},
        )
    ]
    assert [event["event"] for event in events] == ["metadata", "agent:handoff"]
    assert events[-1]["data"]["prior_usage"]["total_tokens"] == 12
    assert events[-1]["data"]["message_id"] == f"handoff-user:{presenter.run_id}"
    assert not any(event["event"] in {"done", "goal:end", "tool:args:chunk"} for event in saved)
    assert [
        event["data"]["total_tokens"] for event in saved if event["event"] == "token:usage"
    ] == [12]
    assert not agent._stream_tasks
    assert get_model.await_count == (2 if use_fallback else 1)

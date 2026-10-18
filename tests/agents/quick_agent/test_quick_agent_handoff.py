"""Quick and Search share one durable user turn while switching executors."""

from typing import Any
from unittest.mock import AsyncMock

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from src.agents.core.base import GraphBuilder
from src.agents.quick_agent.graph import QuickAgent
from src.agents.quick_agent.nodes import quick_agent_node


class RoutingModel:
    def __init__(self, *, delegate=True):
        self.delegate = delegate
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
                tool_calls=[{"name": "handoff_to_search", "args": {}, "id": "route-1"}],
            )
        return AIMessage(content="你好")


class GraphModel(BaseChatModel):
    delegate: bool = True

    @property
    def _llm_type(self):
        return "handoff-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        response = AIMessage(
            content="" if self.delegate else "已完成",
            tool_calls=(
                [{"name": "handoff_to_search", "args": {}, "id": "route-1"}]
                if self.delegate
                else []
            ),
            usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


def patch_model(monkeypatch, model):
    async def get_model(**kwargs):
        return model

    monkeypatch.setattr("src.agents.quick_agent.nodes.LLMClient.get_model", get_model)


async def test_handoff_preserves_history_without_writing_current_turn_twice(monkeypatch):
    model = RoutingModel()
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


async def test_real_stream_handoff_has_usage_but_no_early_done_or_goal_end(monkeypatch):
    from src.infra.writer.present import Presenter, PresenterConfig

    patch_model(monkeypatch, GraphModel())
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
            agent_options={"_resolved_fallback_model": None},
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

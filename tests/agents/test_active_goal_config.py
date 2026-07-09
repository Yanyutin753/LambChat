from __future__ import annotations

import asyncio
from typing import Any

import pytest

from plugins.system.agent_team.backend.runtime import graph as team_graph
from src.agents.fast_agent import graph as fast_graph
from src.agents.search_agent import graph as search_graph


class _DummyContext:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def setup(self) -> None:
        pass

    async def close(self) -> None:
        pass


class _DummyPresenter:
    run_id = "run-goal"
    trace_id = "trace-goal"
    langsmith_context: dict[str, Any] | None = None

    def metadata(self) -> dict[str, Any]:
        return {"event": "metadata", "data": {"run_id": self.run_id}}

    async def build_langsmith_metadata(
        self,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.langsmith_context = context
        return {"captured_context": context or {}}

    def error(self, message: str, error_type: str) -> dict[str, Any]:
        return {"event": "error", "data": {"message": message, "type": error_type}}

    def done(self) -> dict[str, Any]:
        return {"event": "done", "data": {"status": "completed"}}


class _CapturingGraph:
    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None

    async def ainvoke(self, _state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.config = config
        return {}


class _FutureGraph:
    def __init__(self) -> None:
        self.config: dict[str, Any] | None = None

    def ainvoke(self, _state: dict[str, Any], config: dict[str, Any]) -> asyncio.Future[dict]:
        self.config = config
        future = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(future.set_result, {})
        return future


async def _drain_stream(agent: Any, graph: _CapturingGraph) -> None:
    agent._initialized = True
    agent._graph = graph

    async for _event in agent._stream(
        "continue",
        "session-goal",
        user_id="user-goal",
        presenter=_DummyPresenter(),
        active_goal={"objective": "ship it", "rubric": "- done"},
    ):
        pass


async def _drain_stream_with_presenter(
    agent: Any,
    graph: _CapturingGraph,
    presenter: _DummyPresenter,
    **kwargs: Any,
) -> None:
    agent._initialized = True
    agent._graph = graph

    async for _event in agent._stream(
        "continue",
        "session-goal",
        user_id="user-goal",
        presenter=presenter,
        **kwargs,
    ):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "agent_cls", "context_name"),
    [
        (fast_graph, fast_graph.FastAgent, "FastAgentContext"),
        (search_graph, search_graph.SearchAgent, "SearchAgentContext"),
        (team_graph, team_graph.TeamAgent, "TeamAgentContext"),
    ],
)
async def test_agent_stream_passes_active_goal_to_node_config(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    agent_cls: Any,
    context_name: str,
) -> None:
    monkeypatch.setattr(module, context_name, _DummyContext)
    graph = _CapturingGraph()

    await _drain_stream(agent_cls(), graph)

    assert graph.config is not None
    assert graph.config["configurable"]["active_goal"] == {
        "objective": "ship it",
        "rubric": "- done",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "agent_cls", "context_name"),
    [
        (fast_graph, fast_graph.FastAgent, "FastAgentContext"),
        (search_graph, search_graph.SearchAgent, "SearchAgentContext"),
        (team_graph, team_graph.TeamAgent, "TeamAgentContext"),
    ],
)
async def test_agent_stream_accepts_future_returned_by_graph_ainvoke(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    agent_cls: Any,
    context_name: str,
) -> None:
    monkeypatch.setattr(module, context_name, _DummyContext)
    graph = _FutureGraph()

    await _drain_stream(agent_cls(), graph)

    assert graph.config is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "agent_cls", "context_name"),
    [
        (fast_graph, fast_graph.FastAgent, "FastAgentContext"),
        (search_graph, search_graph.SearchAgent, "SearchAgentContext"),
        (team_graph, team_graph.TeamAgent, "TeamAgentContext"),
    ],
)
async def test_agent_stream_passes_runtime_context_to_langsmith_metadata(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    agent_cls: Any,
    context_name: str,
) -> None:
    monkeypatch.setattr(module, context_name, _DummyContext)
    graph = _CapturingGraph()
    presenter = _DummyPresenter()

    await _drain_stream_with_presenter(
        agent_cls(),
        graph,
        presenter,
        agent_options={"model": "gpt-test", "temperature": 0.1},
        team_id="team-1",
        enabled_skills=["skill-a"],
        disabled_skills=["skill-b"],
        disabled_tools=["tool-a"],
        disabled_mcp_tools=["mcp-a"],
        persona_system_prompt="persona",
        attachments=[{"name": "brief.txt"}],
        active_goal={"objective": "finish"},
        recommendation_input="hello",
    )

    assert graph.config is not None
    metadata = graph.config["metadata"]
    captured = metadata["captured_context"]
    assert captured["agent_options"] == {"model": "gpt-test", "temperature": 0.1}
    assert captured["enabled_skills"] == ["skill-a"] or agent_cls is team_graph.TeamAgent
    assert captured["disabled_skills"] == ["skill-b"]
    assert captured["disabled_mcp_tools"] == ["mcp-a"]
    assert captured["persona_system_prompt"] == "persona"
    assert captured["attachments"] == [{"name": "brief.txt"}]
    assert captured["active_goal"] == {"objective": "finish"}
    assert captured["recommendation_input"] == "hello"
    if agent_cls is team_graph.TeamAgent:
        assert captured["team_id"] == "team-1"
    else:
        assert "team_id" not in captured

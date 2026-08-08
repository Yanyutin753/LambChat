from __future__ import annotations

from pathlib import Path

import pytest

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "agents"


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_deep_agent_nodes_restore_todo_middleware_for_main_and_subagents(
    agent_name: str,
) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

    assert "from langchain.agents.middleware import TodoListMiddleware" in source
    assert source.count("TodoListMiddleware()") == 2

    subagent_builder = source.index("def _build_subagent_middleware")
    main_stack = source.index("user_middleware =", subagent_builder)
    graph_creation = source.index("inner_graph = create_deep_agent", main_stack)

    assert "TodoListMiddleware()" in source[subagent_builder:main_stack]
    assert "TodoListMiddleware()" in source[main_stack:graph_creation]

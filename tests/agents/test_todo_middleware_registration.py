from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "agents"


def test_compact_todo_middleware_keeps_tool_and_state_without_default_prompt() -> None:
    spec = importlib.util.find_spec("src.agents.core.todo_middleware")
    assert spec is not None
    module = importlib.import_module("src.agents.core.todo_middleware")

    middleware = module.create_todo_middleware()

    assert middleware.system_prompt == ""
    assert [tool.name for tool in middleware.tools] == ["write_todos"]
    assert "todos" in middleware.state_schema.__annotations__


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_deep_agent_nodes_use_compact_todo_middleware_for_main_and_subagents(
    agent_name: str,
) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

    assert "from src.agents.core.todo_middleware import create_todo_middleware" in source
    assert source.count("create_todo_middleware()") == 2
    assert "TodoListMiddleware()" not in source

    subagent_builder = source.index("def _build_subagent_middleware")
    main_stack = source.index("user_middleware =", subagent_builder)
    graph_creation = source.index("inner_graph = create_deep_agent", main_stack)

    assert "create_todo_middleware()" in source[subagent_builder:main_stack]
    assert "create_todo_middleware()" in source[main_stack:graph_creation]

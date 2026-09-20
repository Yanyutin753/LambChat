from __future__ import annotations

from pathlib import Path

import pytest
from langchain.agents.middleware import TodoListMiddleware

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "agents"


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_deep_agent_nodes_register_todo_middleware(agent_name: str) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

    assert "from src.agents.core.todo_middleware import create_todo_middleware" in source
    assert "create_todo_middleware()" in source


def test_todo_middleware_factory_exposes_write_todos() -> None:
    from src.agents.core.todo_middleware import create_todo_middleware

    middleware = create_todo_middleware()

    assert isinstance(middleware, TodoListMiddleware)
    # system_prompt 非空：Todo 触发指引的唯一系统级通道就是本中间件
    # （见 test_prompt_policy_planning）。
    assert middleware.system_prompt.strip()
    assert [tool.name for tool in middleware.tools] == ["write_todos"]
    assert "todos" in middleware.state_schema.__annotations__
    assert "multi-step" in middleware.tool_description
    assert "at most once per model turn" in middleware.tool_description
    assert "replaces the entire list" in middleware.tool_description


def test_memory_compaction_does_not_register_todo_middleware() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src" / "infra" / "memory" / "compaction_agent.py"
    ).read_text()

    assert "TodoListMiddleware" not in source
    assert "create_todo_middleware" not in source

from __future__ import annotations

from pathlib import Path

import pytest

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "agents"


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_deep_agent_nodes_do_not_register_todo_middleware(agent_name: str) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

    assert "todo_middleware" not in source
    assert "create_todo_middleware" not in source
    assert "TodoListMiddleware" not in source

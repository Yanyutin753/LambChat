"""Resolved model headers and user-supplied options must never be dumped to logs."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative", ["search_agent/nodes.py", "search_agent/graph.py", "team_agent/graph.py"]
)
def test_agent_logs_never_dump_full_options(relative):
    path = Path(__file__).resolve().parents[3] / "src/agents" / relative
    calls = [
        node
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    ]
    offenders = [
        node.lineno
        for node in calls
        if any(
            isinstance(part, ast.Name) and part.id == "agent_options"
            for arg in node.args
            for part in ast.walk(arg)
        )
    ]
    assert offenders == [], f"Raw model options logged at {relative}:{offenders}"

import ast
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.parametrize("agent", ["search_agent", "team_agent"])
@pytest.mark.parametrize("failure_stage", ["close", "flush"])
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_actual_inner_cleanup_emits_usage_even_when_cleanup_fails(
    agent, failure_stage, error_type
):
    source = Path(__file__).parents[3] / "src" / "agents" / agent / "nodes.py"
    tree = ast.parse(source.read_text())
    cleanup = next(
        node.finalbody
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "subagent_sessions"
            and call.func.attr == "close"
            for stmt in node.finalbody
            for call in ast.walk(stmt)
        )
    )
    # Execute the production cleanup block with failed resources, without building a model graph.
    function = ast.AsyncFunctionDef(
        name="cleanup",
        args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=copy.deepcopy(cleanup),
        decorator_list=[],
        type_params=[],
    )
    namespace = {
        "asyncio": asyncio,
        "subagent_sessions": SimpleNamespace(close=AsyncMock()),
        "event_processor": SimpleNamespace(
            drain_activity_references=AsyncMock(), flush=AsyncMock()
        ),
        "emit_token_usage": AsyncMock(),
        "presenter": object(),
        "run_started_at": 0,
        "model_id": "model",
        "selected_model": "model",
    }
    target = (
        namespace["subagent_sessions"].close
        if failure_stage == "close"
        else namespace["event_processor"].flush
    )
    target.side_effect = error_type("interrupted cleanup")
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
            str(source),
            "exec",
        ),
        namespace,
    )
    with pytest.raises(error_type, match="interrupted cleanup"):
        await namespace["cleanup"]()
    namespace["emit_token_usage"].assert_awaited_once()

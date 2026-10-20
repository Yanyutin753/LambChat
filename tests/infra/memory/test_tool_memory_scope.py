"""Personal preferences must retain their documented cross-project default."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.memory import tools


@pytest.mark.parametrize(
    "requested,expected", [(None, "user"), ("user", "user"), ("project", "project")]
)
async def test_personal_preference_tool_scope_honors_default_and_explicit_override(
    monkeypatch, requested, expected
):
    backend = SimpleNamespace(retain=AsyncMock(return_value={"success": True}))
    monkeypatch.setattr(tools, "get_user_id_from_runtime", lambda runtime: "owner")
    monkeypatch.setattr(tools, "get_session_id_from_runtime", lambda runtime: "source-session")
    monkeypatch.setattr(tools, "user_memory_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(tools, "_get_backend", AsyncMock(return_value=backend))
    monkeypatch.setattr(
        "src.infra.memory.scope.resolve_session_project_id", AsyncMock(return_value="alpha")
    )

    result = json.loads(
        await tools.memory_retain.coroutine(
            content="Across all projects the user prefers concise Chinese explanations.",
            context="user_preference",
            scope=requested,
        )
    )

    assert result["success"] is True
    assert backend.retain.await_args.kwargs["scope"] == expected
    assert backend.retain.await_args.kwargs["source"] == "auto_retained"

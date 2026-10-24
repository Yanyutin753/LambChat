"""Resolved provider credentials must never become public session metadata."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from src.api.routes.chat_request_config import build_conversation_config
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.session import Session


def _options():
    return {
        "model_id": "allowed",
        "thinking": "medium",
        "_resolved_model_config": {"request_headers": {"Authorization": "provider-secret"}},
        "_resolved_fallback_model": "private",
        "_handoff_usage": {"internal": 1},
    }


def test_new_conversation_does_not_persist_internal_model_options():
    options = _options()
    original = deepcopy(options)
    result = build_conversation_config(
        "run", "search", AgentRequest(message="hi", agent_options=options), "en"
    )
    assert result["agent_options"] == {"model_id": "allowed", "thinking": "medium"}
    assert options == original


@pytest.mark.parametrize("mode", ["python", "json"])
def test_legacy_session_serialization_removes_internal_model_credentials(mode):
    metadata = {
        "agent_options": _options(),
        "project_id": "project",
        "checkpoints": [{"id": "checkpoint"}],
    }
    session = Session(id="s", metadata=deepcopy(metadata))
    result = session.model_dump(mode=mode)
    assert result["metadata"]["agent_options"] == {"model_id": "allowed", "thinking": "medium"}
    assert result["metadata"]["project_id"] == "project"
    assert session.metadata == metadata


async def test_startup_refuses_readiness_when_permission_migration_fails(monkeypatch):
    from src.api import main
    from src.infra.role.storage import RoleStorage

    failure = RuntimeError("migration unavailable")
    monkeypatch.setattr(RoleStorage, "init_default_roles", AsyncMock(side_effect=failure))
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    with pytest.raises(RuntimeError, match="migration unavailable"):
        async with main.lifespan(FastAPI()):
            pytest.fail("startup exposed readiness after failed permission migration")

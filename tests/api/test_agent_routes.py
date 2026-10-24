from __future__ import annotations

import pytest

from src.api.routes import agent as agent_routes


@pytest.mark.asyncio
async def test_list_agents_reads_roles_and_agent_access_in_batches(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.kernel.schemas.user import TokenPayload

    roles = [SimpleNamespace(id="r1", name="one"), SimpleNamespace(id="r2", name="two")]
    get_roles = AsyncMock(return_value=roles)
    get_access = AsyncMock(return_value={"r1": ["fast"], "r2": None})
    config = SimpleNamespace(
        get_user_preference=AsyncMock(return_value=None), get_role_agents_by_ids=get_access
    )
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage",
        lambda: SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(roles=["one", "two"]))
        ),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: SimpleNamespace(get_roles_by_names=get_roles),
    )
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: config)
    monkeypatch.setattr(
        "src.infra.agent.model_access.resolve_user_allowed_model_ids", AsyncMock(return_value=None)
    )
    filtered = AsyncMock(return_value=[{"id": "fast"}])
    monkeypatch.setattr(agent_routes.AgentFactory, "get_filtered_agents", filtered)
    response = await agent_routes.list_agents(TokenPayload(sub="u", username="u", roles=[]))
    assert response["agents"] == [{"id": "fast"}]
    get_roles.assert_awaited_once_with(["one", "two"])
    get_access.assert_awaited_once_with(["r1", "r2"])
    assert filtered.await_args.kwargs["role_agent_map"] == {"r1": ["fast"], "r2": None}


def test_bounded_role_names_preserves_order_and_caps_large_role_lists() -> None:
    roles = [f"role-{index}" for index in range(agent_routes.AGENT_ROLE_LOOKUP_LIMIT + 25)]

    bounded = agent_routes._bounded_role_names(roles)

    assert bounded == [f"role-{index}" for index in range(agent_routes.AGENT_ROLE_LOOKUP_LIMIT)]


def test_format_agent_sse_event_drops_oversized_json_payload() -> None:
    event = {
        "event": "message:chunk",
        "data": {"content": "x" * (agent_routes.AGENT_SSE_DATA_MAX_BYTES + 1)},
    }

    formatted = agent_routes._format_agent_sse_event(event)

    assert "event: error" in formatted
    assert "event_payload_too_large" in formatted
    assert len(formatted.encode("utf-8")) < 1024


@pytest.mark.asyncio
async def test_list_tools_offloads_agent_discovery_for_unknown_agent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agents as agents_module
    from src.agents.core.base import _AGENT_REGISTRY

    calls: list[str] = []

    def fake_discover_agents() -> None:
        return None

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_routes.settings, "ENABLE_MCP", False, raising=False)
    monkeypatch.setattr(agents_module, "discover_agents", fake_discover_agents)
    monkeypatch.setattr(agent_routes, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.delitem(_AGENT_REGISTRY, "missing-agent", raising=False)

    response = await agent_routes.list_tools(
        user=type("User", (), {"sub": "user-1"})(),
        agent_id="missing-agent",
    )

    assert response.count == len(response.tools)
    assert calls == ["fake_discover_agents"]


@pytest.mark.parametrize("path", ["/search/chat", "/search/stream"])
async def test_direct_agent_routes_are_retired(path, monkeypatch):
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    get_agent = AsyncMock()
    monkeypatch.setattr(agent_routes.AgentFactory, "get", get_agent)
    app = FastAPI()
    app.include_router(agent_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"message": "hello", "session_id": "other"})
    assert response.status_code == 404
    get_agent.assert_not_awaited()

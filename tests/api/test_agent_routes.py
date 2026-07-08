from __future__ import annotations

import asyncio

import pytest

from src.api.routes import agent as agent_routes
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.mcp import MCPToolInfo


@pytest.mark.asyncio
async def test_gather_limited_caps_concurrent_agent_route_work() -> None:
    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def _work(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return value

    task = asyncio.create_task(
        agent_routes._gather_limited([lambda i=i: _work(i) for i in range(5)], limit=2)
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    assert await task == [0, 1, 2, 3, 4]


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


@pytest.mark.asyncio
async def test_list_tools_includes_internal_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    async def fake_resolve_user_mcp_access(user_id: str):
        assert user_id == "user-1"
        return ["user"], False

    async def fake_get_internal_tool_infos(**kwargs):
        calls.append(kwargs)
        return [
            MCPToolInfo(
                name="demo_internal_tool",
                description="Run an internal operation",
                parameters=[
                    {
                        "name": "target_id",
                        "type": "string",
                        "description": "Target id",
                        "required": True,
                    }
                ],
            ),
            MCPToolInfo(
                name="demo_internal_debug",
                description="Inspect async operation debug events",
                parameters=[
                    {
                        "name": "target_id",
                        "type": "string",
                        "description": "Target id",
                        "required": True,
                    },
                    {
                        "name": "run_id",
                        "type": "string",
                        "description": "Run id",
                        "required": True,
                    },
                ],
            )
        ]

    monkeypatch.setattr(agent_routes.settings, "ENABLE_MCP", False, raising=False)
    monkeypatch.setattr(
        "src.infra.mcp.quota.resolve_user_mcp_access",
        fake_resolve_user_mcp_access,
    )
    monkeypatch.setattr(
        "src.infra.tool.internal_registry.get_internal_tool_infos",
        fake_get_internal_tool_infos,
    )

    response = await agent_routes.list_tools(
        user=type(
            "User",
            (),
            {"sub": "user-1", "roles": ["user"], "permissions": ["demo:read", "demo:run"]},
        )(),
    )

    assert calls == [{"user_id": "user-1", "user_roles": ["user"], "is_admin": False}]
    assert response.count == len(response.tools)
    run_tool = next(tool for tool in response.tools if tool.name == "demo_internal_tool")
    assert run_tool.category == "internal"
    assert run_tool.server == "lambchat_internal"
    assert run_tool.description == "Run an internal operation"
    assert run_tool.parameters[0].name == "target_id"
    assert run_tool.parameters[0].required is True
    debug_tool = next(tool for tool in response.tools if tool.name == "demo_internal_debug")
    assert debug_tool.category == "internal"
    assert debug_tool.server == "lambchat_internal"
    assert "async operation" in debug_tool.description
    assert {param.name for param in debug_tool.parameters} == {"target_id", "run_id"}


@pytest.mark.asyncio
async def test_agent_stream_offloads_sse_json_formatting(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _Agent:
        async def stream(self, *args, **kwargs):
            yield {
                "event": "message:chunk",
                "data": {"content": "hello", "payload": ["x" * 1024]},
            }

    async def fake_get(agent_id: str):
        return _Agent()

    async def fake_validate(agent_options, user):
        return None

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_routes.AgentFactory, "get", fake_get)
    monkeypatch.setattr(agent_routes, "validate_agent_model_access", fake_validate)
    monkeypatch.setattr(agent_routes, "run_blocking_io", fake_run_blocking_io)

    response = await agent_routes.chat_stream(
        "search",
        AgentRequest(message="hi"),
        request=type("Request", (), {"base_url": "http://testserver/"})(),
        user=type("User", (), {"sub": "user-1"})(),
    )
    chunk = await response.body_iterator.__anext__()

    assert "event: message:chunk" in chunk
    assert calls == ["_format_agent_sse_event"]

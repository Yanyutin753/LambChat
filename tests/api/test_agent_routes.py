from __future__ import annotations

import asyncio

import pytest

from src.api.routes import agent as agent_routes
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.mcp import MCPToolInfo
from src.kernel.schemas.user import TokenPayload


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
async def test_list_tools_includes_internal_workflow_tools(
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
                name="workflow_run",
                description="Run a workflow",
                parameters=[
                    {
                        "name": "workflow_id",
                        "type": "string",
                        "description": "Workflow id",
                        "required": True,
                    }
                ],
            ),
            MCPToolInfo(
                name="workflow_get_run",
                description="Inspect async/stream workflow run debug events",
                parameters=[
                    {
                        "name": "workflow_id",
                        "type": "string",
                        "description": "Workflow id",
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
            {"sub": "user-1", "roles": ["user"], "permissions": ["workflow:read", "workflow:run"]},
        )(),
    )

    assert calls == [{"user_id": "user-1", "user_roles": ["user"], "is_admin": False}]
    assert response.count == len(response.tools)
    workflow_tool = next(tool for tool in response.tools if tool.name == "workflow_run")
    assert workflow_tool.category == "internal"
    assert workflow_tool.server == "lambchat_internal"
    assert workflow_tool.description == "Run a workflow"
    assert workflow_tool.parameters[0].name == "workflow_id"
    assert workflow_tool.parameters[0].required is True
    get_run_tool = next(tool for tool in response.tools if tool.name == "workflow_get_run")
    assert get_run_tool.category == "internal"
    assert get_run_tool.server == "lambchat_internal"
    assert "async/stream" in get_run_tool.description
    assert {param.name for param in get_run_tool.parameters} == {"workflow_id", "run_id"}


@pytest.mark.asyncio
async def test_list_tools_respects_workflow_plugin_runtime_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry
    from src.kernel.extensions import (
        WORKFLOW_PLUGIN_ID,
        PluginRuntime,
        build_workflow_plugin_manifest,
    )

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def fake_resolve_user_mcp_access(user_id: str):
        assert user_id == "user-1"
        return ["user"], False

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    user = TokenPayload(
        sub="user-1",
        username="user-1",
        roles=["user"],
        permissions=["workflow:read", "workflow:run"],
    )

    monkeypatch.setattr(agent_routes.settings, "ENABLE_MCP", False, raising=False)
    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)
    monkeypatch.setattr(
        "src.infra.mcp.quota.resolve_user_mcp_access",
        fake_resolve_user_mcp_access,
    )

    disabled_response = await agent_routes.list_tools(user=user)
    disabled_names = {tool.name for tool in disabled_response.tools}

    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)
    enabled_response = await agent_routes.list_tools(user=user)
    enabled_tools = {tool.name: tool for tool in enabled_response.tools}

    assert "workflow_get_run" not in disabled_names
    assert {
        "workflow_run",
        "workflow_list",
        "workflow_get_schema",
        "workflow_get_run",
        "workflow_resume",
    } <= set(enabled_tools)
    assert enabled_tools["workflow_get_run"].category == "internal"
    assert enabled_tools["workflow_get_run"].server == "lambchat_internal"
    assert "debug events" in enabled_tools["workflow_get_run"].description
    assert enabled_tools["workflow_resume"].category == "internal"
    assert enabled_tools["workflow_resume"].server == "lambchat_internal"


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

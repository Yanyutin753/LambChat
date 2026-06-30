from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import mcp as mcp_route
from src.kernel.schemas.mcp import MCPServerResponse, MCPToolInfo, MCPTransport
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["mcp:read"],
    )


def _fake_admin() -> TokenPayload:
    return TokenPayload(
        sub="admin-1",
        username="admin",
        roles=["admin"],
        permissions=["mcp:read", "mcp:admin"],
    )


def _fake_mcp_import_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["mcp:read", "mcp:write_sse"],
    )


@pytest.mark.asyncio
async def test_list_mcp_servers_returns_paginated_response() -> None:
    class _FakeStorage:
        async def get_visible_servers(self, user_id: str, is_admin: bool, user_roles, limit=None):
            assert user_id == "user-1"
            assert is_admin is False
            assert user_roles == ["user"]
            assert limit == 5
            return [
                MCPServerResponse(
                    name=f"server-{i}",
                    transport=MCPTransport.SSE,
                    enabled=True,
                    url=f"https://example.com/{i}",
                    headers=None,
                    command=None,
                    env_keys=None,
                    is_system=False,
                    can_edit=True,
                    allowed_roles=[],
                    role_quotas={},
                    created_at=None,
                    updated_at=None,
                )
                for i in range(5)
            ]

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/mcp/?skip=2&limit=2&q=server")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert payload["skip"] == 2
    assert payload["limit"] == 2
    assert [server["name"] for server in payload["servers"]] == ["server-2", "server-3"]


@pytest.mark.asyncio
async def test_admin_mcp_list_includes_internal_server() -> None:
    class _FakeStorage:
        async def get_visible_servers(self, user_id: str, is_admin: bool, user_roles, limit=None):
            assert is_admin is True
            assert limit == 21
            return []

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/admin/mcp/")

    assert response.status_code == 200
    payload = response.json()
    assert any(server["name"] == "lambchat_internal" for server in payload["servers"])


@pytest.mark.asyncio
async def test_admin_internal_tool_discovery_uses_internal_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_internal_tool_infos(*args, **kwargs):
        return [
            MCPToolInfo(
                name="image_generate",
                description="Generate images",
                parameters=[],
                policy_configured=True,
            )
        ]

    monkeypatch.setattr(
        "src.infra.tool.internal_registry.get_internal_tool_infos",
        fake_get_internal_tool_infos,
    )

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/admin/mcp/lambchat_internal/tools")

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_name"] == "lambchat_internal"
    assert payload["count"] == 1
    assert payload["tools"][0]["name"] == "image_generate"


@pytest.mark.asyncio
async def test_admin_internal_tool_invoke_runs_allowlisted_workflow_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _FakeTool:
        name = "workflow_run"

        async def _arun(self, *args, config=None, **kwargs):
            calls.append({"args": args, "config": config, "kwargs": kwargs})
            runtime = kwargs.pop("runtime")
            user_id = runtime.config["configurable"]["context"].user_id
            return json.dumps(
                {
                    "plugin_id": "workflow",
                    "workflow_id": kwargs["workflow_id"],
                    "run_id": "wfr-tool",
                    "status": "succeeded",
                    "user_id": user_id,
                }
            )

    async def fake_get_internal_tools_for_user(*args, **kwargs):
        assert kwargs == {"user_id": "admin-1", "user_roles": ["admin"], "is_admin": True}
        return [_FakeTool()]

    monkeypatch.setattr(
        "src.infra.tool.internal_registry.get_internal_tools_for_user",
        fake_get_internal_tools_for_user,
    )

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/mcp/lambchat_internal/tools/workflow_run/invoke",
            json={"arguments": {"workflow_id": "wf-1", "input": {"message": "hi"}}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "server_name": "lambchat_internal",
        "tool_name": "workflow_run",
        "result": {
            "plugin_id": "workflow",
            "workflow_id": "wf-1",
            "run_id": "wfr-tool",
            "status": "succeeded",
            "user_id": "admin-1",
        },
    }
    assert calls[0]["config"] == {}
    assert calls[0]["kwargs"]["workflow_id"] == "wf-1"
    assert calls[0]["kwargs"]["input"] == {"message": "hi"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "raw_result", "expected_result"),
    [
        (
            "workflow_list",
            {"scope": "published"},
            {
                "plugin_id": "workflow",
                "scope": "published",
                "workflows": [{"workflow_id": "wf-1", "status": "published"}],
            },
            {
                "plugin_id": "workflow",
                "scope": "published",
                "workflows": [{"workflow_id": "wf-1", "status": "published"}],
            },
        ),
        (
            "workflow_get_schema",
            {"workflow_id": "wf-1", "version_id": "wfv-1"},
            json.dumps(
                {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "input_schema": {"type": "object", "properties": {"items": {"type": "array"}}},
                }
            ),
            {
                "plugin_id": "workflow",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "input_schema": {"type": "object", "properties": {"items": {"type": "array"}}},
            },
        ),
        (
            "workflow_get_run",
            {"workflow_id": "wf-1", "run_id": "wfr-1"},
            json.dumps(
                {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "run_id": "wfr-1",
                    "status": "running",
                    "events": [{"event_type": "run_queued"}],
                }
            ),
            {
                "plugin_id": "workflow",
                "workflow_id": "wf-1",
                "run_id": "wfr-1",
                "status": "running",
                "events": [{"event_type": "run_queued"}],
            },
        ),
    ],
)
async def test_admin_internal_tool_invoke_runs_allowlisted_workflow_read_tools(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict,
    raw_result,
    expected_result: dict,
) -> None:
    calls: list[dict] = []

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

        async def _arun(self, *args, config=None, **kwargs):
            calls.append({"args": args, "config": config, "kwargs": kwargs})
            return raw_result

    async def fake_get_internal_tools_for_user(*args, **kwargs):
        assert kwargs == {"user_id": "admin-1", "user_roles": ["admin"], "is_admin": True}
        return [_FakeTool(tool_name)]

    monkeypatch.setattr(
        "src.infra.tool.internal_registry.get_internal_tools_for_user",
        fake_get_internal_tools_for_user,
    )

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/admin/mcp/lambchat_internal/tools/{tool_name}/invoke",
            json={"arguments": arguments},
        )

    assert response.status_code == 200
    assert response.json() == {
        "server_name": "lambchat_internal",
        "tool_name": tool_name,
        "result": expected_result,
    }
    assert calls[0]["config"] == {}
    called_kwargs = dict(calls[0]["kwargs"])
    runtime = called_kwargs.pop("runtime")
    assert called_kwargs == arguments
    assert runtime.config["configurable"]["context"].user_id == "admin-1"


@pytest.mark.asyncio
async def test_admin_internal_tool_invoke_rejects_non_allowlisted_tool() -> None:
    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/mcp/lambchat_internal/tools/image_generate/invoke",
            json={"arguments": {}},
        )

    assert response.status_code == 403
    assert "cannot be invoked" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_internal_tool_invoke_rejects_external_server() -> None:
    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/mcp/external-server/tools/workflow_run/invoke",
            json={"arguments": {"workflow_id": "wf-1"}},
        )

    assert response.status_code == 404
    assert "external-server" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_internal_tool_invoke_respects_workflow_runtime_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry
    from src.kernel.extensions import PluginRuntime, build_workflow_plugin_manifest

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    runtime = PluginRuntime([build_workflow_plugin_manifest()])

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: object()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke",
            json={"arguments": {"workflow_id": "wf-1", "run_id": "wfr-1"}},
        )

    assert response.status_code == 404
    assert "workflow_get_run" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_mcp_servers_rejects_oversized_payload_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_route, "MCP_IMPORT_MAX_SERVERS", 2, raising=False)

    class _FakeStorage:
        async def import_servers(self, *args, **kwargs):
            raise AssertionError("oversized import should be rejected before storage")

    app = FastAPI()
    app.include_router(mcp_route.router, prefix="/api/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_mcp_import_user
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    payload = {
        "servers": {
            f"server-{i}": {
                "transport": "sse",
                "url": f"https://example.com/{i}",
            }
            for i in range(3)
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/mcp/import", json=payload)

    assert response.status_code == 413
    assert "too many MCP servers" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_toggle_tool_returns_bad_request_for_disabled_tool_overflow() -> None:
    class _FakeStorage:
        async def set_system_tool_disabled(self, *_args, **_kwargs):
            raise ValueError("Too many disabled tools: maximum 100 allowed.")

    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/admin/mcp/server-1/tools/tool-101",
            json={"enabled": False},
        )

    assert response.status_code == 400
    assert "maximum 100" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_update_tool_policy_accepts_inline_exposure() -> None:
    class _FakeStorage:
        def __init__(self) -> None:
            self.calls = []

        async def get_system_server(self, name: str):
            assert name == "server-1"
            return object()

        async def set_tool_policy(self, **kwargs):
            self.calls.append(kwargs)
            from src.kernel.schemas.mcp import MCPToolPolicy

            return MCPToolPolicy(
                server_name=kwargs["server_name"],
                tool_name=kwargs["tool_name"],
                disabled=kwargs["disabled"],
                inline_exposure=kwargs["inline_exposure"],
            )

    storage = _FakeStorage()
    app = FastAPI()
    app.include_router(mcp_route.admin_router, prefix="/api/admin/mcp")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_admin
    app.dependency_overrides[mcp_route.get_mcp_storage] = lambda: storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/admin/mcp/server-1/tools/extract/policy",
            json={"disabled": False, "inline_exposure": True},
        )

    assert response.status_code == 200
    assert response.json()["inline_exposure"] is True
    assert storage.calls == [
        {
            "server_name": "server-1",
            "tool_name": "extract",
            "disabled": False,
            "inline_exposure": True,
            "allowed_roles": None,
            "role_quotas": None,
            "updated_by": "admin-1",
        }
    ]

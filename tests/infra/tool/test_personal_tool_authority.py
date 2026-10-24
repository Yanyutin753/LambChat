"""Tool authorization uses current roles and cannot borrow chat permissions."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.tool import env_var_tool, team_tool
from src.kernel.schemas.user import TokenPayload


async def test_environment_write_denied_before_storage(monkeypatch):
    runtime = SimpleNamespace(config={"configurable": {"user_id": "owner"}})
    monkeypatch.setattr(env_var_tool, "_get_user_id", lambda _: "owner")
    with patch("src.infra.user.storage.UserStorage.get_by_id", AsyncMock(return_value=None)):
        with patch.object(env_var_tool, "EnvVarStorage") as storage:
            result = json.loads(await env_var_tool.env_var_set.coroutine("KEY", "secret", runtime))
    assert "Permission denied" in result["error"]
    storage.assert_not_called()


def test_chat_write_does_not_authorize_team_or_persona_access():
    user = TokenPayload(sub="owner", username="owner", permissions=["chat:write"])
    assert not team_tool._can_create_team(user)
    assert not team_tool._can_read_personas(user)


async def test_deleted_or_inactive_user_cannot_execute_personal_tools(monkeypatch):
    user = SimpleNamespace(id="owner", username="owner", roles=["writer"], is_active=False)
    with patch("src.infra.user.storage.UserStorage.get_by_id", AsyncMock(return_value=user)):
        with patch("src.infra.role.storage.RoleStorage.get_by_names", AsyncMock(return_value=[])):
            assert await team_tool._resolve_user("owner") is None


async def test_current_role_revocation_affects_tool_discovery_and_execution(monkeypatch):
    from langchain_core.tools import StructuredTool

    from src.infra.auth import tool_authority
    from src.infra.tool import internal_registry
    from src.infra.tool.mcp_client import MCPToolWithRetry

    user = SimpleNamespace(id="owner", username="owner", roles=["writer"], is_active=True)
    roles = [SimpleNamespace(name="writer", permissions=["envvar:write"])]
    invoke = AsyncMock(return_value="saved")

    async def save() -> str:
        return await invoke()

    tool = StructuredTool.from_function(coroutine=save, name="env_var_set", description="Save")
    monkeypatch.setattr(tool_authority.UserStorage, "get_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        tool_authority.RoleStorage, "get_by_names", AsyncMock(side_effect=lambda _: roles)
    )
    monkeypatch.setattr(internal_registry, "build_internal_tools", lambda: [tool])
    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", AsyncMock(return_value={}))
    direct, deferred = await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="owner", user_roles=["stale-admin"], is_admin=True
    )
    assert len(direct + deferred) == 1
    wrapped = (direct + deferred)[0]
    assert isinstance(wrapped, MCPToolWithRetry)
    roles.clear()
    result = json.loads(await wrapped.ainvoke({}))
    assert "Permission denied" in result["error"]
    invoke.assert_not_awaited()
    assert await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="owner", user_roles=["stale-admin"], is_admin=True
    ) == ([], [])


@pytest.mark.parametrize(
    "tool_name,permission,kwargs",
    [
        ("memory_retain", "memory:write", {"content": "remember"}),
        ("memory_recall", "memory:read", {"query": "search"}),
        ("memory_delete", "memory:delete", {"memory_id": "memory-1"}),
    ],
)
async def test_memory_tools_deny_before_backend(monkeypatch, tool_name, permission, kwargs):
    from src.infra.memory import tools

    monkeypatch.setattr(tools, "get_user_id_from_runtime", lambda _: "owner")
    monkeypatch.setattr(tools, "has_tool_permission", AsyncMock(return_value=False))
    backend = AsyncMock()
    monkeypatch.setattr(tools, "_get_backend", backend)
    result = json.loads(await getattr(tools, tool_name).coroutine(**kwargs))
    assert permission in result["error"]
    backend.assert_not_awaited()


async def test_environment_ownership_comes_from_runtime_not_arguments(monkeypatch):
    monkeypatch.setattr(env_var_tool, "_get_user_id", lambda _: "owner")
    monkeypatch.setattr(env_var_tool, "has_tool_permission", AsyncMock(return_value=True))
    variable = SimpleNamespace(key="KEY", created_at=None, updated_at=None)
    storage = SimpleNamespace(set_var=AsyncMock(return_value=variable))
    monkeypatch.setattr(env_var_tool, "EnvVarStorage", lambda: storage)
    monkeypatch.setattr(env_var_tool, "sync_envvar_change", AsyncMock())
    monkeypatch.setattr(env_var_tool, "get_backend_from_runtime", lambda _: None)
    result = json.loads(await env_var_tool.env_var_set.coroutine("KEY", "secret", None))
    assert result["success"]
    storage.set_var.assert_awaited_once_with("owner", "KEY", "secret")


def test_team_hydration_does_not_expose_another_owners_private_persona():
    from src.infra.team.manager import TeamManager
    from src.kernel.schemas.team import TeamMemberResponse, TeamResponse

    team = TeamResponse(
        id="team",
        name="Own team",
        owner_user_id="owner",
        members=[
            TeamMemberResponse(
                member_id="member", persona_preset_id="private", role_name="Original"
            )
        ],
    )
    hydrated = TeamManager._hydrate_team_from_personas(
        team, {"private": {"scope": "user", "owner_user_id": "other", "name": "Private name"}}
    )
    assert hydrated.members[0].role_name == "Original"


def test_internal_policy_disable_is_not_bypassed_by_configuration_admin():
    from src.infra.tool.internal_registry import _is_tool_allowed
    from src.kernel.schemas.mcp import MCPToolPolicy

    assert not _is_tool_allowed(
        policy=MCPToolPolicy(disabled=True), user_roles=["admin"], is_admin=True
    )


async def test_bound_external_tool_rechecks_current_server_role_access(monkeypatch):
    from langchain_core.tools import StructuredTool

    from src.infra.auth import tool_authority
    from src.infra.mcp.storage import MCPStorage
    from src.infra.tool.mcp_client import MCPToolWithRetry
    from src.kernel.schemas.mcp import MCPTransport, SystemMCPServer

    original = AsyncMock(return_value="must not run")

    async def action() -> str:
        return await original()

    tool = StructuredTool.from_function(
        coroutine=action, name="server:action", description="Action"
    )
    wrapped = MCPToolWithRetry(tool, user_id="owner", server_name="server", is_admin=True)
    monkeypatch.setattr(
        tool_authority,
        "resolve_tool_user",
        AsyncMock(
            return_value=TokenPayload(
                sub="owner",
                username="owner",
                roles=["reader"],
                permissions=["mcp:read", "mcp:admin"],
            )
        ),
    )
    monkeypatch.setattr(MCPStorage, "get_user_server", AsyncMock(return_value=None))
    monkeypatch.setattr(
        MCPStorage,
        "get_system_server",
        AsyncMock(
            return_value=SystemMCPServer(
                name="server", transport=MCPTransport.SSE, allowed_roles=["writer"]
            )
        ),
    )
    result = json.loads(await wrapped.ainvoke({}))
    assert "Permission denied" in result["error"]
    original.assert_not_awaited()

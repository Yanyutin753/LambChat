from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import ToolMessage

from src.infra.agent.middleware import sandbox_confirm
from src.kernel.schemas.model import ModelConfig, mask_api_key
from src.kernel.schemas.user import TokenPayload


def test_model_reader_never_receives_custom_header_secrets():
    model = ModelConfig(
        value="model", label="Model", request_headers={"Custom-Key": "private-secret"}
    )
    public = mask_api_key(model)
    assert public.request_headers == {"Custom-Key": "********"}
    assert model.request_headers == {"Custom-Key": "private-secret"}


@pytest.mark.asyncio
async def test_sandbox_tool_denied_before_confirmation_and_execution(monkeypatch):
    monkeypatch.setattr(
        sandbox_confirm, "has_tool_permission", AsyncMock(return_value=False), raising=False
    )
    policy = AsyncMock(return_value="none")
    middleware = sandbox_confirm.SandboxConfirmMiddleware(user_id="owner", policy_resolver=policy)
    handler = AsyncMock(return_value=ToolMessage(content="executed", tool_call_id="call"))
    request = SimpleNamespace(
        tool_call={"id": "call", "name": "execute", "args": {"command": "echo secret"}}, state={}
    )
    result = await middleware.awrap_tool_call(request, handler)
    assert result.status == "error"
    handler.assert_not_awaited()
    policy.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_agent_execution_requires_current_assignment(monkeypatch):
    from src.infra.agent import access

    user = TokenPayload(sub="u", username="u", roles=["reader"], permissions=["chat:write"])
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: SimpleNamespace(
            get_roles_by_names=AsyncMock(return_value=[SimpleNamespace(id="r", name="reader")])
        ),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: SimpleNamespace(get_role_agents_by_ids=AsyncMock(return_value={"r": []})),
    )
    monkeypatch.setattr(
        "src.agents.core.base.AgentFactory.get_filtered_agents", AsyncMock(return_value=[])
    )
    from src.kernel.errors import AppError

    with pytest.raises(AppError):
        await access.validate_user_agent_access("search", user)


@pytest.mark.asyncio
async def test_denied_sandbox_creation_has_no_provider_side_effect(monkeypatch):
    from src.infra.backend.lazy_sandbox import LazySandboxBackend
    from src.kernel.errors import AppError

    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=False)
    )
    factory = AsyncMock()
    backend = LazySandboxBackend(
        session_id="s", user_id="u", presenter=SimpleNamespace(), manager_factory=factory
    )
    with pytest.raises(AppError):
        await backend._ensure_ready()
    factory.assert_not_called()


@pytest.mark.parametrize("agent", ["search_agent", "team_agent"])
def test_main_and_persistent_children_share_sandbox_authority_factory(agent):
    import ast
    from pathlib import Path

    tree = ast.parse(Path(f"src/agents/{agent}/nodes.py").read_text())
    child = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_subagent_middleware"
    )

    def calls(node):
        return [
            item
            for item in ast.walk(node)
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "create_sandbox_confirm_middleware"
        ]

    assert calls(child), "Persistent child tools must retain the same permission/confirmation gate"
    assert len(calls(tree)) == 2, "The main and child stacks must both install the gate"


async def test_shared_sandbox_factory_keeps_local_machine_policy(monkeypatch):
    from src.infra.backend.local import WorkspaceAliasBackend

    lookup = AsyncMock(return_value="all")
    monkeypatch.setattr(sandbox_confirm, "_lookup_confirm_policy", lookup)
    local = object.__new__(WorkspaceAliasBackend)
    gate = sandbox_confirm.create_sandbox_confirm_middleware("owner", local, "selected-machine")
    assert await gate._policy_resolver() == "all"
    lookup.assert_awaited_once_with("owner", "selected-machine")


async def test_shared_sandbox_factory_uses_cloud_policy_for_cloud_backend(monkeypatch):
    lookup = AsyncMock(return_value="commands")
    monkeypatch.setattr(sandbox_confirm, "_lookup_cloud_confirm_policy", lookup)
    gate = sandbox_confirm.create_sandbox_confirm_middleware("owner", object(), "local-machine")
    assert await gate._policy_resolver() == "commands"
    lookup.assert_awaited_once_with("owner")

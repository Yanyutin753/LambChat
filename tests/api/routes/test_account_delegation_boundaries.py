"""Account and role grants cannot turn routine administration into escalation."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import role as role_routes
from src.api.routes import user as user_routes
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.role import Role
from src.kernel.schemas.user import TokenPayload, User


@pytest.fixture
def boundary_app(monkeypatch):
    actor = TokenPayload(sub="operator", username="operator", permissions=["user:write"])
    target = User(id="target", username="target", email="target@example.com", roles=["member"])
    roles = {
        "member": Role(id="member-id", name="member", permissions=["chat:write"]),
        "admin": Role(id="admin-id", name="admin", permissions=["user:write"]),
        "operator": Role(id="operator-id", name="operator", permissions=["chat:write"]),
    }
    saved = []
    other_admin = {"exists": False}
    model_scopes = {"member-id": [], "operator-id": [], "admin-id": []}
    agent_scopes = {"member-id": [], "operator-id": [], "admin-id": []}

    class Users:
        async def get_user(self, user_id):
            return target.model_copy(update={"id": user_id})

        async def update_user(self, user_id, data):
            saved.append(data.model_dump(exclude_unset=True))
            return target.model_copy(update=data.model_dump(exclude_unset=True))

        async def register(self, data, **options):
            assert options == {"assign_default_role": False}
            saved.append(data.model_dump())
            return target

        async def delete_user(self, user_id):
            saved.append({"deleted": user_id})
            return True

    class Roles:
        async def list_roles(self, *args):
            return list(roles.values())

        async def count_roles(self, *args):
            return len(roles)

        async def get_roles_by_names(self, names):
            return [roles[name] for name in names if name in roles]

        async def get_role(self, role_id):
            return next((role for role in roles.values() if role.id == role_id), None)

        async def get_role_by_name(self, name):
            return roles.get(name)

        async def update_role(self, role_id, data):
            saved.append(data.model_dump(exclude_unset=True))
            return roles["member"].model_copy(update=data.model_dump(exclude_unset=True))

        async def create_role(self, data):
            saved.append(data.model_dump())
            return Role(id="created", **data.model_dump())

    class Config:
        async def get_role_models_by_ids(self, role_ids):
            return {role_id: model_scopes.get(role_id, []) for role_id in role_ids}

        async def get_role_agents_by_ids(self, role_ids):
            return {role_id: agent_scopes.get(role_id, []) for role_id in role_ids}

        async def get_catalog_config(self):
            return []

        async def get_global_config(self):
            return []

    class Models:
        async def get_many_by_ids_and_values(self, identifiers):
            model = ModelConfig(id="model-uuid", value="model-value", label="Model")
            return ({"model-uuid": model} if "model-uuid" in identifiers else {}, {})

    monkeypatch.setattr("src.infra.agent.model_storage.get_model_storage", Models)
    monkeypatch.setattr("src.infra.role.manager.get_role_manager", Roles)
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", Config)
    monkeypatch.setattr(
        "src.agents.core.base.AgentFactory.list_agents",
        lambda *args: [
            {"id": "search", "name": "Search", "sort_order": 1},
            {"id": "team", "name": "Team", "sort_order": 2},
        ],
    )

    @asynccontextmanager
    async def mutation(_actor):
        yield actor

    monkeypatch.setattr(user_routes, "UserManager", Users)
    monkeypatch.setattr(role_routes, "RoleManager", Roles)
    monkeypatch.setattr(user_routes, "authority_mutation", mutation, raising=False)
    monkeypatch.setattr(role_routes, "authority_mutation", mutation, raising=False)
    # The same manager resolves target authority from current persisted roles.
    try:
        from src.infra.auth import delegation
    except ImportError:
        pass
    else:
        monkeypatch.setattr(delegation, "RoleManager", Roles)

        class RoleCollection:
            def find(self, query):
                async def values():
                    for role in roles.values():
                        if "system:admin" in role.permissions:
                            yield {"name": role.name}

                return values()

        class UserCollection:
            async def find_one(self, query):
                return {"_id": "other-admin"} if other_admin["exists"] else None

        monkeypatch.setattr(
            delegation, "RoleStorage", lambda: SimpleNamespace(collection=RoleCollection())
        )
        monkeypatch.setattr(
            delegation, "UserStorage", lambda: SimpleNamespace(collection=UserCollection())
        )

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(user_routes.router, prefix="/users")
    app.include_router(role_routes.router, prefix="/roles")
    app.dependency_overrides[deps.get_current_user_required] = lambda: actor
    return SimpleNamespace(
        app=app,
        actor=actor,
        target=target,
        roles=roles,
        saved=saved,
        other_admin=other_admin,
        model_scopes=model_scopes,
        agent_scopes=agent_scopes,
    )


async def request(case, method, path, body):
    async with AsyncClient(transport=ASGITransport(app=case.app), base_url="http://test") as client:
        return await client.request(method, path, json=body)


@pytest.mark.parametrize(
    "body", [{"roles": ["admin"]}, {"password": "new-secret"}, {"is_active": False}]
)
async def test_profile_editor_cannot_change_account_authority_or_credentials(boundary_app, body):
    response = await request(boundary_app, "PUT", "/users/target", body)
    assert response.status_code == 403
    assert boundary_app.saved == []


@pytest.mark.parametrize(
    "field",
    [
        "reset_token",
        "reset_token_expires",
        "verification_token",
        "verification_token_expires",
        "oauth_id",
        "oauth_provider",
        "email_verified",
    ],
)
async def test_http_user_update_rejects_internal_authentication_fields(boundary_app, field):
    response = await request(boundary_app, "PUT", "/users/target", {field: None})
    assert response.status_code == 422
    assert boundary_app.saved == []


async def test_user_write_alone_cannot_create_accounts(boundary_app):
    response = await request(
        boundary_app,
        "POST",
        "/users/",
        {"username": "new", "email": "new@example.com", "password": "new-secret"},
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_delegate_cannot_assign_an_unscoped_role(boundary_app):
    boundary_app.actor.permissions = ["user:assign_roles", "user:write", "chat:write"]
    response = await request(boundary_app, "PUT", "/users/target", {"roles": ["admin"]})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_delegate_cannot_change_own_roles(boundary_app):
    boundary_app.actor.permissions = ["user:assign_roles", "chat:write"]
    boundary_app.actor.__dict__["assignable_role_ids"] = ["member-id"]
    response = await request(boundary_app, "PUT", "/users/operator", {"roles": ["member"]})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_delegate_cannot_reset_a_superior_account(boundary_app):
    boundary_app.actor.permissions = ["user:write", "user:reset_password"]
    boundary_app.target.roles = ["admin"]
    boundary_app.roles["admin"].permissions = ["system:admin"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_role_writer_cannot_grant_permissions(boundary_app):
    boundary_app.actor.permissions = ["role:manage", "role:write", "chat:write"]
    response = await request(
        boundary_app, "PUT", "/roles/member-id", {"permissions": ["chat:write"]}
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_permission_possession_does_not_imply_grant_authority(boundary_app):
    boundary_app.actor.permissions = ["role:manage", "role:write", "role:grant", "chat:write"]
    response = await request(
        boundary_app, "PUT", "/roles/member-id", {"permissions": ["chat:write"]}
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_delegate_cannot_grant_system_administration(boundary_app):
    boundary_app.actor.permissions = ["role:manage", "role:write", "role:grant", "system:admin"]
    # Highest trust is deliberately absent; a legacy role name grants nothing.
    boundary_app.actor.permissions.remove("system:admin")
    boundary_app.actor.__dict__["grantable_permissions"] = ["system:admin"]
    response = await request(
        boundary_app, "PUT", "/roles/member-id", {"permissions": ["system:admin"]}
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_role_read_requires_explicit_capability(boundary_app):
    response = await request(boundary_app, "GET", "/roles/", None)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,body", [("PUT", {"is_active": False}), ("PUT", {"roles": []}), ("DELETE", None)]
)
async def test_last_usable_system_administrator_cannot_be_removed(boundary_app, method, body):
    boundary_app.actor.permissions = [
        "system:admin",
        "user:write",
        "user:status",
        "user:assign_roles",
        "user:delete",
    ]
    boundary_app.target.roles = ["admin"]
    boundary_app.roles["admin"].permissions = ["system:admin"]
    response = await request(boundary_app, method, "/users/target", body)
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_system_administrator_can_disable_another_when_one_remains(boundary_app):
    boundary_app.actor.permissions = ["system:admin", "user:status"]
    boundary_app.target.roles = ["admin"]
    boundary_app.roles["admin"].permissions = ["system:admin"]
    boundary_app.other_admin["exists"] = True
    response = await request(boundary_app, "PUT", "/users/target", {"is_active": False})
    assert response.status_code == 200
    assert boundary_app.saved == [{"is_active": False}]


async def test_profile_editor_cannot_take_over_recovery_email(boundary_app):
    boundary_app.actor.permissions = ["user:write", "chat:write"]
    response = await request(
        boundary_app, "PUT", "/users/target", {"email": "attacker@example.com"}
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_create_only_account_manager_creates_without_implicit_roles(boundary_app):
    boundary_app.actor.permissions = ["user:create"]
    response = await request(
        boundary_app,
        "POST",
        "/users/",
        {"username": "new", "email": "new@example.com", "password": "new-secret"},
    )
    assert response.status_code == 200
    assert boundary_app.saved[0]["roles"] == []


async def test_create_only_account_manager_cannot_assign_roles(boundary_app):
    boundary_app.actor.permissions = ["user:create"]
    response = await request(
        boundary_app,
        "POST",
        "/users/",
        {
            "username": "new",
            "email": "new@example.com",
            "password": "new-secret",
            "roles": ["member"],
        },
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


@pytest.mark.parametrize("permission", ["chat:read", "session:admin", "skill:admin", "role:manage"])
@pytest.mark.parametrize("field", ["permissions", "grantable_permissions"])
async def test_retired_permissions_cannot_be_granted_through_http(boundary_app, permission, field):
    boundary_app.actor.permissions = ["system:admin", "role:write", "role:grant"]
    response = await request(boundary_app, "PUT", "/roles/member-id", {field: [permission]})
    assert response.status_code == 422
    assert boundary_app.saved == []
    # Historical rows remain readable for the one-time migration.
    role = Role(id="legacy", name="legacy", permissions=[permission])
    assert role.permissions == [permission]


@pytest.mark.parametrize(
    "body", [{"password": "new-secret"}, {"email": "attacker@example.com"}, {"is_active": False}]
)
async def test_account_manager_cannot_take_over_unlimited_model_account(boundary_app, body):
    boundary_app.actor.permissions = [
        "chat:write",
        "user:write",
        "user:reset_password",
        "user:status",
    ]
    boundary_app.actor.roles = ["operator"]
    boundary_app.roles["member"].unrestricted_models = True
    response = await request(boundary_app, "PUT", "/users/target", body)
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_account_manager_cannot_take_over_account_with_additional_agent(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:reset_password"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.agent_scopes["operator-id"] = ["search"]
    boundary_app.agent_scopes["member-id"] = ["search", "team"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_role_assignment_cannot_grant_unlimited_models_to_restricted_actor(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:create", "user:assign_roles"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.actor.assignable_role_ids = ["member-id"]
    boundary_app.roles["member"].unrestricted_models = True
    response = await request(
        boundary_app,
        "POST",
        "/users/",
        {
            "username": "new",
            "email": "new@example.com",
            "password": "new-secret",
            "roles": ["member"],
        },
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_role_assignment_cannot_grant_agents_the_actor_cannot_use(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:create", "user:assign_roles"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.actor.assignable_role_ids = ["member-id"]
    boundary_app.agent_scopes["operator-id"] = ["search"]
    boundary_app.agent_scopes["member-id"] = ["search", "team"]
    response = await request(
        boundary_app,
        "POST",
        "/users/",
        {
            "username": "new",
            "email": "new@example.com",
            "password": "new-secret",
            "roles": ["member"],
        },
    )
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_account_manager_can_reset_equally_scoped_account(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:reset_password"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.agent_scopes["operator-id"] = ["search"]
    boundary_app.agent_scopes["member-id"] = ["search"]
    boundary_app.model_scopes["operator-id"] = ["model-1"]
    boundary_app.model_scopes["member-id"] = ["model-1"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 200
    assert boundary_app.saved == [{"password": "new-secret"}]


async def test_account_manager_cannot_take_over_account_with_additional_model(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:reset_password"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.model_scopes["operator-id"] = ["model-1"]
    boundary_app.model_scopes["member-id"] = ["model-1", "model-2"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_account_manager_with_model_value_scope_can_manage_one_matching_model_id(
    boundary_app,
):
    boundary_app.actor.permissions = ["chat:write", "user:reset_password"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.model_scopes["operator-id"] = ["model-value"]
    boundary_app.model_scopes["member-id"] = ["model-uuid"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 200
    assert boundary_app.saved == [{"password": "new-secret"}]


async def test_one_model_id_does_not_authorize_account_with_all_same_value_channels(boundary_app):
    boundary_app.actor.permissions = ["chat:write", "user:reset_password"]
    boundary_app.actor.roles = ["operator"]
    boundary_app.model_scopes["operator-id"] = ["model-uuid"]
    boundary_app.model_scopes["member-id"] = ["model-value"]
    response = await request(boundary_app, "PUT", "/users/target", {"password": "new-secret"})
    assert response.status_code == 403
    assert boundary_app.saved == []


async def test_new_role_without_agent_assignment_persists_no_agent_access(
    boundary_app, monkeypatch
):
    from unittest.mock import AsyncMock

    from src.infra.agent import config_storage

    boundary_app.actor.permissions = ["role:write"]
    assign = AsyncMock(return_value=[])
    monkeypatch.setattr(
        config_storage, "get_agent_config_storage", lambda: SimpleNamespace(set_role_agents=assign)
    )
    response = await request(boundary_app, "POST", "/roles/", {"name": "new-role"})
    assert response.status_code == 200
    assign.assert_awaited_once_with("created", "new-role", [])

"""Historical capabilities migrate once; new grants never imply unrelated duties."""

import pytest

from src.infra.auth import rbac


def test_legacy_admin_permissions_expand_only_in_migration():
    migrated = rbac.migrate_permission_grants(["model:admin", "usage:admin", "user:write"])
    assert {
        "model:read",
        "model:assign",
        "model:delete",
        "pricing:manage",
        "usage:quota_manage",
        "user:create",
        "user:assign_roles",
    } <= set(migrated)
    assert "system:admin" not in migrated
    assert rbac.migrate_permission_grants(migrated) == migrated


def test_read_only_role_migration_does_not_create_mutation_grants():
    migrated = set(
        rbac.migrate_permission_grants(["session:read", "team:read", "marketplace:read"])
    )
    assert not migrated.intersection({"session:write", "team:write", "skill:write", "memory:write"})
    assert "project:read" in migrated


def test_default_guest_remains_read_only():
    roles = {role["name"]: role for role in rbac.RBACManager().get_default_roles()}
    assert {"project:read", "memory:read", "file:read", "sandbox:read"} <= set(
        roles["guest"]["permissions"]
    )
    assert "system:admin" not in roles["user"]["permissions"]
    assert "sandbox:execute" not in roles["guest"]["permissions"]


@pytest.mark.asyncio
async def test_missing_auxiliary_role_does_not_widen_model_access(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.agent.model_access import resolve_user_allowed_model_ids
    from src.kernel.schemas.user import TokenPayload

    roles = SimpleNamespace(
        get_roles_by_names=AsyncMock(
            return_value=[
                SimpleNamespace(id="restricted", unrestricted_models=False),
                SimpleNamespace(id="aux", unrestricted_models=False),
            ]
        )
    )
    storage = SimpleNamespace(
        get_role_models_by_ids=AsyncMock(return_value={"restricted": ["m"], "aux": None})
    )
    monkeypatch.setattr("src.infra.role.manager.get_role_manager", lambda: roles)
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    assert await resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["restricted", "aux"])
    ) == ["m"]


@pytest.mark.parametrize("assignment,unrestricted", [(None, True), ([], False), (["model"], False)])
async def test_storage_migration_snapshots_legacy_model_scope_once(
    monkeypatch, assignment, unrestricted
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.role.storage import RoleStorage

    document = {"_id": "legacy", "name": "legacy", "permissions": ["model:admin"]}

    class Collection:
        def find(self, query):
            async def cursor():
                if not document.get("migrated"):
                    yield dict(document)

            return cursor()

        async def update_one(self, query, update):
            document.update(update["$set"])
            document["migrated"] = True
            return SimpleNamespace(modified_count=1)

        async def find_one(self, *args):
            return None

    storage = RoleStorage()
    monkeypatch.setattr(type(storage), "collection", property(lambda _: Collection()))
    monkeypatch.setattr(storage, "invalidate_cache", AsyncMock())
    mappings = SimpleNamespace(get_role_models=AsyncMock(return_value=assignment))
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: mappings)
    await storage.migrate_permission_boundaries()
    assert document["unrestricted_models"] is unrestricted
    assert "model:assign" in document["permissions"]
    document["permissions"] = ["model:admin"]
    await storage.migrate_permission_boundaries()
    assert document["permissions"] == ["model:admin"]
    mappings.get_role_models.assert_awaited_once_with("legacy")


async def test_storage_migration_does_not_succeed_after_lost_compare_and_set(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.role.storage import RoleStorage

    document = {"_id": "legacy", "name": "legacy", "permissions": [], "unrestricted_models": False}

    class Collection:
        def find(self, query):
            async def cursor():
                yield document

            return cursor()

        update_one = AsyncMock(return_value=SimpleNamespace(modified_count=0))
        find_one = AsyncMock(return_value=document)

    storage = RoleStorage()
    monkeypatch.setattr(type(storage), "collection", property(lambda _: Collection()))
    with pytest.raises(RuntimeError, match="migration incomplete"):
        await storage.migrate_permission_boundaries()

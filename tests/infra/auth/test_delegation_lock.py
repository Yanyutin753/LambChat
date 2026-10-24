"""Authority mutation serializes the read-check-write sequence across workers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api import deps
from src.infra.auth import delegation
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload, UserCreate, UserInDB


async def test_authority_mutation_reloads_actor_and_rejects_concurrent_writer(monkeypatch):
    state = {"held": False}
    fresh = TokenPayload(sub="actor", username="actor", permissions=[])

    class Lock:
        async def acquire(self, *, blocking):
            assert blocking is False
            if state["held"]:
                return False
            state["held"] = True
            return True

        async def release(self):
            state["held"] = False

    monkeypatch.setattr(
        delegation, "get_redis_client", lambda: SimpleNamespace(lock=lambda *args, **kwargs: Lock())
    )
    monkeypatch.setattr(deps, "_load_user_payload", AsyncMock(return_value=fresh))
    stale = TokenPayload(sub="actor", username="actor", permissions=["system:admin"])
    async with delegation.authority_mutation(stale) as actor:
        assert actor.permissions == []
        with pytest.raises(AppError) as failure:
            async with delegation.authority_mutation(stale):
                pytest.fail("Concurrent account writes must not enter the critical section")
        assert failure.value.error_code == ErrorCode.CONFLICT
    assert state["held"] is False
    async with delegation.authority_mutation(stale):
        assert state["held"] is True
    assert state["held"] is False


async def test_authority_mutation_denies_storage_failure_before_write(monkeypatch):
    class BrokenLock:
        async def acquire(self, **kwargs):
            raise ConnectionError("unavailable")

    monkeypatch.setattr(
        delegation,
        "get_redis_client",
        lambda: SimpleNamespace(lock=lambda *args, **kwargs: BrokenLock()),
    )
    with pytest.raises(AppError) as failure:
        async with delegation.authority_mutation(TokenPayload(sub="actor", username="actor")):
            pytest.fail("A failed authority lock must never permit persistence")
    assert failure.value.error_code == ErrorCode.SERVICE_UNAVAILABLE


async def test_administrative_creation_preserves_explicit_empty_roles(monkeypatch):
    from src.infra.user.manager import UserManager

    stored = []

    class Storage:
        async def list_users(self, **kwargs):
            pytest.fail("Administrative creation must not invoke first-user/default grants")

        async def create(self, data):
            stored.append(data.roles)
            return UserInDB(
                id="new",
                username=data.username,
                email=data.email,
                roles=data.roles,
                password_hash="hash",
            )

    manager = UserManager()
    manager.storage = Storage()
    created = await manager.register(
        UserCreate(username="new", email="new@example.com", password="new-secret"),
        assign_default_role=False,
    )
    assert created.roles == []
    assert stored == [[]]

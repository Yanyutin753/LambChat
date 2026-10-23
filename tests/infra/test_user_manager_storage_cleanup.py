from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.auth import two_factor as two_factor_module
from src.infra.storage.s3.service import get_storage_service, init_storage
from src.infra.storage.s3.types import S3Config, S3Provider
from src.infra.user import manager as user_manager_module
from src.infra.user.manager import UserManager
from src.kernel.config import settings
from src.kernel.schemas.user import User, UserInDB


class _UserStorage:
    async def delete(self, user_id: str) -> bool:
        return True


class _ConcurrentListStorage:
    def __init__(self) -> None:
        self.list_started = asyncio.Event()
        self.count_started = asyncio.Event()

    async def list_users(self, *_args, **_kwargs) -> list[User]:
        self.list_started.set()
        await asyncio.wait_for(self.count_started.wait(), timeout=1)
        return [
            User(
                id="user-1",
                username="alice",
                email="alice@example.com",
                roles=["user"],
                permissions=[],
                is_active=True,
            )
        ]

    async def count_users(self, *_args, **_kwargs) -> int:
        self.count_started.set()
        await asyncio.wait_for(self.list_started.wait(), timeout=1)
        return 1


class _LoginStorage:
    async def authenticate(self, username_or_email: str, password: str) -> UserInDB:
        assert username_or_email == "alice"
        assert password == "secret"
        return UserInDB(
            id="user-1",
            username="alice",
            email="alice@example.com",
            password_hash="hash",
            roles=["user", "admin"],
            permissions=[],
            is_active=True,
            email_verified=True,
            created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        )


class _RoleStorageShouldNotBeCalled:
    async def get_by_name(self, name: str):
        raise AssertionError(f"login should not fetch role {name}")

    async def get_by_names(self, names):
        raise AssertionError(f"login should not fetch roles {names}")


@pytest.mark.asyncio
async def test_login_does_not_fetch_roles_on_token_hot_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        two_factor_module, "create_access_token", lambda user_id, **_: f"access:{user_id}"
    )
    monkeypatch.setattr(
        two_factor_module,
        "create_refresh_token",
        lambda user_id, username, **_: f"refresh:{user_id}:{username}",
    )

    manager = UserManager()
    manager.storage = _LoginStorage()
    manager.role_storage = _RoleStorageShouldNotBeCalled()

    token = await manager.login("alice", "secret")

    assert token is not None
    assert token.access_token == "access:user-1"
    assert token.refresh_token == "refresh:user-1:alice"


@pytest.mark.asyncio
async def test_list_users_fetches_rows_and_count_concurrently() -> None:
    manager = UserManager()
    manager.storage = _ConcurrentListStorage()

    result = await manager.list_users(skip=0, limit=20)

    assert result.total == 1
    assert [user.username for user in result.users] == ["alice"]


@pytest.mark.asyncio
async def test_delete_user_skips_s3_cleanup_when_s3_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )
    storage = get_storage_service()
    calls: list[str] = []

    async def delete_user_files(user_id: str) -> int:
        calls.append(user_id)
        return 1

    monkeypatch.setattr(storage, "delete_user_files", delete_user_files)
    monkeypatch.setattr(settings, "S3_ENABLED", False, raising=False)

    manager = UserManager()
    manager.storage = _UserStorage()

    assert await manager.delete_user("user-1") is True
    await asyncio.sleep(0)

    assert calls == []


@pytest.mark.asyncio
async def test_delete_user_treats_string_false_as_s3_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )
    storage = get_storage_service()
    calls: list[str] = []

    async def delete_user_files(user_id: str) -> int:
        calls.append(user_id)
        return 1

    monkeypatch.setattr(storage, "delete_user_files", delete_user_files)
    monkeypatch.setattr(settings, "S3_ENABLED", "false", raising=False)

    manager = UserManager()
    manager.storage = _UserStorage()

    assert await manager.delete_user("user-1") is True
    await asyncio.sleep(0)

    assert calls == []


@pytest.mark.asyncio
async def test_delete_user_uses_initialized_storage_when_s3_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _Storage:
        _config = type("_Config", (), {"bucket_name": "bucket"})()

        async def delete_user_files(self, user_id: str) -> int:
            calls.append(user_id)
            return 1

    async def get_or_init_storage():
        return _Storage()

    monkeypatch.setattr(settings, "S3_ENABLED", True, raising=False)
    monkeypatch.setattr("src.infra.user.manager.get_or_init_storage", get_or_init_storage)

    manager = UserManager()
    manager.storage = _UserStorage()

    assert await manager.delete_user("user-1") is True
    await asyncio.sleep(0)

    assert calls == ["user-1"]


@pytest.mark.asyncio
async def test_delete_user_s3_cleanup_tasks_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    class _Storage:
        _config = type("_Config", (), {"bucket_name": "bucket"})()

        async def delete_user_files(self, user_id: str) -> int:
            calls.append(user_id)
            started.set()
            await release.wait()
            return 1

    async def get_or_init_storage():
        return _Storage()

    monkeypatch.setattr(settings, "S3_ENABLED", True, raising=False)
    monkeypatch.setattr("src.infra.user.manager.get_or_init_storage", get_or_init_storage)
    monkeypatch.setattr(
        user_manager_module,
        "_s3_cleanup_tasks",
        BestEffortTaskLimiter("test user S3 cleanup", max_tasks=1),
    )

    manager = UserManager()
    manager.storage = _UserStorage()

    assert await manager.delete_user("user-1") is True
    await started.wait()
    assert await manager.delete_user("user-2") is True
    await asyncio.sleep(0)

    assert calls == ["user-1"]

    release.set()

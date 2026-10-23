from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.infra.user import storage as user_storage_module
from src.infra.user.storage import UserStorage
from src.kernel.schemas.user import UserCreate, UserInDB, UserUpdate


class _InsertResult:
    inserted_id = "user-id"


class _FakeCollection:
    def __init__(self, user: UserInDB | None = None) -> None:
        self.user = user
        self.inserted: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None

    async def insert_one(self, doc: dict[str, Any]) -> _InsertResult:
        self.inserted = doc
        return _InsertResult()

    async def find_one_and_update(
        self,
        _query: dict[str, Any],
        update: dict[str, Any],
        return_document: bool,
    ) -> dict[str, Any]:
        self.updated = update["$set"]
        return {
            "_id": "user-id",
            "username": "alice",
            "email": "alice@example.com",
            "password_hash": self.updated["password_hash"],
            "roles": ["user"],
            "permissions": [],
            "is_active": True,
            "email_verified": True,
            "created_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
            "updated_at": self.updated["updated_at"],
        }


class _FindOneCollection:
    def __init__(self, doc: dict[str, Any] | None) -> None:
        self.doc = doc
        self.find_one_calls: list[dict[str, Any]] = []

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        self.find_one_calls.append(query)
        if self.doc is None:
            return None
        return dict(self.doc)


async def _fake_run_blocking_io(func, *args, **kwargs):
    _fake_run_blocking_io.calls.append(func.__name__)
    return func(*args, **kwargs)


_fake_run_blocking_io.calls = []


@pytest.fixture(autouse=True)
def _patch_password_helpers(monkeypatch):
    _fake_run_blocking_io.calls = []
    monkeypatch.setattr(
        user_storage_module,
        "run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )
    monkeypatch.setattr(user_storage_module, "hash_password", lambda password: f"hash:{password}")
    monkeypatch.setattr(
        user_storage_module,
        "verify_password",
        lambda password, hashed: hashed == f"hash:{password}",
    )


@pytest.mark.asyncio
async def test_create_hashes_password_off_event_loop() -> None:
    storage = UserStorage()
    storage._collection = _FakeCollection()

    await storage.create(
        UserCreate(
            username="alice",
            email="alice@example.com",
            password="secret123",
            skip_verification=True,
        )
    )

    assert _fake_run_blocking_io.calls == ["<lambda>"]
    assert storage.collection.inserted["password_hash"] == "hash:secret123"


@pytest.mark.asyncio
async def test_update_hashes_password_off_event_loop() -> None:
    storage = UserStorage()
    storage._collection = _FakeCollection()

    await storage.update("6659f5bd6b4a1b2c3d4e5f60", UserUpdate(password="new-secret"))

    assert _fake_run_blocking_io.calls == ["<lambda>"]
    assert storage.collection.updated["password_hash"] == "hash:new-secret"


@pytest.mark.asyncio
async def test_authenticate_verifies_password_off_event_loop() -> None:
    storage = UserStorage()
    storage._collection = _FindOneCollection(
        {
            "_id": "user-id",
            "username": "alice",
            "email": "alice@example.com",
            "password_hash": "hash:secret123",
            "roles": ["user"],
            "permissions": [],
            "is_active": True,
            "email_verified": True,
            "created_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
        }
    )

    user = await storage.authenticate("alice", "secret123")

    assert user is not None
    assert user.username == "alice"
    assert _fake_run_blocking_io.calls == ["<lambda>"]


@pytest.mark.asyncio
async def test_authenticate_fetches_username_or_email_with_single_query() -> None:
    user_doc = {
        "_id": "user-id",
        "username": "alice",
        "email": "alice@example.com",
        "password_hash": "hash:secret123",
        "roles": ["user"],
        "permissions": [],
        "is_active": True,
        "email_verified": True,
        "created_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 25, tzinfo=timezone.utc),
    }
    storage = UserStorage()
    storage._collection = _FindOneCollection(user_doc)

    user = await storage.authenticate("alice@example.com", "secret123")

    assert user is not None
    assert user.email == "alice@example.com"
    assert storage.collection.find_one_calls == [
        {"$or": [{"username": "alice@example.com"}, {"email": "alice@example.com"}]}
    ]


async def test_password_change_revokes_old_sessions_without_disabling_two_factor():
    storage = UserStorage()
    storage._collection = _FakeCollection()
    await storage.update("507f1f77bcf86cd799439011", UserUpdate(password="new-secret"))
    fields = storage.collection.updated
    assert len(fields["auth_version"]) >= 32
    assert "two_factor" not in fields
    assert "two_factor_enabled" not in fields

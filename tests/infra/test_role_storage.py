from __future__ import annotations

from datetime import datetime

import pytest

from src.infra.role.storage import RoleStorage


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    async def incr(self, key: str) -> int:
        next_value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(next_value)
        return next_value


class _FakeCollection:
    async def find_one(self, query: dict) -> dict | None:
        if query != {"name": "admin"}:
            return None
        return {
            "_id": "role-1",
            "name": "admin",
            "description": "Administrator",
            "permissions": [],
            "allowed_agents": [],
            "limits": None,
            "is_system": True,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }


@pytest.mark.asyncio
async def test_get_by_name_uses_dedicated_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    isolated_pool_flags: list[bool] = []

    monkeypatch.setattr(
        "src.infra.role.storage.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )

    storage = RoleStorage()
    storage._collection = _FakeCollection()

    role = await storage.get_by_name("admin")

    assert role is not None
    assert role.name == "admin"
    assert isolated_pool_flags == [True]

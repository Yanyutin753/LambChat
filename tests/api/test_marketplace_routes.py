from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.api.routes import marketplace as marketplace_routes
from src.infra.skill.types import InstalledFrom, MarketplaceSkillResponse, SkillMeta
from src.kernel.schemas.user import TokenPayload


def _publisher() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="publisher",
        roles=["user"],
        permissions=["marketplace:publish"],
    )


def _reader() -> TokenPayload:
    return TokenPayload(
        sub="user-2",
        username="reader",
        roles=["user"],
        permissions=["marketplace:read"],
    )


class _MarketplaceListStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list_marketplace_skills(self, **kwargs):
        self.calls.append(kwargs)
        return [
            MarketplaceSkillResponse(
                skill_name="planner",
                description="Plan work",
                tags=["planning"],
                version="2.0.0",
                created_by="user-1",
                created_by_username="tester",
                is_active=True,
                file_count=2,
            )
        ]


class _MarketplaceShouldNotSync:
    async def create_marketplace_skill(self, *_args, **_kwargs):
        return SimpleNamespace()

    async def sync_marketplace_files(self, *_args, **_kwargs):
        raise AssertionError("oversized marketplace files should be rejected before sync")

    async def delete_marketplace_skill(self, *_args, **_kwargs):
        raise AssertionError("metadata should not be created for oversized payload")


class _InstallMarketplace:
    async def get_marketplace_skill(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(skill_name=name, is_active=True, created_by="publisher")

    async def list_marketplace_file_paths(self, name: str) -> list[str]:
        return ["SKILL.md"]

    async def iter_marketplace_file_batches(self, name: str):
        yield {"SKILL.md": "# Marketplace version"}


class _FailingInstallMarketplace(_InstallMarketplace):
    async def iter_marketplace_file_batches(self, name: str):
        raise RuntimeError("marketplace read failed")
        yield {}


class _ManualSkillStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.upserted: list[tuple[str, dict[str, str], str]] = []
        self.synced: list[tuple[str, dict[str, str], str]] = []
        self.meta_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.invalidated: list[str] = []

    async def get_skill_meta(self, name: str, user_id: str) -> SkillMeta:
        return SkillMeta(installed_from=InstalledFrom.MANUAL)

    async def delete_skill_files(self, name: str, user_id: str) -> None:
        self.deleted.append((name, user_id))

    async def upsert_skill_files_batch(self, name: str, files: dict[str, str], user_id: str) -> int:
        self.upserted.append((name, files, user_id))
        return len(files)

    async def sync_skill_files(self, name: str, files: dict[str, str], user_id: str) -> None:
        self.synced.append((name, files, user_id))

    async def set_skill_meta(self, name: str, user_id: str, **kwargs: Any) -> None:
        self.meta_calls.append((name, user_id, kwargs))

    async def invalidate_user_cache(self, user_id: str) -> None:
        self.invalidated.append(user_id)


@pytest.mark.asyncio
async def test_list_marketplace_skills_keeps_skill_payload_and_adds_extension_entry() -> None:
    marketplace = _MarketplaceListStorage()

    result = await marketplace_routes.list_marketplace_skills(
        tags="planning,productivity",
        search="plan",
        skip=5,
        limit=10,
        user=_reader(),
        marketplace=marketplace,
    )

    assert marketplace.calls == [
        {
            "tags": ["planning", "productivity"],
            "search": "plan",
            "include_inactive": False,
            "viewer_id": "user-2",
            "skip": 5,
            "limit": 10,
        }
    ]
    assert result[0].skill_name == "planner"
    assert result[0].version == "2.0.0"
    assert result[0].extension_type == "skill"
    assert result[0].extension_id == "skill:planner"
    assert result[0].extension is not None
    assert result[0].extension.id == "skill:planner"
    assert result[0].extension.type == "skill"
    assert result[0].extension.capabilities == ["skill"]

@pytest.mark.asyncio
async def test_create_marketplace_skill_rejects_too_many_files_before_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(marketplace_routes, "MARKETPLACE_SKILL_MAX_FILES", 2)

    with pytest.raises(HTTPException) as exc:
        await marketplace_routes.create_marketplace_skill(
            marketplace_routes.MarketplaceCreateRequest(
                skill_name="too-many",
                files={
                    "a.md": "hello",
                    "b.md": "hello",
                    "c.md": "hello",
                },
            ),
            user=_publisher(),
            marketplace=_MarketplaceShouldNotSync(),
        )

    assert exc.value.status_code == 413
    assert "too many files" in exc.value.detail


@pytest.mark.asyncio
async def test_create_marketplace_skill_rejects_total_file_content_before_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(marketplace_routes, "MARKETPLACE_SKILL_MAX_TOTAL_CHARS", 10)

    with pytest.raises(HTTPException) as exc:
        await marketplace_routes.create_marketplace_skill(
            marketplace_routes.MarketplaceCreateRequest(
                skill_name="too-large",
                files={
                    "a.md": "hello",
                    "b.md": "world!",
                },
            ),
            user=_publisher(),
            marketplace=_MarketplaceShouldNotSync(),
        )

    assert exc.value.status_code == 413
    assert "too large" in exc.value.detail


@pytest.mark.asyncio
async def test_install_marketplace_skill_replaces_existing_manual_skill() -> None:
    storage = _ManualSkillStorage()

    result = await marketplace_routes.install_marketplace_skill(
        "planner",
        user=TokenPayload(
            sub="user-1",
            username="reader",
            roles=["user"],
            permissions=["marketplace:read"],
        ),
        marketplace=_InstallMarketplace(),
        storage=storage,
    )

    assert result["skill_name"] == "planner"
    assert result["file_count"] == 1
    assert storage.deleted == []
    assert storage.upserted == []
    assert storage.synced == [("planner", {"SKILL.md": "# Marketplace version"}, "user-1")]
    assert storage.meta_calls == [
        (
            "planner",
            "user-1",
            {"installed_from": InstalledFrom.MARKETPLACE},
        )
    ]
    assert storage.invalidated == ["user-1"]


@pytest.mark.asyncio
async def test_install_marketplace_skill_keeps_manual_skill_when_marketplace_read_fails() -> None:
    storage = _ManualSkillStorage()

    with pytest.raises(RuntimeError, match="marketplace read failed"):
        await marketplace_routes.install_marketplace_skill(
            "planner",
            user=TokenPayload(
                sub="user-1",
                username="reader",
                roles=["user"],
                permissions=["marketplace:read"],
            ),
            marketplace=_FailingInstallMarketplace(),
            storage=storage,
        )

    assert storage.deleted == []
    assert storage.upserted == []
    assert storage.synced == []
    assert storage.meta_calls == []
    assert storage.invalidated == []

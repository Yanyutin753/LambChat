from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import marketplace as marketplace_routes
from src.infra.skill.types import MarketplaceSkillResponse
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

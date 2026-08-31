from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.api.routes.auth import profile as profile_route
from src.infra.user import storage as user_storage
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", ["light", "dark", "sepia"])
async def test_update_profile_metadata_accepts_supported_themes(
    monkeypatch: pytest.MonkeyPatch, theme: str
) -> None:
    received: dict = {}

    class _FakeStorage:
        async def update_metadata(self, _user_id, metadata):
            received.update(metadata)
            return {"metadata": metadata}

    monkeypatch.setattr(user_storage, "UserStorage", lambda: _FakeStorage())

    app = FastAPI()
    app.include_router(profile_route.router, prefix="/api/auth")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/auth/profile/metadata",
            json={"metadata": {"theme": theme}},
        )

    assert response.status_code == 200
    assert received == {"theme": theme}


@pytest.mark.asyncio
async def test_update_profile_metadata_rejects_unknown_theme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def update_metadata(self, *_args, **_kwargs):
            raise AssertionError("unknown theme should be rejected before storage update")

    monkeypatch.setattr(user_storage, "UserStorage", lambda: _StorageShouldNotBeCalled())

    app = FastAPI()
    app.include_router(profile_route.router, prefix="/api/auth")
    register_error_handlers(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/auth/profile/metadata",
            json={"metadata": {"theme": "neon"}},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_theme"


@pytest.mark.asyncio
async def test_update_profile_metadata_rejects_too_many_favorite_presets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def update_metadata(self, *_args, **_kwargs):
            raise AssertionError("oversized metadata should be rejected before storage update")

    monkeypatch.setattr(user_storage, "UserStorage", lambda: _StorageShouldNotBeCalled())

    app = FastAPI()
    app.include_router(profile_route.router, prefix="/api/auth")
    register_error_handlers(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/auth/profile/metadata",
            json={"metadata": {"favorite_preset_ids": [f"preset-{index}" for index in range(101)]}},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "profile_field_too_many"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata_key", ["disabled_skills", "pinned_skill_names", "favorite_skill_names"]
)
async def test_update_profile_metadata_rejects_too_many_skill_lists(
    monkeypatch: pytest.MonkeyPatch,
    metadata_key: str,
) -> None:
    class _StorageShouldNotBeCalled:
        async def update_metadata(self, *_args, **_kwargs):
            raise AssertionError("oversized metadata should be rejected before storage update")

    monkeypatch.setattr(user_storage, "UserStorage", lambda: _StorageShouldNotBeCalled())

    app = FastAPI()
    app.include_router(profile_route.router, prefix="/api/auth")
    register_error_handlers(app)
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/auth/profile/metadata",
            json={"metadata": {metadata_key: [f"{metadata_key}-{index}" for index in range(101)]}},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "profile_field_too_many"

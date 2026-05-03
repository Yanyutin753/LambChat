from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import persona_preset as persona_preset_route
from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetScope,
    PersonaPresetStatus,
    PersonaPresetVisibility,
)
from src.kernel.schemas.user import TokenPayload


def _fake_user(*permissions: str) -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=list(permissions),
    )


@pytest.mark.asyncio
async def test_list_persona_presets_returns_real_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeManager:
        async def list_presets(self, **kwargs):
            assert kwargs["skip"] == 20
            assert kwargs["limit"] == 10
            return [
                PersonaPreset(
                    id="preset-1",
                    scope=PersonaPresetScope.GLOBAL,
                    owner_user_id=None,
                    name="Planner",
                    description="Plan carefully",
                    avatar=None,
                    tags=["planning"],
                    system_prompt="Plan first.",
                    skill_names=["planner"],
                    visibility=PersonaPresetVisibility.PUBLIC,
                    status=PersonaPresetStatus.PUBLISHED,
                    source_preset_id=None,
                    copied_from_version=None,
                    version=1,
                    usage_count=5,
                    created_by="admin-1",
                    updated_by="admin-1",
                    created_at=datetime(2026, 1, 1),
                    updated_at=datetime(2026, 1, 2),
                )
            ]

        async def count_presets(self, **kwargs):
            assert kwargs["skip"] == 20
            assert kwargs["limit"] == 10
            return 37

    monkeypatch.setattr(persona_preset_route, "_manager", lambda: _FakeManager())

    app = FastAPI()
    app.include_router(persona_preset_route.router, prefix="/api/persona-presets")
    app.dependency_overrides[api_deps.get_current_user_required] = lambda: _fake_user(
        "persona_preset:read"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/persona-presets/?skip=20&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 37
    assert len(payload["presets"]) == 1

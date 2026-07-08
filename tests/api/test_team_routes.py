from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import team as team_route
from src.kernel.extensions import AGENT_TEAM_PLUGIN_ID, PluginManifest, PluginRuntime
from src.kernel.schemas.team import (
    TeamCreate,
    TeamListResponse,
    TeamPreferenceUpdate,
    TeamResponse,
    TeamVisibility,
)
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["chat:write"],
    )


def test_team_create_rejects_too_many_members() -> None:
    with pytest.raises(ValueError):
        TeamCreate(
            name="Large team",
            members=[
                {"persona_preset_id": f"preset-{index}", "role_name": f"Role {index}"}
                for index in range(21)
            ],
        )


def test_team_member_schema_accepts_null_and_string_model_id() -> None:
    no_override = TeamCreate(
        name="Default Model Team",
        members=[{"persona_preset_id": "preset-1", "model_id": None}],
    )
    override = TeamCreate(
        name="Override Model Team",
        members=[{"persona_preset_id": "preset-1", "model_id": "model-member"}],
    )

    assert no_override.members[0].model_id is None
    assert override.members[0].model_id == "model-member"


def test_team_member_schema_ignores_legacy_agent_id() -> None:
    team = TeamCreate(
        name="Legacy Mode Team",
        members=[{"persona_preset_id": "preset-1", "agent_id": "search"}],
    )

    assert not hasattr(team.members[0], "agent_id")


def _team(team_id: str = "team-1") -> TeamResponse:
    return TeamResponse(
        id=team_id,
        owner_user_id="user-1",
        name="Team",
        visibility=TeamVisibility.PRIVATE,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


@pytest.mark.asyncio
async def test_collection_crud_accepts_paths_without_trailing_slash() -> None:
    calls: list[str] = []
    seen_users: list[TokenPayload] = []

    class _FakeManager:
        async def list_teams(self, **kwargs):
            calls.append("list")
            return TeamListResponse(teams=[_team()], total=1, skip=0, limit=20)

        async def create_team(self, body, **kwargs):
            calls.append("create")
            seen_users.append(kwargs["user"])
            return _team("created")

    app = FastAPI()
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_response = await client.get("/api/teams")
        create_response = await client.post("/api/teams", json={"name": "Team"})

    assert list_response.status_code == 200
    assert create_response.status_code == 201
    assert calls == ["list", "create"]
    assert seen_users[0].sub == "user-1"


@pytest.mark.asyncio
async def test_team_routes_fail_closed_when_agent_team_plugin_disabled() -> None:
    class _FakeManager:
        async def list_teams(self, **kwargs):
            raise AssertionError("disabled Agent Team route must not reach manager")

    runtime = PluginRuntime(
        [
            PluginManifest(
                id=AGENT_TEAM_PLUGIN_ID,
                name="Agent Team",
                version="1.0.0",
                api_version="1",
                enabled_by_default=False,
            )
        ]
    )
    app = FastAPI()
    app.state.plugin_runtime = runtime
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/teams")

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "plugin_unavailable"
    assert response.json()["detail"]["plugin_id"] == AGENT_TEAM_PLUGIN_ID


@pytest.mark.asyncio
async def test_create_team_returns_bad_request_for_invalid_member_model() -> None:
    class _FakeManager:
        async def create_team(self, body, **kwargs):
            raise ValueError("team_member_model_unavailable")

    app = FastAPI()
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/teams",
            json={
                "name": "Team",
                "members": [{"persona_preset_id": "preset-1", "model_id": "missing-model"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "team_member_model_unavailable"


@pytest.mark.asyncio
async def test_update_team_passes_current_user_to_model_validation() -> None:
    calls: list[dict] = []

    class _FakeManager:
        async def update_team(self, team_id, body, **kwargs):
            calls.append(kwargs)
            return _team(team_id)

    app = FastAPI()
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/teams/team-1",
            json={
                "members": [{"persona_preset_id": "preset-1", "model_id": "model-member"}],
            },
        )

    assert response.status_code == 200
    assert calls[0]["owner_user_id"] == "user-1"
    assert calls[0]["user"].sub == "user-1"


@pytest.mark.asyncio
async def test_list_teams_accepts_export_page_size() -> None:
    calls: list[dict] = []

    class _FakeManager:
        async def list_teams(self, **kwargs):
            calls.append(kwargs)
            return TeamListResponse(
                teams=[],
                total=0,
                skip=kwargs["skip"],
                limit=kwargs["limit"],
            )

    app = FastAPI()
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/teams/?skip=0&limit=200")

    assert response.status_code == 200
    assert response.json()["limit"] == 200
    assert calls[0]["limit"] == 200


@pytest.mark.asyncio
async def test_update_team_preference_route() -> None:
    calls: list[tuple[str, bool | None, bool | None]] = []

    class _FakeManager:
        async def update_preference(self, team_id: str, preference, **kwargs):
            assert isinstance(preference, TeamPreferenceUpdate)
            assert kwargs["owner_user_id"] == "user-1"
            calls.append((team_id, preference.is_favorite, preference.is_pinned))
            return _team(team_id).model_copy(update={"is_favorite": True})

    app = FastAPI()
    app.include_router(team_route.router, prefix="/api/teams")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[team_route._get_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/teams/team-1/preference",
            json={"is_favorite": True},
        )

    assert response.status_code == 200
    assert response.json()["is_favorite"] is True
    assert calls == [("team-1", True, None)]

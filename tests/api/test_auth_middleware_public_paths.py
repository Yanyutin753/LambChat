from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.middleware.auth import AuthMiddleware


@pytest.mark.asyncio
async def test_vapid_public_key_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/push/vapid-public-key")
    async def vapid_public_key() -> dict[str, str]:
        return {"public_key": "test-key"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/push/vapid-public-key")

    assert response.status_code == 200
    assert response.json() == {"public_key": "test-key"}


@pytest.mark.asyncio
async def test_progress_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/progress/goal-3-tasks.md")
    async def progress_file() -> str:
        return "progress"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/progress/goal-3-tasks.md")

    assert response.status_code == 200
    assert response.json() == "progress"


@pytest.mark.asyncio
async def test_plugin_contribution_states_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/extensions/plugins/contribution-states")
    async def contribution_states() -> dict[str, object]:
        return {"plugins": [], "total": 0}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/extensions/plugins/contribution-states")

    assert response.status_code == 200
    assert response.json() == {"plugins": [], "total": 0}


@pytest.mark.asyncio
async def test_plugin_contributions_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/extensions/plugins/contributions")
    async def contributions() -> dict[str, object]:
        return {"plugins": [], "total": 0}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/extensions/plugins/contributions")

    assert response.status_code == 200
    assert response.json() == {"plugins": [], "total": 0}


@pytest.mark.asyncio
async def test_extension_host_contributions_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/extensions/contributions")
    async def contributions() -> dict[str, object]:
        return {"plugins": [], "total": 0}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/extensions/contributions")

    assert response.status_code == 200
    assert response.json() == {"plugins": [], "total": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,scope",
    [
        ("/api/extensions/contributions/project-options", "project"),
        ("/api/extensions/contributions/session-options", "session"),
        ("/api/extensions/contributions/channel-options", "channel"),
        ("/api/extensions/contributions/scheduled-task-options", "scheduled_task"),
    ],
)
async def test_extension_host_scoped_option_paths_are_public_without_authorization(
    path: str,
    scope: str,
) -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get(path)
    async def scoped_options() -> dict[str, object]:
        return {"options": [], "total": 0, "scope": scope}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"options": [], "total": 0, "scope": scope}


@pytest.mark.asyncio
async def test_extension_host_slots_path_is_public_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/extensions/slots")
    async def slots() -> dict[str, object]:
        return {"slots": [], "total": 0}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/extensions/slots")

    assert response.status_code == 200
    assert response.json() == {"slots": [], "total": 0}


@pytest.mark.asyncio
async def test_full_plugin_runtime_path_stays_protected_without_authorization() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/extensions/plugins/")
    async def plugins() -> dict[str, object]:
        return {"plugins": [], "total": 0}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/extensions/plugins/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

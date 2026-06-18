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

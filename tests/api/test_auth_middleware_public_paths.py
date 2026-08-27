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
async def test_static_font_paths_are_public_without_authorization() -> None:
    """自托管字体 /fonts/*.woff2 必须匿名可访问（否则未登录用户字体全部 401）。"""
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/fonts/source-sans-3-400-latin.woff2")
    async def font_file() -> dict[str, str]:
        return {"ok": "font"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/fonts/source-sans-3-400-latin.woff2")

    assert response.status_code == 200

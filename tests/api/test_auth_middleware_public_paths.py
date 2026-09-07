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


@pytest.mark.asyncio
async def test_release_asset_download_path_is_public_without_authorization() -> None:
    """release 资产代理下载必须匿名可访问（移动端更新链路）。

    PUBLIC_PATHS 是精确匹配集合——``/api/version/assets/`` 挂在那里挡不住
    ``/api/version/assets/<name>/download`` 实际路径，移动端「立即更新」
    全部 401（2.8.3 引入，2026-09-07 用户报告）。
    """
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/version/assets/{asset_name}/download")
    async def asset_download(asset_name: str) -> dict[str, str]:
        return {"ok": "asset", "name": asset_name}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/version/assets/LambChat-android-v2.8.4-signed.apk/download",
            headers={"accept": "*/*"},  # WebView fetch 非 text/html，不走浏览器导航豁免
        )

    assert response.status_code == 200
    assert response.json()["ok"] == "asset"

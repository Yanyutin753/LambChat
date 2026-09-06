"""Tests for version route with release assets."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.version import router
from src.infra.github_client import GitHubClient, GitHubRelease


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    # Mock settings so the route can resolve them without real config
    with patch(
        "src.api.routes.version.settings",
        MagicMock(
            APP_VERSION="2.5.0",
            GIT_TAG="v2.5.0",
            COMMIT_HASH="abc1234",
            BUILD_TIME="2026-01-01T00:00:00Z",
            GITHUB_URL="https://github.com/Yanyutin753/LambChat",
        ),
    ):
        yield TestClient(app)


def make_mock_release(**overrides) -> GitHubRelease:
    defaults = dict(
        tag_name="v2.6.0",
        html_url="https://github.com/Yanyutin753/LambChat/releases/tag/v2.6.0",
        published_at="2026-06-11T00:00:00Z",
        body="## What's New\n- Fixed bugs\n- Added features",
        assets=[
            {
                "name": "LambChat-v2.6.0-android-signed.apk",
                "url": "https://github.com/Yanyutin753/LambChat/releases/download/v2.6.0/LambChat-v2.6.0-android-signed.apk",
                "size": 50_000_000,
                "content_type": "application/vnd.android.package-archive",
            }
        ],
    )
    defaults.update(overrides)
    return GitHubRelease(**defaults)


def test_version_response_has_release_notes(client):
    release = make_mock_release()
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_notes"] == "## What's New\n- Fixed bugs\n- Added features"


def test_version_response_has_release_assets(client):
    release = make_mock_release()
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_assets"] is not None
        assert len(data["release_assets"]) == 1
        asset = data["release_assets"][0]
        assert asset["name"] == "LambChat-v2.6.0-android-signed.apk"
        assert "android-signed.apk" in asset["url"]
        assert asset["size"] == 50_000_000


def test_version_response_no_release(client):
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=None
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_notes"] is None
        assert data["release_assets"] is None


def test_has_update_compares_client_version(client):
    """客户端上报版本时，has_update 按客户端版本比较，服务端版本不参与。"""
    release = make_mock_release(tag_name="v2.6.0")
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        # 客户端已是 2.6.0：即使服务端是 2.5.0 也不提示更新
        resp = client.get("/api/version", params={"client_version": "2.6.0"})
        assert resp.status_code == 200
        assert resp.json()["has_update"] is False

        # 客户端 2.5.0 落后于最新版：提示更新
        resp = client.get("/api/version", params={"client_version": "2.5.0"})
        assert resp.status_code == 200
        assert resp.json()["has_update"] is True


def test_has_update_falls_back_to_server_version_without_client_version(client):
    """未上报客户端版本时保持旧行为：按服务端版本比较。"""
    release = make_mock_release(tag_name="v2.6.0")
    with patch.object(
        GitHubClient, "get_latest_release", new_callable=AsyncMock, return_value=release
    ):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json()["has_update"] is True

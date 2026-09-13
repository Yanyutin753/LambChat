"""资产下载代理的缓存竞态自愈回归。

事故（v2.11.0 发版实测）：latest.json 由 updater 工作流在 release 发布后
上传，服务端 latest-release 进程缓存（TTL 1h）持有无 latest.json 的旧
资产快照 → 桌面端自更新主端点 404（备用 GitHub 端点国内不可达）。
热修：latest 路径找不到资产时 force_refresh 一次再找。
"""

from src.api.routes.version import download_release_asset
from src.infra.github_client import GitHubRelease
from src.kernel.errors import AppError, ErrorCode

import pytest


def _release(assets: list[str]) -> GitHubRelease:
    return GitHubRelease(
        tag_name="v2.11.0",
        html_url="https://example.com",
        published_at="2026-09-13T10:28:39Z",
        assets=[
            {
                "name": name,
                "url": f"https://example.com/{name}",
                "size": 1,
                "content_type": "application/octet-stream",
            }
            for name in assets
        ],
    )


class _Stream:
    status_code = 200
    content_length = 1

    async def iter_chunks(self):
        yield b"{}"

    async def close(self):
        return None


class _FakeClient:
    """第一次返回旧快照（无 latest.json），force_refresh 后返回新快照。"""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def get_latest_release(self, force_refresh: bool = False):
        self.calls.append(force_refresh)
        if not force_refresh:
            return _release(["app.tar.gz", "deb"])
        return _release(["app.tar.gz", "deb", "latest.json"])

    async def get_release_by_tag(self, tag):
        return _release(["latest.json"])

    async def open_asset_stream(self, url):
        return _Stream()


async def test_latest_path_retries_with_force_refresh_on_missing_asset(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.routes import version as version_module

    fake = _FakeClient()
    monkeypatch.setattr(version_module, "github_client", fake)

    response = await download_release_asset("latest.json", tag=None)
    assert response.status_code == 200
    assert fake.calls == [False, True]  # 缓存快照未命中 → 强刷自愈


async def test_tag_path_does_not_force_refresh(monkeypatch: pytest.MonkeyPatch):
    from src.api.routes import version as version_module

    class _TagClient:
        refreshed = False

        async def get_release_by_tag(self, tag):
            return _release(["latest.json"])

        async def get_latest_release(self, force_refresh=False):
            _TagClient.refreshed = True
            return _release([])

        async def open_asset_stream(self, url):
            class _Stream:
                status_code = 200
                content_length = 1

                async def iter_chunks(self):
                    yield b"{}"

                async def close(self):
                    return None

            return _Stream()

    monkeypatch.setattr(version_module, "github_client", _TagClient())
    response = await download_release_asset("latest.json", tag="v2.11.0")
    assert response.status_code == 200
    assert _TagClient.refreshed is False  # tag 锁定路径不做 latest 强刷

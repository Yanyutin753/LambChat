"""GitHubClient 按标签取 release 的行为（下载代理按版本锁资产用）。"""

from datetime import UTC, datetime, timedelta

import pytest

from src.infra import github_client as gc_module
from src.infra.github_client import CACHE_TTL_SECONDS, GitHubClient

TAG_URL = f"{gc_module.GITHUB_API_URL.replace('/latest', '')}/tags/v2.6.0"

PAYLOAD = {
    "tag_name": "v2.6.0",
    "html_url": "https://github.com/Yanyutin753/LambChat/releases/tag/v2.6.0",
    "published_at": "2026-06-11T00:00:00Z",
    "body": "notes",
    "assets": [
        {
            "name": "LambChat-v2.6.0-Windows.msi",
            "browser_download_url": "https://github.com/x/y/releases/download/v2.6.0/LambChat-v2.6.0-Windows.msi",
            "size": 42,
            "content_type": "application/octet-stream",
        }
    ],
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """按 URL 应答的 httpx.AsyncClient 替身；请求 URL 记到类级共享列表
    （_fetch_release 每次调用都新建 client，单实例列表会漏记）。"""

    all_requests: list[str] = []

    def __init__(self, responses=None, timeout=None):
        self._responses = responses or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeAsyncClient.all_requests.append(url)
        return self._responses.get(url, _FakeResponse(status_code=404))


@pytest.fixture(autouse=True)
def _reset_requests():
    _FakeAsyncClient.all_requests = []


def _install(monkeypatch: pytest.MonkeyPatch, responses) -> None:
    def _factory(*args, **kwargs):
        return _FakeAsyncClient(responses=responses, *args, **kwargs)

    monkeypatch.setattr(gc_module.httpx, "AsyncClient", _factory)


@pytest.mark.asyncio
async def test_get_release_by_tag_hits_tags_endpoint_and_parses_assets(monkeypatch):
    _install(monkeypatch, {TAG_URL: _FakeResponse(payload=PAYLOAD)})

    release = await GitHubClient().get_release_by_tag("v2.6.0")

    assert _FakeAsyncClient.all_requests == [TAG_URL]
    assert release is not None
    assert release.tag_name == "v2.6.0"
    assert release.assets[0]["url"].endswith("LambChat-v2.6.0-Windows.msi")


@pytest.mark.asyncio
async def test_get_release_by_tag_caches_per_tag_until_ttl(monkeypatch):
    _install(monkeypatch, {TAG_URL: _FakeResponse(payload=PAYLOAD)})
    client = GitHubClient()

    await client.get_release_by_tag("v2.6.0")
    await client.get_release_by_tag("v2.6.0")
    assert _FakeAsyncClient.all_requests == [TAG_URL]  # TTL 内只打一次上游

    # 老化缓存条目越过 TTL 后重新拉取
    client._tag_cache["v2.6.0"] = (
        client._tag_cache["v2.6.0"][0],
        datetime.now(UTC) - timedelta(seconds=CACHE_TTL_SECONDS + 1),
    )
    await client.get_release_by_tag("v2.6.0")
    assert _FakeAsyncClient.all_requests == [TAG_URL, TAG_URL]


@pytest.mark.asyncio
async def test_get_release_by_tag_missing_tag_returns_none(monkeypatch):
    _install(monkeypatch, {})  # 任何 URL 都 404

    release = await GitHubClient().get_release_by_tag("v9.9.9")

    assert release is None
    assert _FakeAsyncClient.all_requests == [
        f"{gc_module.GITHUB_API_URL.replace('/latest', '')}/tags/v9.9.9"
    ]

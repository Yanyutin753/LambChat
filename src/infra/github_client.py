"""GitHub client for fetching release information."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx

GITHUB_REPO = "Yanyutin753/LambChat"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_TAG_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{{tag}}"
CACHE_TTL_SECONDS = 3600  # 1 hour
TAG_CACHE_MAX_ENTRIES = 8


@dataclass
class GitHubRelease:
    """GitHub release information"""

    tag_name: str
    html_url: str
    published_at: str
    body: str = ""
    assets: list[dict] = field(default_factory=list)


@dataclass
class AssetStream:
    """已打开的上游资产流（持有 httpx 连接，消费完毕必须 close）。"""

    client: httpx.AsyncClient
    response: httpx.Response

    @property
    def status_code(self) -> int:
        return self.response.status_code

    @property
    def content_length(self) -> int | None:
        header = self.response.headers.get("content-length")
        return int(header) if header and header.isdigit() else None

    async def iter_chunks(self):
        """按 256KB 分块产出上游字节流。"""
        async for chunk in self.response.aiter_bytes(256 * 1024):
            yield chunk

    async def close(self) -> None:
        await self.response.aclose()
        await self.client.aclose()


class GitHubClient:
    """Client for fetching GitHub release information with simple in-memory cache."""

    def __init__(self):
        self._cache: Optional[GitHubRelease] = None
        self._cache_time: Optional[datetime] = None
        self._tag_cache: dict[str, tuple[GitHubRelease, datetime]] = {}

    async def get_latest_release(self, force_refresh: bool = False) -> Optional[GitHubRelease]:
        """Get latest release from GitHub, using cache if available"""
        if not force_refresh and self._is_cache_valid():
            return self._cache

        release = await self._fetch_release()
        if release:
            self._cache = release
            self._cache_time = datetime.now(UTC)
        return release

    def _is_cache_valid(self) -> bool:
        """Check if cache is valid"""
        if self._cache is None or self._cache_time is None:
            return False
        elapsed = datetime.now(UTC) - self._cache_time
        return elapsed < timedelta(seconds=CACHE_TTL_SECONDS)

    async def get_release_by_tag(self, tag: str) -> Optional[GitHubRelease]:
        """按 tag 查 release（下载代理把清单锁到具体版本时用）。

        更新器下载端点会扇出到这里：不缓存的话 GitHub 匿名 API 限流
        （60 次/小时/源 IP）会被瞬时打穿，故与 latest 同 TTL 做 per-tag
        缓存，容量截断防任意 tag 撑爆内存。
        """
        key = tag.strip()
        if not key:
            return None
        cached = self._tag_cache.get(key)
        if cached and datetime.now(UTC) - cached[1] < timedelta(seconds=CACHE_TTL_SECONDS):
            return cached[0]
        release = await self._fetch_release(GITHUB_TAG_RELEASE_URL.format(tag=key))
        if release:
            if len(self._tag_cache) >= TAG_CACHE_MAX_ENTRIES:
                oldest = min(self._tag_cache, key=lambda k: self._tag_cache[k][1])
                del self._tag_cache[oldest]
            self._tag_cache[key] = (release, datetime.now(UTC))
        return release

    async def open_asset_stream(self, url: str) -> "AssetStream":
        """打开 release 资产的上游下载流（github.com 302 → 签名 blob，需跟随重定向）。

        供下载代理路由使用：调用方负责消费 ``iter_chunks`` 后 ``close``。
        读超时放宽到 120s（大文件逐块读取），不设总超时。
        """
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0),
            follow_redirects=True,
        )
        try:
            response = await client.send(client.build_request("GET", url), stream=True)
        except Exception:
            await client.aclose()
            raise
        return AssetStream(client=client, response=response)

    async def _fetch_release(self, url: str = GITHUB_API_URL) -> Optional[GitHubRelease]:
        """Fetch release JSON from GitHub API (latest or by-tag endpoint)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers={"Accept": "application/vnd.github+json"})
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_release(data)
                return None
        except Exception:
            return None

    def _parse_release(self, data: dict) -> GitHubRelease:
        """Parse GitHub API response"""
        assets = []
        for asset in data.get("assets", []):
            assets.append(
                {
                    "name": asset.get("name", ""),
                    "url": asset.get("browser_download_url", ""),
                    "size": asset.get("size"),
                    "content_type": asset.get("content_type", "application/octet-stream"),
                }
            )
        return GitHubRelease(
            tag_name=data.get("tag_name", ""),
            html_url=data.get("html_url", ""),
            published_at=data.get("published_at", ""),
            body=data.get("body", ""),
            assets=assets,
        )


# Singleton instance
github_client = GitHubClient()

"""GitHub client for fetching release information."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx

GITHUB_REPO = "Yanyutin753/LambChat"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass
class GitHubRelease:
    """GitHub release information"""

    tag_name: str
    html_url: str
    published_at: str


class GitHubClient:
    """Client for fetching GitHub release information with simple in-memory cache."""

    def __init__(self):
        self._cache: Optional[GitHubRelease] = None
        self._cache_time: Optional[datetime] = None

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
        """Check if cache is still valid"""
        if self._cache is None or self._cache_time is None:
            return False
        elapsed = datetime.now(UTC) - self._cache_time
        return elapsed < timedelta(seconds=CACHE_TTL_SECONDS)

    async def _fetch_release(self) -> Optional[GitHubRelease]:
        """Fetch latest release from GitHub API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    GITHUB_API_URL, headers={"Accept": "application/vnd.github+json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_release(data)
                return None
        except Exception:
            return None

    def _parse_release(self, data: dict) -> GitHubRelease:
        """Parse GitHub API response"""
        return GitHubRelease(
            tag_name=data.get("tag_name", ""),
            html_url=data.get("html_url", ""),
            published_at=data.get("published_at", ""),
        )


# Singleton instance
github_client = GitHubClient()

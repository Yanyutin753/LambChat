"""Tests for GitHub client."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infra.github_client import GitHubClient, GitHubRelease


class TestGitHubClient:
    """Test cases for GitHubClient."""

    def test_parse_release(self):
        """Test parsing GitHub API response."""
        client = GitHubClient()
        mock_response = {
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/Yanyutin753/LambChat/releases/tag/v1.2.0",
            "published_at": "2026-02-28T12:00:00Z",
        }
        release = client._parse_release(mock_response)
        assert release.tag_name == "v1.2.0"
        assert release.html_url == "https://github.com/Yanyutin753/LambChat/releases/tag/v1.2.0"
        assert release.published_at == "2026-02-28T12:00:00Z"

    @pytest.mark.asyncio
    async def test_get_latest_release_cached(self):
        """Test that cache is used on subsequent calls."""
        from datetime import UTC, datetime, timedelta

        client = GitHubClient()

        # Pre-populate cache with cache time
        client._cache = GitHubRelease(
            tag_name="v1.2.0",
            html_url="https://github.com/Yanyutin753/LambChat/releases/tag/v1.2.0",
            published_at="2026-02-28T12:00:00Z",
        )
        client._cache_time = datetime.now(UTC) - timedelta(minutes=30)  # Cache is 30 minutes old

        with patch.object(client, "_fetch_release", new_callable=AsyncMock) as mock_fetch:
            # First call - should use cache
            result = await client.get_latest_release(force_refresh=False)
            assert result is not None
            assert result.tag_name == "v1.2.0"
            # fetch should not be called
            assert mock_fetch.call_count == 0

    @pytest.mark.asyncio
    async def test_get_latest_release_force_refresh(self):
        """Test force_refresh bypasses cache."""
        client = GitHubClient()

        # Pre-populate cache
        client._cache = GitHubRelease(
            tag_name="v1.0.0",
            html_url="https://github.com/Yanyutin753/LambChat/releases/tag/v1.0.0",
            published_at="2026-01-01T12:00:00Z",
        )

        with patch.object(client, "_fetch_release", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = GitHubRelease(
                tag_name="v1.2.0",
                html_url="https://github.com/Yanyutin753/LambChat/releases/tag/v1.2.0",
                published_at="2026-02-28T12:00:00Z",
            )

            # Force refresh should bypass cache
            result = await client.get_latest_release(force_refresh=True)
            assert result is not None
            assert result.tag_name == "v1.2.0"
            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_release_failure(self):
        """Test handling of fetch failure."""
        client = GitHubClient()

        with patch.object(client, "_fetch_release", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            result = await client.get_latest_release(force_refresh=True)
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        """Test that HTTP errors are handled gracefully."""
        client = GitHubClient()

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await client._fetch_release()
            assert result is None

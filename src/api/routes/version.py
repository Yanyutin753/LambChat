"""Version info route."""

from fastapi import APIRouter, Query

from src.infra.github_client import github_client
from src.kernel.config import settings
from src.kernel.schemas.agent import VersionResponse
from src.kernel.version_utils import has_new_version, normalize_version

router = APIRouter()


@router.get("/version", response_model=VersionResponse)
async def get_version(
    force_refresh: bool = Query(False, description="Force refresh GitHub cache"),
) -> VersionResponse:
    """Get application version info including git tag and build time."""
    # Fetch latest from GitHub
    latest_release = await github_client.get_latest_release(force_refresh=force_refresh)

    # Determine if update available
    has_update = False
    if latest_release:
        has_update = has_new_version(settings.APP_VERSION, latest_release.tag_name)

    return VersionResponse(
        app_version=settings.APP_VERSION,
        git_tag=settings.GIT_TAG,
        commit_hash=settings.COMMIT_HASH,
        build_time=settings.BUILD_TIME,
        latest_version=normalize_version(latest_release.tag_name) if latest_release else None,
        release_url=latest_release.html_url if latest_release else None,
        has_update=has_update,
        published_at=latest_release.published_at if latest_release else None,
    )

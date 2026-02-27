"""Version info route."""

from fastapi import APIRouter

from src.kernel.config import settings
from src.kernel.schemas.agent import VersionResponse

router = APIRouter()


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Get application version info including git tag and build time."""
    return VersionResponse(
        app_version=settings.APP_VERSION,
        git_tag=settings.GIT_TAG,
        commit_hash=settings.COMMIT_HASH,
        build_time=settings.BUILD_TIME,
    )

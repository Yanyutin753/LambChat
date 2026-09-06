"""Version info route."""

from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from src.infra.github_client import github_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import ReleaseAsset, VersionResponse
from src.kernel.version_utils import has_new_version, normalize_version

router = APIRouter()


@router.get("/version", response_model=VersionResponse)
async def get_version(
    force_refresh: bool = Query(False, description="Force refresh GitHub cache"),
    client_version: Optional[str] = Query(
        None,
        description="Client app version; has_update compares against it instead of server version",
    ),
) -> VersionResponse:
    """Get application version info including git tag and build time."""
    # Fetch latest from GitHub
    latest_release = await github_client.get_latest_release(force_refresh=force_refresh)

    # Determine if update available
    # has_update 优先按客户端上报版本比较（客户端自检更新）；未上报时回落
    # 服务端版本（网页端仅展示版本信息，沿用旧语义）
    current_version = client_version or settings.APP_VERSION
    has_update = False
    if latest_release:
        has_update = has_new_version(current_version, latest_release.tag_name)

    release_assets = None
    if latest_release:
        release_assets = [ReleaseAsset(**asset) for asset in latest_release.assets]

    return VersionResponse(
        app_version=settings.APP_VERSION,
        git_tag=settings.GIT_TAG,
        commit_hash=settings.COMMIT_HASH,
        build_time=settings.BUILD_TIME,
        latest_version=normalize_version(latest_release.tag_name) if latest_release else None,
        release_url=latest_release.html_url if latest_release else None,
        github_url=settings.GITHUB_URL,
        has_update=has_update,
        published_at=latest_release.published_at if latest_release else None,
        release_notes=latest_release.body if latest_release else None,
        release_assets=release_assets,
    )


def _find_asset(latest_release: Any, asset_name: str) -> Optional[dict]:
    """在最新 release 资产清单里按名精确查找（同时防止把端点当开放代理）。"""
    if not latest_release:
        return None
    for asset in latest_release.assets:
        if asset.get("name") == asset_name:
            return asset
    return None


@router.get("/version/assets/{asset_name}/download")
async def download_release_asset(asset_name: str) -> StreamingResponse:
    """按资产名流式代理 GitHub release 资产下载。

    移动端 WebView 直连 github.com 会被 CORS 拦截（release 下载端点不带
    Access-Control-Allow-Origin）；经自托管后端同源转发即可正常下载，
    且 content-length 转发后前端进度条照常工作。
    """
    latest_release = await github_client.get_latest_release()
    asset = _find_asset(latest_release, asset_name)
    if asset is None:
        raise AppError(ErrorCode.RELEASE_ASSET_NOT_FOUND, args={"name": asset_name})

    stream = await github_client.open_asset_stream(asset["url"])
    if stream.status_code != 200:
        status = stream.status_code
        await stream.close()
        raise AppError(ErrorCode.RELEASE_ASSET_FETCH_FAILED, args={"status": status})

    async def _stream():
        try:
            async for chunk in stream.iter_chunks():
                yield chunk
        finally:
            await stream.close()

    headers = {"Content-Disposition": f'attachment; filename="{asset_name}"'}
    if stream.content_length:
        headers["Content-Length"] = str(stream.content_length)
    return StreamingResponse(
        _stream(),
        media_type=asset.get("content_type") or "application/octet-stream",
        headers=headers,
    )

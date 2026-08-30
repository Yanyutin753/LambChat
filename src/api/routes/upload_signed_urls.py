"""
Signed URL API routes for upload-backed files.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required, require_permissions
from src.infra.logging import get_logger
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

SIGNED_URL_KEYS_MAX = 100

router = APIRouter()


class SignedUrlRequest(BaseModel):
    """Request model for getting signed URLs"""

    keys: list[str] = Field(
        ...,
        min_length=1,
        max_length=SIGNED_URL_KEYS_MAX,
        description="List of S3 object keys to get signed URLs for",
    )
    expires: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="URL expiration time in seconds (default 1 hour, max 24 hours)",
    )


class SignedUrlItem(BaseModel):
    """Single signed URL result"""

    key: str
    url: str | None = None
    error: str | None = None


class SignedUrlResponse(BaseModel):
    """Response model for signed URLs"""

    urls: list[SignedUrlItem]
    expires_in: int


@router.post(
    "/signed-urls",
    response_model=SignedUrlResponse,
    dependencies=[Depends(require_permissions("file:upload"))],
)
async def get_signed_urls(
    body: SignedUrlRequest,
    req: Request,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlResponse:
    """
    Get presigned URLs for private S3 objects.
    """
    del current_user
    from src.api.routes import upload as upload_route

    storage = await upload_route.get_or_init_storage()
    base_url = upload_route._get_base_url(req)

    if storage.is_local:
        urls = []
        for key in body.keys:
            try:
                exists = await storage.file_exists(key)
                if exists:
                    urls.append(SignedUrlItem(key=key, url=f"{base_url}/api/upload/file/{key}"))
                else:
                    urls.append(SignedUrlItem(key=key, error="File not found"))
            except Exception as e:
                urls.append(SignedUrlItem(key=key, error=str(e)))
        return SignedUrlResponse(urls=urls, expires_in=0)

    if storage._config.public_bucket:
        urls = []
        for key in body.keys:
            try:
                url = await storage.get_file_url(key)
                urls.append(SignedUrlItem(key=key, url=url))
            except Exception as e:
                urls.append(SignedUrlItem(key=key, error=str(e)))
        return SignedUrlResponse(urls=urls, expires_in=0)

    urls = []
    for key in body.keys:
        try:
            url = await storage.get_presigned_url(key, body.expires)
            urls.append(SignedUrlItem(key=key, url=url))
        except Exception as e:
            logger.warning("Failed to generate signed URL for %s: %s", key, e)
            urls.append(SignedUrlItem(key=key, error=str(e)))

    return SignedUrlResponse(urls=urls, expires_in=body.expires)


@router.get(
    "/signed-url",
    response_model=SignedUrlItem,
    dependencies=[Depends(require_permissions("file:upload"))],
)
async def get_single_signed_url(
    key: str,
    request: Request,
    expires: int = 3600,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlItem:
    """
    Get a single presigned URL for a private S3 object.
    """
    del current_user
    if expires < 60 or expires > 86400:
        raise AppError(ErrorCode.INVALID_EXPIRES_RANGE)

    from src.api.routes import upload as upload_route

    storage = await upload_route.get_or_init_storage()
    base_url = upload_route._get_base_url(request)

    try:
        if storage.is_local:
            exists = await storage.file_exists(key)
            if not exists:
                return SignedUrlItem(key=key, error="File not found")
            return SignedUrlItem(key=key, url=f"{base_url}/api/upload/file/{key}")
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, expires)
        return SignedUrlItem(key=key, url=url)
    except Exception as e:
        logger.warning("Failed to generate signed URL for %s: %s", key, e)
        return SignedUrlItem(key=key, error=str(e))

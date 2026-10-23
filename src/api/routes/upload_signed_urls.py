"""
Signed URL API routes for upload-backed files.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required
from src.infra.logging import get_logger
from src.infra.upload.access import file_access_url, require_file_access, validate_file_key
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
    app_url: bool = False


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
)
async def get_signed_urls(
    body: SignedUrlRequest,
    req: Request,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlResponse:
    """
    Get presigned URLs for private S3 objects.
    """
    from src.api.routes import upload as upload_route

    for key in body.keys:
        validate_file_key(key)

    private_urls = []
    public_keys = []
    base_url = upload_route._get_base_url(req)
    private_keys = [
        key
        for key in body.keys
        if key.startswith(("cua_screenshots/", "tool_binaries/"))
        and "\\" not in key
        and not any(part in (".", "..", "") for part in key.split("/"))
    ]
    private_access = (
        await upload_route._file_record_storage.get_private_key_access(
            private_keys, current_user.sub
        )
        if private_keys
        else {}
    )
    for key in body.keys:
        if "\\" in key or any(part in (".", "..", "") for part in key.split("/")):
            private_urls.append(SignedUrlItem(key=key, error="File not found"))
        elif key in private_access:
            if private_access[key]:
                private_urls.append(SignedUrlItem(key=key, url=f"{base_url}/api/upload/file/{key}"))
            else:
                private_urls.append(SignedUrlItem(key=key, error="File not found"))
        else:
            public_keys.append(key)
    if public_keys:
        from src.infra.upload.shared_files import owned_file_keys

        owned_keys = await owned_file_keys(set(public_keys), current_user.sub)
        owned_keys.update(key for key in public_keys if key.startswith("avatars/"))
        private_urls.extend(
            SignedUrlItem(key=key, error="File not found")
            for key in public_keys
            if key not in owned_keys
        )
        public_keys = [key for key in public_keys if key in owned_keys]
    if not public_keys:
        return SignedUrlResponse(urls=private_urls, expires_in=0)
    if body.app_url:
        return SignedUrlResponse(
            urls=private_urls
            + [
                SignedUrlItem(
                    key=key,
                    url=file_access_url(
                        f"{base_url}/api/upload/file/{key}", key, expires=body.expires
                    ),
                )
                for key in public_keys
            ],
            expires_in=body.expires,
        )
    storage = await upload_route.get_or_init_storage()

    if storage.is_local:
        urls = list(private_urls)
        for key in public_keys:
            try:
                exists = await storage.file_exists(key)
                if exists:
                    urls.append(
                        SignedUrlItem(
                            key=key,
                            url=file_access_url(
                                f"{base_url}/api/upload/file/{key}", key, expires=body.expires
                            ),
                        )
                    )
                else:
                    urls.append(SignedUrlItem(key=key, error="File not found"))
            except Exception as e:
                urls.append(SignedUrlItem(key=key, error=str(e)))
        return SignedUrlResponse(urls=urls, expires_in=0)

    if storage._config.public_bucket:
        urls = list(private_urls)
        for key in public_keys:
            try:
                url = await storage.get_file_url(key)
                urls.append(SignedUrlItem(key=key, url=url))
            except Exception as e:
                urls.append(SignedUrlItem(key=key, error=str(e)))
        return SignedUrlResponse(urls=urls, expires_in=0)

    urls = list(private_urls)
    for key in public_keys:
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
)
async def get_single_signed_url(
    key: str,
    request: Request,
    expires: int = 3600,
    app_url: bool = False,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlItem:
    """
    Get a single presigned URL for a private S3 object.
    """
    if expires < 60 or expires > 86400:
        raise AppError(ErrorCode.INVALID_EXPIRES_RANGE)
    validate_file_key(key)

    from src.api.routes import upload as upload_route

    if "\\" in key or any(part in (".", "..", "") for part in key.split("/")):
        return SignedUrlItem(key=key, error="File not found")
    base_url = upload_route._get_base_url(request)
    if key.startswith(
        ("cua_screenshots/", "tool_binaries/")
    ) and await upload_route._file_record_storage.is_private_key(key):
        try:
            await upload_route._file_record_storage.require_private_access(key, current_user.sub)
            return SignedUrlItem(key=key, url=f"{base_url}/api/upload/file/{key}")
        except AppError:
            return SignedUrlItem(key=key, error="File not found")
    record = await upload_route._file_record_storage.find_by_key(key, current_user.sub)
    if not record or record.get("uploaded_by") != current_user.sub or record.get("deleting_at"):
        try:
            await require_file_access(key, current_user.sub)
        except AppError:
            return SignedUrlItem(key=key, error="File not found")
    if app_url:
        return SignedUrlItem(
            key=key, url=file_access_url(f"{base_url}/api/upload/file/{key}", key, expires=expires)
        )
    storage = await upload_route.get_or_init_storage()

    try:
        if storage.is_local:
            exists = await storage.file_exists(key)
            if not exists:
                return SignedUrlItem(key=key, error="File not found")
            return SignedUrlItem(
                key=key,
                url=file_access_url(f"{base_url}/api/upload/file/{key}", key, expires=expires),
            )
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, expires)
        return SignedUrlItem(key=key, url=url)
    except Exception as e:
        logger.warning("Failed to generate signed URL for %s: %s", key, e)
        return SignedUrlItem(key=key, error=str(e))

"""
File upload API routes

Provides endpoints for file uploads to S3-compatible storage.
"""

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required, require_permissions
from src.infra.settings.service import get_settings_service
from src.infra.storage.s3 import S3Config, S3Provider, get_storage_service, init_storage
from src.kernel.config import settings
from src.kernel.schemas.user import TokenPayload

logger = logging.getLogger(__name__)


def _parse_bool(value: Any) -> bool:
    """Parse boolean value from various types."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


router = APIRouter()


async def get_s3_enabled() -> bool:
    """Get S3 enabled status from settings (supports database settings)"""
    # First try to get from settings service (database)
    try:
        service = get_settings_service()
        s3_enabled = await service.get("S3_ENABLED")
        if s3_enabled is not None:
            return bool(s3_enabled)
    except Exception:
        pass
    # Fall back to environment/config
    return settings.S3_ENABLED


async def get_s3_config_from_settings() -> S3Config:
    """Get S3 configuration from settings (supports database settings)"""
    # Try to get from settings service first (database)
    s3_enabled = await get_s3_enabled()
    logger.info(f"S3 enabled: {s3_enabled}")
    if not s3_enabled:
        # Fall back to config
        return settings.get_s3_config()

    # Get all settings from database
    try:
        service = get_settings_service()
        # Use get_raw for sensitive settings to get actual values
        s3_provider = await service.get_raw("S3_PROVIDER")
        s3_endpoint = await service.get_raw("S3_ENDPOINT_URL")
        s3_access_key = await service.get_raw("S3_ACCESS_KEY")
        s3_secret_key = await service.get_raw("S3_SECRET_KEY")
        s3_region = await service.get_raw("S3_REGION")
        s3_bucket = await service.get_raw("S3_BUCKET_NAME")
        s3_custom_domain = await service.get_raw("S3_CUSTOM_DOMAIN")
        s3_path_style = await service.get_raw("S3_PATH_STYLE")
        s3_max_size = await service.get_raw("S3_MAX_FILE_SIZE")
        s3_public_bucket = await service.get_raw("S3_PUBLIC_BUCKET")

        logger.info(
            f"S3 config from DB - provider: {s3_provider}, endpoint: {s3_endpoint}, bucket: {s3_bucket}, region: {s3_region}, path_style: {s3_path_style}, public: {s3_public_bucket}"
        )
    except Exception as e:
        # Fall back to config
        logger.warning(f"Failed to get S3 config from database: {e}")
        return settings.get_s3_config()

    # Use config values as fallback
    s3_provider = s3_provider if s3_provider is not None else settings.S3_PROVIDER
    s3_endpoint = s3_endpoint if s3_endpoint is not None else settings.S3_ENDPOINT_URL
    s3_access_key = s3_access_key if s3_access_key is not None else settings.S3_ACCESS_KEY
    s3_secret_key = s3_secret_key if s3_secret_key is not None else settings.S3_SECRET_KEY
    s3_region = s3_region if s3_region is not None else settings.S3_REGION
    s3_bucket = s3_bucket if s3_bucket is not None else settings.S3_BUCKET_NAME
    s3_custom_domain = (
        s3_custom_domain if s3_custom_domain is not None else settings.S3_CUSTOM_DOMAIN
    )
    s3_path_style = s3_path_style if s3_path_style is not None else settings.S3_PATH_STYLE
    s3_max_size = s3_max_size if s3_max_size is not None else settings.S3_MAX_FILE_SIZE
    s3_public_bucket = (
        s3_public_bucket
        if s3_public_bucket is not None
        else getattr(settings, "S3_PUBLIC_BUCKET", False)
    )

    # Map provider string to enum
    provider_map = {
        "aws": S3Provider.AWS,
        "aliyun": S3Provider.ALIYUN,
        "tencent": S3Provider.TENCENT,
        "minio": S3Provider.MINIO,
        "custom": S3Provider.CUSTOM,
    }

    return S3Config(
        provider=provider_map.get(str(s3_provider).lower(), S3Provider.AWS),
        endpoint_url=s3_endpoint if s3_endpoint else None,
        access_key=str(s3_access_key) if s3_access_key else "",
        secret_key=str(s3_secret_key) if s3_secret_key else "",
        region=str(s3_region) if s3_region else "us-east-1",
        bucket_name=str(s3_bucket) if s3_bucket else "",
        custom_domain=s3_custom_domain if s3_custom_domain else None,
        path_style=_parse_bool(s3_path_style),
        public_bucket=_parse_bool(s3_public_bucket),
        max_file_size=int(s3_max_size) if s3_max_size else 10485760,
    )


async def get_or_init_storage():
    """Initialize and get storage service"""
    s3_enabled = await get_s3_enabled()
    if s3_enabled:
        config = await get_s3_config_from_settings()
        await init_storage(config)
    return get_storage_service()


@router.post("/upload", dependencies=[Depends(require_permissions("file:upload"))])
async def upload_file(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Upload a file to S3

    Requires: file:upload permission
    Files are stored in folders organized by user_id.

    Args:
        file: File to upload
        current_user: Current authenticated user

    Returns:
        Upload result with URL and metadata
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings in System Settings.",
        )

    storage = await get_or_init_storage()

    # Validate file
    content = await file.read()
    is_valid, error_msg = storage.validate_file(file.filename or "", len(content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Reset file position after reading
    await file.seek(0)

    # Upload - use user_id as folder
    try:
        result = await storage.upload_file(
            file=file.file,
            folder=current_user.sub,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            metadata={"uploaded_by": current_user.sub},
        )

        return {
            "key": result.key,
            "url": result.url,
            "size": result.size,
            "content_type": result.content_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def _get_image_content_type(data: bytes) -> str:
    """Detect image content type from binary data using magic bytes"""
    # Check magic bytes to detect image type
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif data[:2] == b"\xff\xd8":
        return "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    elif data[:2] in (b"BM", b"BA"):
        return "image/bmp"
    else:
        return "image/png"  # Default to PNG


@router.post("/upload/avatar", dependencies=[Depends(require_permissions("file:upload"))])
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Upload user avatar

    Avatar is stored as base64 in the database (users.avatar_data).
    No S3 required for avatar storage.

    Requires: file:upload permission

    Args:
        file: Avatar image file
        current_user: Current authenticated user

    Returns:
        Avatar data URI
    """
    # Read file content
    content = await file.read()

    # Validate file size (max 2MB for avatar)
    max_size = 2 * 1024 * 1024  # 2MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="Avatar file size exceeds maximum of 2MB",
        )

    # Validate file type
    allowed_image_extensions = ["jpg", "jpeg", "png", "gif", "webp"]
    ext = (
        (file.filename or "avatar.png").lower().split(".")[-1]
        if "." in (file.filename or "")
        else ""
    )
    if ext not in allowed_image_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' is not allowed. Allowed types: {', '.join(allowed_image_extensions)}",
        )

    # Detect content type
    content_type = _get_image_content_type(content)

    # Convert to base64
    avatar_base64 = base64.b64encode(content).decode("utf-8")
    data_uri = f"data:{content_type};base64,{avatar_base64}"

    # Update user's avatar_url (with data URI) in database
    # Note: We store the data URI in avatar_url for backward compatibility with frontend
    try:
        from src.infra.user.storage import UserStorage
        from src.kernel.schemas.user import UserUpdate

        logger.info(f"Uploading avatar for user: {current_user.sub}, filename: {file.filename}")
        storage = UserStorage()
        await storage.update(
            current_user.sub,
            UserUpdate(avatar_url=data_uri),  # Store data URI in avatar_url for frontend
        )
        logger.info(f"Avatar uploaded successfully for user: {current_user.sub}")

        return {
            "url": data_uri,
            "size": len(content),
            "content_type": content_type,
        }
    except Exception as e:
        logger.exception("Avatar upload failed")
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")


@router.delete("/{key:path}", dependencies=[Depends(require_permissions("file:upload"))])
async def delete_file(
    key: str,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Delete a file from S3

    Requires: file:upload permission

    Args:
        key: File key to delete
        current_user: Current authenticated user

    Returns:
        Deletion status
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings in System Settings.",
        )

    storage = await get_or_init_storage()

    try:
        deleted = await storage.delete_file(key)
        return {"deleted": deleted, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/config")
async def get_storage_config() -> dict:
    """
    Get storage configuration status

    Returns:
        Storage configuration (without sensitive data)
    """
    s3_enabled = await get_s3_enabled()
    # settings 已在 initialize_settings 时从数据库加载
    s3_provider = settings.S3_PROVIDER
    s3_max_size = settings.S3_MAX_FILE_SIZE

    return {
        "enabled": s3_enabled,
        "provider": s3_provider if s3_enabled else None,
        "max_file_size": int(s3_max_size) if s3_enabled and s3_max_size else None,
    }


# ============================================================================
# Signed URL API (for private buckets)
# ============================================================================


class SignedUrlRequest(BaseModel):
    """Request model for getting signed URLs"""

    keys: list[str] = Field(..., description="List of S3 object keys to get signed URLs for")
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


@router.post("/signed-urls", response_model=SignedUrlResponse)
async def get_signed_urls(
    request: SignedUrlRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlResponse:
    """
    Get presigned URLs for private S3 objects

    This endpoint generates temporary signed URLs that can be used to access
    private files stored in S3. The URLs expire after the specified time.

    Args:
        request: Contains list of S3 keys and optional expiration time
        current_user: Current authenticated user

    Returns:
        List of signed URLs for each requested key
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings.",
        )

    storage = await get_or_init_storage()

    # Check if bucket is private (need signed URLs)
    if storage._config.public_bucket:
        # Public bucket - return direct URLs instead
        urls = []
        for key in request.keys:
            try:
                url = await storage.get_file_url(key)
                urls.append(SignedUrlItem(key=key, url=url))
            except Exception as e:
                urls.append(SignedUrlItem(key=key, error=str(e)))
        return SignedUrlResponse(urls=urls, expires_in=0)  # expires_in=0 means no expiration

    # Private bucket - generate presigned URLs
    urls = []
    for key in request.keys:
        try:
            url = await storage.get_presigned_url(key, request.expires)
            urls.append(SignedUrlItem(key=key, url=url))
        except Exception as e:
            logger.warning(f"Failed to generate signed URL for {key}: {e}")
            urls.append(SignedUrlItem(key=key, error=str(e)))

    return SignedUrlResponse(urls=urls, expires_in=request.expires)


@router.get("/signed-url", response_model=SignedUrlItem)
async def get_single_signed_url(
    key: str,
    expires: int = 3600,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlItem:
    """
    Get a single presigned URL for a private S3 object

    Convenience endpoint for getting a single signed URL.

    Args:
        key: S3 object key
        expires: URL expiration time in seconds (default 1 hour)
        current_user: Current authenticated user

    Returns:
        Signed URL for the requested key
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings.",
        )

    # Validate expires range
    if expires < 60 or expires > 86400:
        raise HTTPException(
            status_code=400,
            detail="expires must be between 60 and 86400 seconds",
        )

    storage = await get_or_init_storage()

    try:
        # If bucket is public, return direct URL
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, expires)
        return SignedUrlItem(key=key, url=url)
    except Exception as e:
        logger.warning(f"Failed to generate signed URL for {key}: {e}")
        return SignedUrlItem(key=key, error=str(e))


class SignedUrlResponseSimple(BaseModel):
    """Simple response for signed URL"""

    url: str
    expires_in: int


@router.get("/signed-url/simple")
async def get_signed_url_simple(
    key: str,
    expires: int = 3600,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> SignedUrlResponseSimple:
    """
    Get a presigned URL for a private S3 object (simple response)

    This endpoint returns just the URL string, useful for direct use in img src, etc.

    Args:
        key: S3 object key
        expires: URL expiration time in seconds (default 1 hour, max 24 hours)
        current_user: Current authenticated user

    Returns:
        Signed URL and expiration time
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings.",
        )

    # Validate expires range
    if expires < 60 or expires > 86400:
        raise HTTPException(
            status_code=400,
            detail="expires must be between 60 and 86400 seconds",
        )

    storage = await get_or_init_storage()

    try:
        # If bucket is public, return direct URL
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
            return SignedUrlResponseSimple(url=url, expires_in=0)
        else:
            url = await storage.get_presigned_url(key, expires)
            return SignedUrlResponseSimple(url=url, expires_in=expires)
    except Exception as e:
        logger.warning(f"Failed to generate signed URL for {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

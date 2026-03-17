"""
File upload API routes

Provides endpoints for file uploads to S3-compatible storage.
"""

import asyncio
import base64
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.file_type import (
    FILE_EXTENSIONS,
    FileCategory,
    get_file_category,
    get_permission_for_category,
)
from src.infra.auth.rbac import check_permission
from src.infra.logging import get_logger
from src.infra.storage.s3 import S3Config, S3Provider, get_storage_service, init_storage
from src.kernel.config import settings
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)


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


def get_s3_enabled() -> bool:
    """Get S3 enabled status from cached settings"""
    return bool(settings.S3_ENABLED)


async def get_s3_config_from_settings() -> S3Config:
    """Get S3 configuration from cached settings"""
    if not get_s3_enabled():
        return settings.get_s3_config()

    provider_map = {
        "aws": S3Provider.AWS,
        "aliyun": S3Provider.ALIYUN,
        "tencent": S3Provider.TENCENT,
        "minio": S3Provider.MINIO,
        "custom": S3Provider.CUSTOM,
    }

    return S3Config(
        provider=provider_map.get(str(settings.S3_PROVIDER).lower(), S3Provider.AWS),
        endpoint_url=settings.S3_ENDPOINT_URL if settings.S3_ENDPOINT_URL else None,
        access_key=str(settings.S3_ACCESS_KEY) if settings.S3_ACCESS_KEY else "",
        secret_key=str(settings.S3_SECRET_KEY) if settings.S3_SECRET_KEY else "",
        region=str(settings.S3_REGION) if settings.S3_REGION else "us-east-1",
        bucket_name=str(settings.S3_BUCKET_NAME) if settings.S3_BUCKET_NAME else "",
        custom_domain=settings.S3_CUSTOM_DOMAIN if settings.S3_CUSTOM_DOMAIN else None,
        path_style=_parse_bool(settings.S3_PATH_STYLE),
        public_bucket=_parse_bool(settings.S3_PUBLIC_BUCKET),
        max_file_size=(int(settings.S3_MAX_FILE_SIZE) if settings.S3_MAX_FILE_SIZE else 10485760),
    )


async def get_or_init_storage():
    """Initialize and get storage service"""
    s3_enabled = get_s3_enabled()
    if s3_enabled:
        config = await get_s3_config_from_settings()
        await init_storage(config)
    return get_storage_service()


async def resolve_upload_limits(user_roles: list[str]) -> dict:
    """Resolve effective upload limits for a user based on their roles.

    Most permissive value across roles wins. Falls back to global settings.
    """
    from src.infra.role.storage import RoleStorage

    defaults = {
        "image": settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        "video": settings.FILE_UPLOAD_MAX_SIZE_VIDEO,
        "audio": settings.FILE_UPLOAD_MAX_SIZE_AUDIO,
        "document": settings.FILE_UPLOAD_MAX_SIZE_DOCUMENT,
        "maxFiles": settings.FILE_UPLOAD_MAX_FILES,
    }

    field_map = {
        "image": "max_file_size_image",
        "video": "max_file_size_video",
        "audio": "max_file_size_audio",
        "document": "max_file_size_document",
        "maxFiles": "max_files",
    }

    resolved = dict(defaults)
    role_overrides: dict[str, int] = {}

    try:
        role_storage = RoleStorage()
        for role_name in user_roles:
            role = await role_storage.get_by_name(role_name)
            if role and role.limits:
                for key, field_name in field_map.items():
                    value = getattr(role.limits, field_name, None)
                    if value is not None:
                        role_overrides[key] = max(role_overrides.get(key, value), value)

        # Only apply role overrides for fields where at least one role set a value
        resolved.update(role_overrides)
    except Exception as e:
        logger.warning(f"Failed to resolve role upload limits, using defaults: {e}")

    return resolved


@router.post("/file")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Upload a file to S3

    Requires: file:upload:{type} permission based on file type
    Files are stored in folders organized by user_id.

    Args:
        request: FastAPI request object (for base_url)
        file: File to upload
        current_user: Current authenticated user

    Returns:
        Upload result with URL and metadata
    """
    if not get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings in System Settings.",
        )

    storage = await get_or_init_storage()

    # Determine file category from filename and content_type (no need to read content)
    category = get_file_category(file.filename or "", file.content_type)
    permission = get_permission_for_category(category)

    # Check permission
    has_specific = False
    has_general = False

    if permission:
        has_specific = check_permission(current_user.permissions, permission)
    has_general = check_permission(current_user.permissions, "file:upload")

    if not (has_specific or has_general):
        category_label = category.value if category != FileCategory.UNKNOWN else "未知"
        raise HTTPException(
            status_code=403,
            detail=f"No permission to upload {category_label} files",
        )

    # Resolve per-role upload limits
    upload_limits = await resolve_upload_limits(current_user.roles)
    size_limits = {
        FileCategory.IMAGE: upload_limits["image"],
        FileCategory.VIDEO: upload_limits["video"],
        FileCategory.AUDIO: upload_limits["audio"],
        FileCategory.DOCUMENT: upload_limits["document"],
        FileCategory.UNKNOWN: 10,
    }
    max_size_mb = size_limits.get(category, 10)
    max_size_bytes = max_size_mb * 1024 * 1024

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_size_bytes:
                raise HTTPException(
                    status_code=400,
                    detail=f"File size exceeds maximum of {max_size_mb}MB",
                )
        except ValueError:
            pass

    # Validate file extension
    ext = (file.filename or "").lower().split(".")[-1]
    allowed_exts = FILE_EXTENSIONS.get(category, set())
    if category != FileCategory.UNKNOWN and ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' is not allowed for {category.value} files",
        )

    # Upload - stream file directly to S3 without buffering in memory
    # Upload - use user_id as folder
    try:
        result = await storage.upload_file(
            file=file.file,
            folder=current_user.sub,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            metadata={"uploaded_by": current_user.sub},
        )

        # 获取 base_url 并生成完整 URL
        base_url = str(request.base_url).rstrip("/")
        proxy_path = f"/api/upload/file/{result.key}"
        proxy_url = f"{base_url}{proxy_path}"

        return {
            "key": result.key,
            "url": proxy_url,
            "name": file.filename,
            "type": category.value,
            "mimeType": file.content_type,
            "size": result.size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def _get_image_content_type(data: bytes) -> str:
    """Detect image content type from binary data using magic bytes"""
    # Check magic bytes to detect image type
    # Safety check: ensure data is long enough for magic byte detection
    if len(data) < 2:
        return "image/png"  # Default for empty/very small data

    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif data[:2] == b"\xff\xd8":
        return "image/jpeg"
    elif len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    elif data[:2] in (b"BM", b"BA"):
        return "image/bmp"
    else:
        return "image/png"  # Default to PNG


@router.post("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
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


@router.delete("/avatar", dependencies=[Depends(require_permissions("avatar:upload"))])
async def delete_avatar(
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Delete user avatar

    Removes the avatar_url from the user's profile.
    Requires: avatar:upload permission

    Args:
        current_user: Current authenticated user

    Returns:
        Deletion status
    """
    try:
        from src.infra.user.storage import UserStorage
        from src.kernel.schemas.user import UserUpdate

        logger.info(f"Deleting avatar for user: {current_user.sub}")
        storage = UserStorage()
        await storage.update(
            current_user.sub,
            UserUpdate(avatar_url=None),
        )
        logger.info(f"Avatar deleted successfully for user: {current_user.sub}")

        return {"deleted": True}
    except Exception as e:
        logger.exception("Avatar deletion failed")
        raise HTTPException(status_code=500, detail=f"Avatar deletion failed: {str(e)}")


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
    if not get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings in System Settings.",
        )

    storage = await get_or_init_storage()

    # Async delete - return immediately, delete in background
    async def background_delete():
        try:
            await storage.delete_file(key)
            logger.info(f"Background delete completed for key: {key}")
        except Exception as e:
            logger.error(f"Background delete failed for key {key}: {e}")

    # Create task and return immediately (non-blocking)
    asyncio.create_task(background_delete())
    return {"deleted": True, "key": key, "status": "deleting"}


@router.get("/config")
async def get_storage_config(
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Get storage configuration status and file upload limits

    Returns effective upload limits for the current user based on their roles.
    Falls back to global settings if no role-specific limits are configured.

    Returns:
        Storage configuration and upload limits
    """
    s3_enabled = get_s3_enabled()

    # Resolve per-role upload limits for current user
    upload_limits = await resolve_upload_limits(current_user.roles)

    return {
        "enabled": s3_enabled,
        "provider": settings.S3_PROVIDER if s3_enabled else None,
        "uploadLimits": {
            "image": upload_limits["image"],
            "video": upload_limits["video"],
            "audio": upload_limits["audio"],
            "document": upload_limits["document"],
            "maxFiles": upload_limits["maxFiles"],
        },
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
    if not get_s3_enabled():
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
    if not get_s3_enabled():
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
    if not get_s3_enabled():
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


@router.get("/file/{key:path}")
async def get_file_proxy(
    key: str,
) -> Response:
    """
    Dynamic proxy endpoint for file access

    Generates a short-lived presigned URL and redirects to it.
    This ensures the URL never expires from the user's perspective.
    No authentication required - uses presigned URLs for access.

    Args:
        key: S3 object key

    Returns:
        302 redirect to presigned URL
    """
    if not get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled.",
        )

    storage = await get_or_init_storage()

    # Verify file exists
    try:
        exists = await storage.file_exists(key)
        if not exists:
            raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.warning(f"Failed to check file existence for {key}: {e}")
        # Continue anyway - let S3 handle the error

    # Generate short-lived presigned URL (5 minutes)
    try:
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, 300)  # 5 minutes
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    # Redirect to presigned URL
    return Response(
        status_code=302,
        headers={"Location": url},
    )

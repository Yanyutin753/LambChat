"""
File upload API routes

Provides endpoints for file uploads to S3-compatible storage.
"""

import hashlib
import uuid
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from fastapi import (
    APIRouter,
    Depends,
    File,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.file_type import (
    FILE_EXTENSIONS,
    FileCategory,
    get_file_category,
    get_permission_for_category,
)
from src.api.routes.upload_cover import get_file_cover_response
from src.api.routes.upload_signed_urls import (
    SignedUrlItem,
    SignedUrlRequest,
    SignedUrlResponse,
    get_signed_urls,
    get_single_signed_url,
)
from src.api.routes.upload_signed_urls import (
    router as signed_url_router,
)
from src.api.routes.upload_thumb import get_file_thumb_response
from src.infra.async_utils import run_blocking_io
from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.auth.rbac import check_permission
from src.infra.logging import get_logger
from src.infra.storage.s3 import (
    S3Config,
    S3Provider,
)
from src.infra.storage.s3.base import BinaryReadFile
from src.infra.upload.file_record import FileRecordStorage
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

__all__ = [
    "SignedUrlItem",
    "SignedUrlRequest",
    "SignedUrlResponse",
    "get_signed_urls",
    "get_single_signed_url",
]

_file_record_storage = FileRecordStorage()
_upload_delete_tasks = BestEffortTaskLimiter("upload delete", max_tasks=8)

UPLOAD_READ_CHUNK_SIZE = 1024 * 1024
UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024


async def drain_upload_delete_tasks() -> None:
    await _upload_delete_tasks.drain()


async def close_upload_route_dependencies() -> None:
    await drain_upload_delete_tasks()
    await _file_record_storage.close()


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


async def _get_live_record_by_hash(
    file_hash: str,
    uploaded_by: str,
    storage=None,
) -> dict | None:
    """Return a dedupe record only if both metadata and the backing file still exist."""
    record = await _file_record_storage.find_by_hash(file_hash, uploaded_by)
    if record is None:
        return None

    storage = storage or await get_or_init_storage()
    if await storage.file_exists(record["key"]):
        if await _file_record_storage.refresh_owned_cleanup(record["key"], uploaded_by):
            return record
        return None

    logger.warning(
        "Found stale file record for hash %s pointing to missing key %s",
        file_hash,
        record["key"],
    )
    await _file_record_storage.delete_by_hash(file_hash, uploaded_by)
    return None


def _get_base_url(request: Request) -> str:
    """获取 base_url：优先当前请求入口（X-Forwarded-Host/Host + X-Forwarded-Proto，
    多入口与重写 Host 的代理下 URL 跟随实际访问域名）；Host 不可用时回退
    APP_BASE_URL（后台任务生成 URL 的场景建议配置）。"""
    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host") or "").split(",")[0].strip()
    if host:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        if forwarded_proto:
            scheme = forwarded_proto
        elif forwarded_host:
            # 显式配置了 X-Forwarded-Host 却没透传 proto：视为经代理，TLS 通常
            # 终结在代理层，对齐 auth/_get_frontend_url 先例按 https 猜（本地除外）
            scheme = "http" if "localhost" in host or "127.0.0.1" in host else "https"
        else:
            # 无任何转发头视为直连：按连接实际 scheme，局域网/自签 http 直连
            # 不被误判成 https（官方 nginx 模板必传 X-Forwarded-Proto）
            scheme = request.url.scheme
        return f"{scheme}://{host}"
    app_base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if app_base_url:
        return app_base_url
    base_url = str(request.base_url).rstrip("/")
    return "" if base_url == "http://None" else base_url


def _build_upload_response(
    request: Request,
    *,
    key: str,
    name: str,
    file_type: str,
    mime_type: str,
    size: int,
    exists: bool = False,
) -> dict:
    """Build a normalized upload response payload."""
    base_url = _get_base_url(request)
    proxy_url = f"{base_url}/api/upload/file/{key}"
    payload = {
        "key": key,
        "url": proxy_url,
        "name": name,
        "type": file_type,
        "mime_type": mime_type,
        "size": size,
    }
    if exists:
        payload["exists"] = True
    return payload


def _avatar_object_key_from_url(avatar_url: str | None, user_id: str) -> str | None:
    if not avatar_url:
        return None

    parsed = urlsplit(avatar_url)
    path = unquote(parsed.path or avatar_url)
    proxy_prefix = "/api/upload/file/"
    if proxy_prefix in path:
        key = path.split(proxy_prefix, 1)[1]
    else:
        key = path.lstrip("/")

    owned_prefix = f"avatars/{user_id}/"
    if key.startswith(owned_prefix):
        return key
    return None


async def _delete_avatar_object_if_owned(
    storage: Any,
    user_id: str,
    avatar_url: str | None,
    *,
    keep_key: str | None = None,
) -> None:
    key = _avatar_object_key_from_url(avatar_url, user_id)
    if key is None or key == keep_key:
        return

    try:
        await storage.delete_file(key)
    except Exception as e:
        logger.warning("Failed to delete previous avatar object %s: %s", key, e, exc_info=True)


def _path_exists(file_path) -> bool:
    return file_path.exists()


async def _get_file_response_metadata(key: str) -> tuple[str | None, str]:
    record = await _file_record_storage.find_by_key(key)
    filename_for_disposition = record["name"] if record else None
    content_type = record["mime_type"] if record and record.get("mime_type") else None

    if not content_type:
        import mimetypes

        content_type, _ = mimetypes.guess_type(key)
        if not content_type:
            content_type = "application/octet-stream"

    return filename_for_disposition, content_type


async def _read_upload_file_limited(
    file: Any,
    *,
    max_size_bytes: int,
    max_size_mb: int,
    purpose: str = "File",
    chunk_size: int = UPLOAD_READ_CHUNK_SIZE,
) -> bytes:
    """Read an UploadFile in chunks and stop as soon as the configured limit is exceeded."""
    data = bytearray()
    total_size = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break

        total_size += len(chunk)
        if total_size > max_size_bytes:
            raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": max_size_mb})
        data.extend(chunk)

    return bytes(data)


class UploadSpool(BinaryReadFile, Protocol):
    def close(self) -> None: ...


@dataclass
class SpooledUpload:
    file: UploadSpool
    sha256_hex: str
    size: int

    def close(self) -> None:
        self.file.close()


async def _spool_upload_file_limited(
    file: Any,
    *,
    max_size_bytes: int,
    max_size_mb: int,
    purpose: str = "File",
    chunk_size: int = UPLOAD_READ_CHUNK_SIZE,
) -> SpooledUpload:
    """Stream an UploadFile into a bounded spool while hashing and enforcing size limits."""
    digest = hashlib.sha256()
    total_size = 0
    spooled = SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_LIMIT, mode="w+b")

    try:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > max_size_bytes:
                raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": max_size_mb})
            digest.update(chunk)
            await run_blocking_io(spooled.write, chunk)

        if total_size == 0:
            raise AppError(ErrorCode.EMPTY_FILE)

        await run_blocking_io(spooled.seek, 0)
        return SpooledUpload(file=spooled, sha256_hex=digest.hexdigest(), size=total_size)
    except Exception:
        spooled.close()
        raise


def get_s3_enabled() -> bool:
    """Get S3 enabled status from cached settings"""
    return _parse_bool(settings.S3_ENABLED)


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
        "local": S3Provider.LOCAL,
    }

    storage_path = getattr(settings, "LOCAL_STORAGE_PATH", "./uploads") or "./uploads"

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
        internal_max_upload_size=(
            int(settings.S3_INTERNAL_UPLOAD_MAX_SIZE)
            if settings.S3_INTERNAL_UPLOAD_MAX_SIZE
            else 1024 * 1024 * 1024
        ),
        presigned_url_expires=(
            int(settings.S3_PRESIGNED_URL_EXPIRES)
            if settings.S3_PRESIGNED_URL_EXPIRES
            else 7 * 24 * 3600
        ),
        storage_path=storage_path,
    )


async def get_or_init_storage():
    """Initialize and get storage service (re-exported from infra layer)"""
    from src.infra.storage.s3.service import get_or_init_storage as _get_or_init

    return await _get_or_init()


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


class FileCheckRequest(BaseModel):
    hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 hex digest")
    size: int = Field(..., gt=0, description="File size in bytes")
    name: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")


@router.post("/check")
async def check_file_exists(
    request: Request,
    body: FileCheckRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    storage = await get_or_init_storage()
    record = await _get_live_record_by_hash(body.hash, current_user.sub, storage)
    if record is None:
        return {"exists": False}
    base_url = _get_base_url(request)
    return {
        "exists": True,
        "key": record["key"],
        "url": f"{base_url}/api/upload/file/{record['key']}",
        "name": record["name"],
        "type": record["category"],
        "mime_type": record["mime_type"],
        "size": record["size"],
    }


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
        raise AppError(ErrorCode.FILE_UPLOAD_NO_PERMISSION, args={"category": category_label})

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
                raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": max_size_mb})
        except ValueError:
            pass

    # Validate file extension
    ext = (file.filename or "").lower().split(".")[-1]
    allowed_exts = FILE_EXTENSIONS.get(category, set())
    if category != FileCategory.UNKNOWN and ext not in allowed_exts:
        raise AppError(
            ErrorCode.FILE_EXTENSION_NOT_ALLOWED, args={"ext": ext, "category": category.value}
        )

    spooled_upload: SpooledUpload | None = None
    storage_key = ""
    file_hash = ""
    try:
        spooled_upload = await _spool_upload_file_limited(
            file,
            max_size_bytes=max_size_bytes,
            max_size_mb=max_size_mb,
        )
        file_hash = spooled_upload.sha256_hex

        # Check if hash already exists (race condition guard)
        existing = await _get_live_record_by_hash(file_hash, current_user.sub, storage)
        if existing:
            return _build_upload_response(
                request,
                key=existing["key"],
                name=existing["name"],
                file_type=existing["category"],
                mime_type=existing["mime_type"],
                size=existing["size"],
                exists=True,
            )

        # Upload with short key organized by category and user
        short_id = uuid.uuid4().hex[:16]
        ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else ""
        storage_key = (
            f"{category.value}/{current_user.sub}/{short_id}.{ext}"
            if ext
            else f"{category.value}/{current_user.sub}/{short_id}"
        )
        upload_result = await storage.upload_stream_to_key(
            file=spooled_upload.file,
            key=storage_key,
            content_type=file.content_type,
            metadata={"uploaded_by": current_user.sub, "content_hash": file_hash},
            skip_size_limit=True,
        )
        storage_key = upload_result.key

        # Write file record
        await _file_record_storage.create(
            file_hash=file_hash,
            key=storage_key,
            name=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
            size=spooled_upload.size,
            category=category.value,
            uploaded_by=current_user.sub,
        )

        return _build_upload_response(
            request,
            key=storage_key,
            name=file.filename or "unknown",
            file_type=category.value,
            mime_type=file.content_type or "application/octet-stream",
            size=spooled_upload.size,
        )
    except DuplicateKeyError as duplicate_error:
        logger.info("Duplicate upload detected for hash %s, reusing existing file", file_hash)

        existing = await _get_live_record_by_hash(file_hash, current_user.sub, storage)
        duplicate_pattern = (duplicate_error.details or {}).get("keyPattern", {})
        is_owner_hash_conflict = duplicate_pattern == {"uploaded_by": 1, "hash": 1}
        try:
            if storage_key and is_owner_hash_conflict:
                await storage.delete_file(storage_key)
        except Exception as cleanup_error:
            logger.warning(
                "Failed to delete duplicate uploaded object %s after dedupe race: %s",
                storage_key,
                cleanup_error,
            )

        if existing:
            return _build_upload_response(
                request,
                key=existing["key"],
                name=existing["name"],
                file_type=existing["category"],
                mime_type=existing["mime_type"],
                size=existing["size"],
                exists=True,
            )

        raise AppError(ErrorCode.UPLOAD_DUPLICATE_CONFLICT)
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.UPLOAD_FAILED, message=str(e))
    finally:
        if spooled_upload is not None:
            spooled_upload.close()


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

    Avatar is stored in object storage and referenced by URL.

    Requires: file:upload permission

    Args:
        file: Avatar image file
        current_user: Current authenticated user

    Returns:
        Avatar data URI
    """
    # Validate file type
    allowed_image_extensions = ["jpg", "jpeg", "png", "gif", "webp"]
    ext = (
        (file.filename or "avatar.png").lower().split(".")[-1]
        if "." in (file.filename or "")
        else ""
    )
    if ext not in allowed_image_extensions:
        raise AppError(
            ErrorCode.FILE_TYPE_NOT_ALLOWED,
            args={"ext": ext, "allowed": ", ".join(allowed_image_extensions)},
        )

    # Validate file size (max 2MB for avatar)
    max_size = 2 * 1024 * 1024  # 2MB
    spooled_upload = await _spool_upload_file_limited(
        file,
        max_size_bytes=max_size,
        max_size_mb=2,
        purpose="Avatar file",
    )

    try:
        header = await run_blocking_io(spooled_upload.file.read, 12)
        content_type = _get_image_content_type(header)
        await run_blocking_io(spooled_upload.file.seek, 0)
    except Exception:
        spooled_upload.close()
        raise

    try:
        from src.infra.user.storage import UserStorage
        from src.kernel.schemas.user import UserUpdate

        storage = await get_or_init_storage()
        upload_result = await storage.upload_file(
            file=spooled_upload.file,
            folder=f"avatars/{current_user.sub}",
            filename=file.filename or "avatar.png",
            content_type=content_type,
            skip_size_limit=True,
        )
        avatar_url = upload_result.url or f"/api/upload/file/{upload_result.key}"

        logger.info(f"Uploading avatar for user: {current_user.sub}, filename: {file.filename}")
        user_storage = UserStorage()
        previous_user = await user_storage.get_by_id(current_user.sub)
        previous_avatar_url = getattr(previous_user, "avatar_url", None)
        await user_storage.update(
            current_user.sub,
            UserUpdate(avatar_url=avatar_url),
        )
        await _delete_avatar_object_if_owned(
            storage,
            current_user.sub,
            previous_avatar_url,
            keep_key=upload_result.key,
        )
        logger.info(f"Avatar uploaded successfully for user: {current_user.sub}")

        return {
            "url": avatar_url,
            "size": spooled_upload.size,
            "content_type": content_type,
        }
    except Exception as e:
        logger.exception("Avatar upload failed")
        raise AppError(ErrorCode.AVATAR_UPLOAD_FAILED, message=str(e))
    finally:
        spooled_upload.close()


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
        user_storage = UserStorage()
        previous_user = await user_storage.get_by_id(current_user.sub)
        previous_avatar_url = getattr(previous_user, "avatar_url", None)
        await user_storage.update(
            current_user.sub,
            UserUpdate(avatar_url=None),
        )
        object_storage = await get_or_init_storage()
        await _delete_avatar_object_if_owned(
            object_storage,
            current_user.sub,
            previous_avatar_url,
        )
        logger.info(f"Avatar deleted successfully for user: {current_user.sub}")

        return {"deleted": True}
    except Exception as e:
        logger.exception("Avatar deletion failed")
        raise AppError(ErrorCode.AVATAR_DELETE_FAILED, message=str(e))


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
    record = await _file_record_storage.find_by_key(key, current_user.sub)
    if record is None:
        raise AppError(ErrorCode.FILE_NOT_FOUND)

    if record.get("reference_count", 0) > 0:
        logger.info("Preserving referenced file %s during delete request", key)
        return {"deleted": False, "key": key, "status": "preserved"}

    if not await _file_record_storage.schedule_owned_cleanup(key, current_user.sub):
        raise AppError(ErrorCode.FILE_NOT_FOUND)

    logger.info("Scheduled unreferenced file %s for delayed cleanup", key)
    return {"deleted": False, "key": key, "status": "scheduled"}


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
        "enabled": True,  # Always enabled (local storage as fallback)
        "provider": settings.S3_PROVIDER if s3_enabled else "local",
        "uploadLimits": {
            "image": upload_limits["image"],
            "video": upload_limits["video"],
            "audio": upload_limits["audio"],
            "document": upload_limits["document"],
            "maxFiles": upload_limits["maxFiles"],
        },
    }


router.include_router(signed_url_router)


@router.get("/file/{key:path}")
async def get_file_proxy(
    key: str,
    request: Request,
    direct: bool = False,
    proxy: bool = False,
    cover: bool = False,
    thumb: bool = False,
    t: int | None = None,
) -> Response:
    """
    Dynamic proxy endpoint for file access

    For S3 storage: generates a short-lived presigned URL and redirects.
    For local storage: serves the file directly.
    No authentication required.

    Query params:
        direct: If true, return the URL as JSON instead of redirecting.
        proxy: If true, stream non-local storage through the app instead of redirecting.
        cover: If true, serve a 16:9 cover thumbnail instead of the original
            (OSS image crop / video first frame; local storage via Pillow).
            Unsupported types return 404 so clients fall back without
            downloading the original file.
        thumb: If true, serve an aspect-fit chat thumbnail instead of the
            original (OSS m_lfit resize; local/Pillow; other S3 providers
            render once and cache beside the original). Unsupported types
            return 404 so clients fall back to the original.
        t: Video snapshot timestamp in ms for cover (default 1000).
    """
    from fastapi.responses import JSONResponse

    storage = await get_or_init_storage()

    if cover:
        return await get_file_cover_response(storage, key, t)

    if thumb:
        return await get_file_thumb_response(storage, key)

    base_url = _get_base_url(request)
    proxy_url = f"{base_url}/api/upload/file/{key}"

    # Local storage: serve file directly with FileResponse (native Range/sendfile support)
    if storage.is_local:
        if direct:
            return JSONResponse({"url": proxy_url})
        try:
            file_path = storage.get_file_path(key)
            if not await run_blocking_io(_path_exists, file_path):
                raise AppError(ErrorCode.FILE_NOT_FOUND)

            filename_for_disposition, content_type = await _get_file_response_metadata(key)

            return FileResponse(
                path=str(file_path),
                media_type=content_type,
                filename=filename_for_disposition,
                content_disposition_type="inline",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except AppError:
            raise
        except Exception as e:
            logger.error(f"Failed to serve local file {key}: {e}")
            raise AppError(ErrorCode.FILE_READ_FAILED)

    # S3 storage: redirect to presigned URL
    try:
        exists = await storage.file_exists(key)
        if not exists:
            raise AppError(ErrorCode.FILE_NOT_FOUND)
    except AppError:
        raise
    except Exception as e:
        logger.warning(f"Failed to check file existence for {key}: {e}")

    if proxy:
        filename_for_disposition, content_type = await _get_file_response_metadata(key)
        headers = {"Cache-Control": "public, max-age=300"}
        if filename_for_disposition:
            headers["Content-Disposition"] = f'inline; filename="{filename_for_disposition}"'

        return StreamingResponse(
            storage.download_stream(key),
            media_type=content_type,
            headers=headers,
        )

    try:
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, 300)
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {key}: {e}")
        raise AppError(ErrorCode.FILE_URL_FAILED)

    if direct:
        return JSONResponse({"url": url})

    return Response(
        status_code=302,
        headers={
            "Location": url,
            "Cache-Control": "public, max-age=300",
        },
    )

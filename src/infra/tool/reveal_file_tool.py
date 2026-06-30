"""
Reveal File 工具

让 Agent 可以向用户展示/推荐文件，前端会自动展开文件树并可以点击查看内容。
文件会自动从 backend 下载并上传到 S3，返回 S3 URL。

统一通过 download_files 获取原始文件内容（沙箱/非沙箱均适用）。
非沙箱模式下，若 backend 下载失败，会回退到直接读取本地文件系统。

返回格式与前端 UploadResult 一致：
{
    "key": "...",
    "url": "...",
    "name": "...",
    "type": "image" | "video" | "audio" | "document",
    "mime_type": "...",
    "size": ...
}

分布式安全设计：
- 不依赖 ContextVar（无法跨进程/Worker 工作）
- 通过 ToolRuntime 注入 backend
- 使用 asyncio.Lock 防止并发初始化
"""

import inspect
import json
import mimetypes
import os
import re
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, Literal, Optional
from urllib.parse import unquote, urlparse

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.logging.context import TraceContext
from src.infra.revealed_file.storage import get_revealed_file_storage
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_delivery_source_from_runtime,
    get_session_id_from_runtime,
    get_trace_id_from_runtime,
    get_user_id_from_runtime,
)
from src.kernel.config import settings

logger = get_logger(__name__)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


_UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024
_LOCAL_REF_RESOLUTION_MAX_BYTES = 2 * 1024 * 1024
_LOCAL_REF_UPLOAD_LIMIT = 20
_DEFAULT_REVEAL_FILE_UPLOAD_MAX_BYTES = 50 * 1024 * 1024

# 文件类型分类
FileCategory = Literal["image", "video", "audio", "document"]

# MIME 类型到文件类别的映射
MIME_TYPE_CATEGORIES: dict[str, FileCategory] = {
    # 图片
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "image/svg+xml": "image",
    "image/bmp": "image",
    "image/x-icon": "image",
    # 视频
    "video/mp4": "video",
    "video/mpeg": "video",
    "video/webm": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video",
    "video/x-ms-wmv": "video",
    # 音频
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/ogg": "audio",
    "audio/aac": "audio",
    "audio/flac": "audio",
    "audio/x-m4a": "audio",
}


def get_file_category(mime_type: str) -> FileCategory:
    """根据 MIME 类型获取文件类别"""
    if mime_type in MIME_TYPE_CATEGORIES:
        return MIME_TYPE_CATEGORIES[mime_type]

    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"

    return "document"


def get_mime_type(filename: str) -> str:
    """根据文件名获取 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def _is_sandbox_backend(backend: Any) -> bool:
    """判断 backend 是否为沙箱类型（支持 shell 命令执行）"""
    return hasattr(backend, "execute") or hasattr(backend, "aexecute")


def _local_filesystem_fallback_enabled() -> bool:
    """Whether non-sandbox reveal flows may read from the process filesystem."""
    return bool(getattr(settings, "ENABLE_LOCAL_FILESYSTEM_FALLBACK", True))


def _can_resolve_local_filesystem_refs(file_path: str) -> bool:
    """Only materialize small local text files for best-effort reference rewriting."""
    try:
        return os.path.getsize(file_path) <= _LOCAL_REF_RESOLUTION_MAX_BYTES
    except OSError:
        return False


def _get_local_ref_upload_limit() -> int:
    return max(int(_LOCAL_REF_UPLOAD_LIMIT), 1)


def _get_reveal_file_upload_max_bytes() -> int:
    configured = getattr(
        settings,
        "S3_INTERNAL_UPLOAD_MAX_SIZE",
        _DEFAULT_REVEAL_FILE_UPLOAD_MAX_BYTES,
    )
    return max(int(configured or _DEFAULT_REVEAL_FILE_UPLOAD_MAX_BYTES), 1)


def _coerce_file_size(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


async def _lookup_session_project_id(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        from src.infra.storage.mongodb import get_mongo_client
        from src.kernel.config import settings

        mongo_client = get_mongo_client()
        db = mongo_client[settings.MONGODB_DB]
        session_doc = await db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
            {"session_id": session_id}, {"metadata.project_id": 1}
        )
        if session_doc:
            return (session_doc.get("metadata") or {}).get("project_id")
    except Exception:
        pass
    return None


async def _index_revealed_file(
    *,
    runtime: ToolRuntime | None,
    file_name: str,
    file_category: FileCategory,
    mime_type: str,
    file_size: int,
    url: str,
    file_key: str,
    description: str,
    original_path: str,
) -> None:
    try:
        req_ctx = TraceContext.get_request_context()
        user_id = req_ctx.user_id or get_user_id_from_runtime(runtime)
        if not user_id:
            logger.info("[reveal_file] Skipping revealed file index: no user_id available")
            return

        session_id = req_ctx.session_id or get_session_id_from_runtime(runtime)
        trace_id = (
            req_ctx.trace_id
            or TraceContext.get().trace_id
            or get_trace_id_from_runtime(runtime)
            or ""
        )
        session_project_id = await _lookup_session_project_id(session_id)
        delivery_source = get_delivery_source_from_runtime(runtime)
        data: dict[str, Any] = {
            "file_type": file_category,
            "mime_type": mime_type,
            "file_size": file_size,
            "url": url,
            "session_id": session_id,
            "project_id": session_project_id,
            "description": description,
            "original_path": original_path,
        }
        if delivery_source:
            data["delivery_source"] = delivery_source

        storage_index = get_revealed_file_storage()
        await storage_index.upsert_by_name(
            user_id=user_id,
            file_name=file_name,
            source="reveal_file",
            file_key=file_key,
            trace_id=trace_id,
            data=data,
        )
    except Exception as idx_err:
        logger.warning(f"[reveal_file] Failed to index revealed file: {idx_err}")


async def _get_backend_file_size(backend: Any, file_path: str) -> int | None:
    async_method = getattr(backend, "aget_file_size", None)
    if callable(async_method):
        try:
            size = async_method(file_path)
            if inspect.isawaitable(size):
                size = await size
            return _coerce_file_size(size)
        except Exception as e:
            logger.debug(f"[reveal_file] aget_file_size failed for {file_path}: {e}")

    sync_method = getattr(backend, "get_file_size", None)
    if callable(sync_method):
        try:
            return _coerce_file_size(await run_blocking_io(sync_method, file_path))
        except Exception as e:
            logger.debug(f"[reveal_file] get_file_size failed for {file_path}: {e}")

    private_method = getattr(backend, "_file_size", None)
    if callable(private_method):
        try:
            return _coerce_file_size(await run_blocking_io(private_method, file_path))
        except Exception as e:
            logger.debug(f"[reveal_file] _file_size failed for {file_path}: {e}")

    return None


async def _get_storage():
    """获取已初始化的 storage 服务（复用 upload 模块的初始化逻辑）"""
    from src.infra.storage.s3.service import get_or_init_storage

    return await get_or_init_storage()


async def _download_file_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """
    通过 download_files 从 backend 获取原始文件内容。

    沙箱（DaytonaBackend）和非沙箱（StateBackend/StoreBackend）均支持 download_files，
    返回原始字节，不包含行号等格式化内容。
    """
    logger.info(f"[reveal_file] Attempting to download: {file_path}")

    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses:
                resp = responses[0]
                logger.info(
                    f"[reveal_file] adownload_files response: path={resp.path}, error={resp.error}, content_len={len(resp.content) if resp.content else 0}"
                )
                if resp.content:
                    return resp.content
                elif resp.error:
                    logger.warning(f"[reveal_file] Download error: {resp.error}")
        except Exception as e:
            logger.warning(f"[reveal_file] adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            responses = await run_blocking_io(backend.download_files, [file_path])
            if responses:
                resp = responses[0]
                logger.info(
                    f"[reveal_file] download_files response: path={resp.path}, error={resp.error}, content_len={len(resp.content) if resp.content else 0}"
                )
                if resp.content:
                    return resp.content
                elif resp.error:
                    logger.warning(f"[reveal_file] Download error: {resp.error}")
        except Exception as e:
            logger.warning(f"[reveal_file] download_files failed for {file_path}: {e}")

    return None


async def _read_file_from_filesystem(file_path: str) -> Optional[bytes]:
    """非沙箱模式下的兜底：直接从本地文件系统读取文件内容"""
    try:

        def _read_small_file() -> Optional[bytes]:
            if not os.path.isfile(file_path):
                return None
            if os.path.getsize(file_path) > _LOCAL_REF_RESOLUTION_MAX_BYTES:
                logger.warning(
                    "[reveal_file] Skipping filesystem fallback read for large file: %s",
                    file_path,
                )
                return None
            with open(file_path, "rb") as file:
                return file.read()

        content = await run_blocking_io(_read_small_file)
        if content is not None:
            return content
        logger.debug(f"[reveal_file] File not found on filesystem: {file_path}")
    except Exception as e:
        logger.warning(f"[reveal_file] Failed to read from filesystem: {file_path}: {e}")
    return None


def _is_file_path(file_path: str) -> bool:
    return os.path.isfile(file_path)


async def _upload_filesystem_file(
    file_path: str,
    storage: Any,
    filename: str,
    mime_type: str,
):
    """Upload a local file handle directly without materializing it as bytes."""

    def _open_file():
        return open(file_path, "rb")

    file = await run_blocking_io(_open_file)
    try:
        return await storage.upload_file(
            file=file,
            folder="revealed_files",
            filename=filename,
            content_type=mime_type,
            skip_size_limit=True,
        )
    finally:
        await run_blocking_io(file.close)


# ---------------------------------------------------------------------------
# 本地资源引用检测与替换
# ---------------------------------------------------------------------------

# 需要处理的文件扩展名（这些文件类型可能引用本地资源）
_RESOLVABLE_EXTENSIONS = {".md", ".markdown", ".html", ".htm", ".svg", ".xhtml"}

# 可上传的资源扩展名（图片、视频、音频）
_UPLOADABLE_EXTENSIONS = {
    # 图片
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".ico",
    ".avif",
    # 视频
    ".mp4",
    ".webm",
    ".mov",
    ".avi",
    ".wmv",
    ".mkv",
    ".ogv",
    # 音频
    ".mp3",
    ".wav",
    ".ogg",
    ".aac",
    ".flac",
    ".m4a",
    ".opus",
}

# 正则模式
_RE_MD_LINK = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")  # ![alt](path)
_RE_HTML_SRC = re.compile(
    r'<(img|video|audio|source|iframe)\b[^>]*(?:src|href)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_CSS_URL = re.compile(r'url\(["\']?([^)"\']+)["\']?\)')  # CSS url()
_RE_SVG_IMAGE = re.compile(r'<image\b[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)


def _is_local_path(path: str) -> bool:
    """判断路径是否为本地文件路径（非 http/https/data URL）"""
    stripped = path.strip()
    return (
        not stripped.startswith("http://")
        and not stripped.startswith("https://")
        and not stripped.startswith("data:")
        and not stripped.startswith("#")
        and not stripped.startswith("blob:")
        and not stripped.startswith("mailto:")
    )


def _is_remote_url(path: str) -> bool:
    """判断路径是否为可直接返回的远程 URL"""
    parsed = urlparse(path.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _get_filename_from_path(path: str) -> str:
    """从本地路径或 URL 中提取文件名。"""
    if _is_remote_url(path):
        parsed = urlparse(path.strip())
        candidate = os.path.basename(unquote(parsed.path))
        if candidate:
            return candidate

    candidate = os.path.basename(path.rstrip("/"))
    return candidate or path


def _is_uploadable_resource(path: str) -> bool:
    """判断路径是否指向可上传的资源文件"""
    # 去掉 query string / fragment
    clean = path.split("?")[0].split("#")[0]
    ext = os.path.splitext(clean)[1].lower()
    return ext in _UPLOADABLE_EXTENSIONS


def _needs_local_ref_resolution(filename: str, mime_type: str) -> bool:
    """判断文件是否需要做本地引用替换"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in _RESOLVABLE_EXTENSIONS:
        return True
    if mime_type in ("text/markdown", "text/x-markdown", "text/html", "image/svg+xml"):
        return True
    return False


async def _upload_local_resource(
    local_path: str,
    file_dir: str,
    backend: Any,
    storage: Any,
    base_url: str,
) -> Optional[str]:
    """
    尝试下载并上传一个本地资源文件到 S3，返回 proxy URL。
    失败时返回 None。
    """
    try:
        if os.path.isabs(local_path):
            abs_path = local_path
        else:
            abs_path = os.path.normpath(os.path.join(file_dir, local_path))

        content = await _download_file_from_backend(backend, abs_path)
        if (
            content is None
            and not _is_sandbox_backend(backend)
            and _local_filesystem_fallback_enabled()
        ):
            if not await run_blocking_io(_is_file_path, abs_path):
                return None
            res_filename = os.path.basename(abs_path)
            res_mime = get_mime_type(res_filename)
            upload_result = await _upload_filesystem_file(
                abs_path,
                storage,
                res_filename,
                res_mime,
            )
            url = f"{base_url}/api/upload/file/{upload_result.key}"
            logger.info(f"[reveal_file] Uploaded local resource {local_path} -> {url}")
            return url
        if content is None:
            return None

        res_filename = os.path.basename(abs_path)
        res_mime = get_mime_type(res_filename)
        with SpooledTemporaryFile(
            max_size=_UPLOAD_SPOOL_MEMORY_LIMIT,
            mode="w+b",
        ) as spooled:
            await run_blocking_io(spooled.write, content)
            del content
            await run_blocking_io(spooled.seek, 0)
            upload_result = await storage.upload_file(
                file=spooled,
                folder="revealed_files",
                filename=res_filename,
                content_type=res_mime,
                skip_size_limit=True,
            )
        url = f"{base_url}/api/upload/file/{upload_result.key}"
        logger.info(f"[reveal_file] Uploaded local resource {local_path} -> {url}")
        return url
    except Exception as e:
        logger.warning(f"[reveal_file] Failed to upload local resource {local_path}: {e}")
        return None


async def _resolve_local_references(
    content: bytes,
    file_dir: str,
    backend: Any,
    storage: Any,
    base_url: str,
) -> bytes:
    """
    检测并替换文本内容中的本地资源引用（图片、视频、音频）为 S3 URL。
    支持 Markdown、HTML、SVG、CSS 等文件类型。

    作为兜底机制：agent 提示词已要求它主动上传资源并使用 URL，
    此函数用于捕获遗漏的本地引用。
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    # 收集所有需要上传的本地资源路径（保持原始大小写用于替换，但去重时不区分）
    seen_normalized = set()
    unique_paths: list[str] = []

    for pattern in (_RE_MD_LINK, _RE_HTML_SRC, _RE_SVG_IMAGE, _RE_CSS_URL):
        for match in pattern.finditer(text):
            # 不同 pattern 的路径在不同 group
            path = (
                match.group(2).strip()
                if match.lastindex and match.lastindex >= 2
                else match.group(1).strip()
            )
            if _is_local_path(path) and _is_uploadable_resource(path):
                normalized = os.path.normpath(path)
                if normalized not in seen_normalized:
                    seen_normalized.add(normalized)
                    unique_paths.append(path)

    if not unique_paths:
        return content
    upload_limit = _get_local_ref_upload_limit()
    if len(unique_paths) > upload_limit:
        logger.warning(
            "[reveal_file] Found %s local resource references; only uploading first %s",
            len(unique_paths),
            upload_limit,
        )
        unique_paths = unique_paths[:upload_limit]

    logger.info(
        f"[reveal_file] Found {len(unique_paths)} local resource reference(s), "
        f"uploading to S3 as fallback"
    )

    # 批量上传
    path_to_url: dict[str, str] = {}
    for ref_path in unique_paths:
        url = await _upload_local_resource(ref_path, file_dir, backend, storage, base_url)
        if url:
            path_to_url[ref_path] = url

    if not path_to_url:
        return content

    # 替换所有匹配到的本地路径
    def _replacer(match: re.Match) -> str:
        original = match.group(0)
        for group_idx in (1, 2):
            if match.lastindex is not None and group_idx <= match.lastindex:
                path = (
                    match.group(group_idx).strip()
                    if match.lastindex and match.lastindex >= group_idx
                    else ""
                )
                if path in path_to_url:
                    return original.replace(path, path_to_url[path], 1)
        return original

    for pattern in (_RE_MD_LINK, _RE_HTML_SRC, _RE_SVG_IMAGE, _RE_CSS_URL):
        text = pattern.sub(_replacer, text)

    return text.encode("utf-8")


@tool
async def reveal_file(
    file_path: Annotated[
        str, "要展示的文件路径（本地绝对路径、相对路径，或可直接访问的 http(s) URL）"
    ],
    description: Annotated[
        Optional[str], "对文件内容的简要描述，帮助用户理解为什么要查看这个文件"
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    向用户展示/推荐一个文件

    用户要求查看、打开、显示文件时，必须调用此工具。
    只回复文件路径或文件名是不够的。
    用户无法直接访问隔离环境中的文件系统，`reveal_file` 才会把文件真正暴露给前端界面。

    当你想让用户查看某个文件时，使用此工具。
    前端自动给用户显示可点击的文件。

    Args:
        file_path: 要展示的文件路径（本地绝对路径、相对路径，或可直接访问的 http(s) URL）
        description: 对文件内容的简要描述，帮助用户理解为什么要查看这个文件（可选）

    Returns:
        JSON 格式的结果，包含文件信息
    """
    if _is_remote_url(file_path):
        filename = _get_filename_from_path(file_path)
        mime_type = get_mime_type(filename)
        file_category = get_file_category(mime_type)
        remote_result = {
            "key": file_path,
            "url": file_path,
            "name": filename,
            "type": file_category,
            "mime_type": mime_type,
            "size": 0,
            "_meta": {
                "path": file_path,
                "description": description or "",
                "source": "remote_url",
            },
        }
        await _index_revealed_file(
            runtime=runtime,
            file_name=filename,
            file_category=file_category,
            mime_type=mime_type,
            file_size=0,
            url=file_path,
            file_key=file_path,
            description=description or "",
            original_path=file_path,
        )
        return await _json_dumps_result(remote_result)

    storage = await _get_storage()

    backend = get_backend_from_runtime(runtime)

    if backend is None:
        logger.warning("Backend not available from runtime, returning raw path")
        backend_unavailable_result: dict[str, Any] = {
            "type": "file_reveal",
            "file": {
                "path": file_path,
                "description": description or "",
            },
        }
        return await _json_dumps_result(backend_unavailable_result)

    try:
        known_size = await _get_backend_file_size(backend, file_path)
        max_upload_bytes = _get_reveal_file_upload_max_bytes()
        if known_size is not None and known_size > max_upload_bytes:
            logger.warning(
                "[reveal_file] Refusing oversized backend file before download: %s size=%s max=%s",
                file_path,
                known_size,
                max_upload_bytes,
            )
            too_large_result = {
                "type": "file_reveal",
                "file": {
                    "path": file_path,
                    "description": description or "",
                    "error": "file_too_large",
                    "size": known_size,
                    "max_size": max_upload_bytes,
                },
            }
            return await _json_dumps_result(too_large_result)

        file_content = await _download_file_from_backend(backend, file_path)
        use_filesystem_stream = False
        if file_content is not None and len(file_content) > max_upload_bytes:
            content_size = len(file_content)
            del file_content
            logger.warning(
                "[reveal_file] Refusing oversized backend file after download: %s size=%s max=%s",
                file_path,
                content_size,
                max_upload_bytes,
            )
            too_large_result = {
                "type": "file_reveal",
                "file": {
                    "path": file_path,
                    "description": description or "",
                    "error": "file_too_large",
                    "size": content_size,
                    "max_size": max_upload_bytes,
                },
            }
            return await _json_dumps_result(too_large_result)

        # 非沙箱模式兜底：backend 下载失败时尝试直接读取本地文件系统
        if (
            file_content is None
            and not _is_sandbox_backend(backend)
            and _local_filesystem_fallback_enabled()
        ):
            logger.info(
                f"[reveal_file] Backend download failed, trying filesystem fallback for {file_path}"
            )
            use_filesystem_stream = await run_blocking_io(_is_file_path, file_path)

        if file_content is None and not use_filesystem_stream:
            logger.error(f"Failed to read file {file_path} from backend")
            missing_file_result = {
                "type": "file_reveal",
                "file": {
                    "path": file_path,
                    "description": description or "",
                    "error": "file_not_found_or_empty",
                },
            }
            return await _json_dumps_result(missing_file_result)

        filename = _get_filename_from_path(file_path)
        mime_type = get_mime_type(filename)

        # 对可包含本地资源引用的文件（Markdown、HTML、SVG 等），兜底替换本地路径
        base_url = get_base_url_from_runtime(runtime)
        if not base_url:
            logger.warning("[reveal_file] base_url is empty, URL may be incomplete")

        if _needs_local_ref_resolution(filename, mime_type) and (
            file_content is not None
            or not use_filesystem_stream
            or _can_resolve_local_filesystem_refs(file_path)
        ):
            if file_content is None and use_filesystem_stream:
                file_content = await _read_file_from_filesystem(file_path)
            if file_content is None:
                raise ValueError(f"Unable to read file content for {file_path}")
            file_dir = os.path.dirname(file_path)
            file_content = await _resolve_local_references(
                file_content, file_dir, backend, storage, base_url
            )
            use_filesystem_stream = False

        if use_filesystem_stream:
            upload_result = await _upload_filesystem_file(file_path, storage, filename, mime_type)
        else:
            with SpooledTemporaryFile(
                max_size=_UPLOAD_SPOOL_MEMORY_LIMIT,
                mode="w+b",
            ) as spooled:
                await run_blocking_io(spooled.write, file_content)
                del file_content
                await run_blocking_io(spooled.seek, 0)
                upload_result = await storage.upload_file(
                    file=spooled,
                    folder="revealed_files",
                    filename=filename,
                    content_type=mime_type,
                    skip_size_limit=True,
                )

        file_category = get_file_category(upload_result.content_type or mime_type)

        proxy_url = f"{base_url}/api/upload/file/{upload_result.key}"

        reveal_result = {
            "key": upload_result.key,
            "url": proxy_url,
            "name": filename,
            "type": file_category,
            "mime_type": upload_result.content_type or mime_type,
            "size": upload_result.size,
            "_meta": {
                "path": file_path,
                "description": description or "",
            },
        }
        logger.info(f"Successfully uploaded {file_path} to S3: {upload_result.url}")

        await _index_revealed_file(
            runtime=runtime,
            file_name=filename,
            file_category=file_category,
            mime_type=upload_result.content_type or mime_type,
            file_size=upload_result.size,
            url=proxy_url,
            file_key=upload_result.key,
            description=description or "",
            original_path=file_path,
        )

        return await _json_dumps_result(reveal_result)

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        error_result = {
            "type": "file_reveal",
            "file": {
                "path": file_path,
                "description": description or "",
                "error": str(e),
            },
        }
        return await _json_dumps_result(error_result)


def get_reveal_file_tool() -> BaseTool:
    """获取 reveal_file 工具实例"""
    return reveal_file

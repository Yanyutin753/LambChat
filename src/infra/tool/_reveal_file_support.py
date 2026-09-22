"""reveal_file 的支撑层：URL/mime 工具、后端与文件系统 IO、本地引用解析。

从 reveal_file_tool.py 拆出（后端文件 ≤1000 行守卫）：主模块保留 reveal_file
主流程、文件库索引与产物去重复用；本模块承载无环依赖的底层助手，禁止
反向 import reveal_file_tool（否则成环）。测试对 moved 符号的 monkeypatch
目标应为本模块（见 test_reveal_file_tool_local_fallback）。
"""

import asyncio
import inspect
import mimetypes
import os
import re
from contextvars import ContextVar
from tempfile import SpooledTemporaryFile
from typing import Any, Literal, Optional
from urllib.parse import unquote, urlparse

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)


# Task-local handoff from the download helper to the immediate error probe. This
# is transient request state only; backend selection still comes from ToolRuntime.
_last_backend_download_error: ContextVar[tuple[Any, str, str] | None] = ContextVar(
    "reveal_file_last_backend_download_error", default=None
)


_UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024
_LOCAL_REF_RESOLUTION_MAX_BYTES = 2 * 1024 * 1024
_LOCAL_REF_UPLOAD_LIMIT = 20
_LOCAL_REF_UPLOAD_CONCURRENCY = 4
_DEFAULT_REVEAL_FILE_UPLOAD_MAX_BYTES = 1024 * 1024 * 1024


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
            return _coerce_file_size(await run_long_blocking_io(sync_method, file_path))
        except Exception as e:
            logger.debug(f"[reveal_file] get_file_size failed for {file_path}: {e}")

    private_method = getattr(backend, "_file_size", None)
    if callable(private_method):
        try:
            return _coerce_file_size(await run_long_blocking_io(private_method, file_path))
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

    The structured ``error`` from a failed response is handed to the immediate
    reveal-file probe via task-local transient state (issue #196).
    """
    logger.info(f"[reveal_file] Attempting to download: {file_path}")
    _last_backend_download_error.set(None)

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
                    _last_backend_download_error.set((backend, file_path, resp.error))
                    return None
        except Exception as e:
            logger.warning(f"[reveal_file] adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            responses = await run_long_blocking_io(backend.download_files, [file_path])
            if responses:
                resp = responses[0]
                logger.info(
                    f"[reveal_file] download_files response: path={resp.path}, error={resp.error}, content_len={len(resp.content) if resp.content else 0}"
                )
                if resp.content:
                    return resp.content
                elif resp.error:
                    logger.warning(f"[reveal_file] Download error: {resp.error}")
                    _last_backend_download_error.set((backend, file_path, resp.error))
                    return None
        except Exception as e:
            logger.warning(f"[reveal_file] download_files failed for {file_path}: {e}")

    return None


async def _probe_download_error(backend: Any, file_path: str) -> Optional[str]:
    """Probe the backend's structured download error for a path (issue #196).

    Called after a download yields no content to tell a directory from a
    missing file, so the caller can give the agent an actionable hint. The
    immediately preceding structured error is reused task-locally; a read-only
    probe is issued only when no such result is available.
    """
    cached = _last_backend_download_error.get()
    if cached is not None and cached[0] is backend and cached[1] == file_path:
        _last_backend_download_error.set(None)
        return cached[2]

    try:
        if hasattr(backend, "adownload_files"):
            responses = await backend.adownload_files([file_path])
        elif hasattr(backend, "download_files"):
            responses = await run_long_blocking_io(backend.download_files, [file_path])
        else:
            return None
        if responses:
            return responses[0].error
    except Exception as e:
        logger.debug("[reveal_file] probe error for %s: %s", file_path, e)
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

        content = await run_long_blocking_io(_read_small_file)
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

    file = await run_long_blocking_io(_open_file)
    try:
        return await storage.upload_file(
            file=file,
            folder="revealed_files",
            filename=filename,
            content_type=mime_type,
            skip_size_limit=True,
        )
    finally:
        await run_long_blocking_io(file.close)


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


_UPLOAD_PROXY_URL_PREFIX = "/api/upload/file/"


def _extract_self_upload_key(url: str) -> str | None:
    """提取指向本站上传代理路由（/api/upload/file/<key>）形态 URL 的 storage key。

    agent 常把 image_generate 等工具返回的长 URL 重新抄写后再传给
    reveal_file，hex id 抄错一个字符即得到不存在的对象；此类 URL 必须
    先校验存在性再透传。不含该路径前缀的远程 URL 返回 None，不校验。
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = unquote(parsed.path or "")
    if _UPLOAD_PROXY_URL_PREFIX not in path:
        return None
    key = path.split(_UPLOAD_PROXY_URL_PREFIX, 1)[1].strip("/")
    return key or None


async def _self_upload_url_missing(key: str) -> bool | None:
    """检查本站上传 key 是否存在；存储不可用（含初始化失败）时返回 None（保持透传可用性）。"""
    try:
        storage = await _get_storage()
        return not await storage.file_exists(key)
    except Exception as e:
        logger.warning(f"[reveal_file] Existence check failed for key {key}: {e}")
        return None


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
            if not await run_long_blocking_io(_is_file_path, abs_path):
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
            await run_long_blocking_io(spooled.write, content)
            del content
            await run_long_blocking_io(spooled.seek, 0)
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


async def _upload_local_references_bounded(
    paths: list[str],
    file_dir: str,
    backend: Any,
    storage: Any,
    base_url: str,
) -> list[Optional[str]]:
    """Upload local references with a fixed-size worker pool and stable results."""
    if not paths:
        return []

    results: list[Optional[str]] = [None] * len(paths)
    next_index = 0
    lock = asyncio.Lock()
    worker_count = min(max(int(_LOCAL_REF_UPLOAD_CONCURRENCY), 1), len(paths))

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(paths):
                    return
                index = next_index
                next_index += 1
            results[index] = await _upload_local_resource(
                paths[index],
                file_dir,
                backend,
                storage,
                base_url,
            )

    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return results


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
    urls = await _upload_local_references_bounded(
        unique_paths,
        file_dir,
        backend,
        storage,
        base_url,
    )
    for ref_path, url in zip(unique_paths, urls):
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

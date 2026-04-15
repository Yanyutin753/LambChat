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

import asyncio
import json
import mimetypes
import os
import re
from typing import Annotated, Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.infra.logging.context import TraceContext
from src.infra.revealed_file.storage import get_revealed_file_storage
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_user_id_from_runtime,
)

logger = get_logger(__name__)

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
            responses = await asyncio.to_thread(backend.download_files, [file_path])
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
        if os.path.isfile(file_path):
            return await asyncio.to_thread(lambda: open(file_path, "rb").read())
        logger.debug(f"[reveal_file] File not found on filesystem: {file_path}")
    except Exception as e:
        logger.warning(f"[reveal_file] Failed to read from filesystem: {file_path}: {e}")
    return None


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
        if content is None and not _is_sandbox_backend(backend):
            content = await _read_file_from_filesystem(abs_path)
        if content is None:
            return None

        res_filename = os.path.basename(abs_path)
        res_mime = get_mime_type(res_filename)
        upload_result = await storage.upload_bytes(
            data=content,
            folder="revealed_files",
            filename=res_filename,
            content_type=res_mime,
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
    file_path: Annotated[str, "要展示的文件路径（绝对路径或相对于工作目录的路径）"],
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
        file_path: 要展示的文件路径（绝对路径或相对于工作目录的路径）
        description: 对文件内容的简要描述，帮助用户理解为什么要查看这个文件（可选）

    Returns:
        JSON 格式的结果，包含文件信息
    """
    storage = await _get_storage()

    backend = get_backend_from_runtime(runtime)

    if backend is None:
        logger.warning("Backend not available from runtime, returning raw path")
        result: dict[str, Any] = {
            "type": "file_reveal",
            "file": {
                "path": file_path,
                "description": description or "",
            },
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        file_content = await _download_file_from_backend(backend, file_path)

        # 非沙箱模式兜底：backend 下载失败时尝试直接读取本地文件系统
        if file_content is None and not _is_sandbox_backend(backend):
            logger.info(
                f"[reveal_file] Backend download failed, trying filesystem fallback for {file_path}"
            )
            file_content = await _read_file_from_filesystem(file_path)

        if file_content is None:
            logger.error(f"Failed to read file {file_path} from backend")
            result = {
                "type": "file_reveal",
                "file": {
                    "path": file_path,
                    "description": description or "",
                    "error": "file_not_found_or_empty",
                },
            }
            return json.dumps(result, ensure_ascii=False)

        filename = file_path.split("/")[-1]
        mime_type = get_mime_type(filename)

        # 对可包含本地资源引用的文件（Markdown、HTML、SVG 等），兜底替换本地路径
        base_url = get_base_url_from_runtime(runtime)
        if not base_url:
            logger.warning("[reveal_file] base_url is empty, URL may be incomplete")

        if _needs_local_ref_resolution(filename, mime_type):
            file_dir = os.path.dirname(file_path)
            file_content = await _resolve_local_references(
                file_content, file_dir, backend, storage, base_url
            )

        upload_result = await storage.upload_bytes(
            data=file_content,
            folder="revealed_files",
            filename=filename,
            content_type=mime_type,
        )

        file_category = get_file_category(upload_result.content_type or mime_type)

        proxy_url = f"{base_url}/api/upload/file/{upload_result.key}"

        result = {
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

        # Index write: persist record to revealed_files collection (fire-and-forget)
        try:
            req_ctx = TraceContext.get_request_context()
            user_id = req_ctx.user_id or get_user_id_from_runtime(runtime)
            session_id = req_ctx.session_id
            trace_id = TraceContext.get().trace_id

            # Look up session's project_id
            session_project_id = None
            if session_id:
                try:
                    from src.infra.storage.mongodb import get_mongo_client
                    from src.kernel.config import settings

                    mongo_client = get_mongo_client()
                    db = mongo_client[settings.MONGODB_DB]
                    session_doc = await db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
                        {"session_id": session_id}, {"metadata.project_id": 1}
                    )
                    if session_doc:
                        session_project_id = (session_doc.get("metadata") or {}).get("project_id")
                except Exception:
                    pass

            if user_id and trace_id:
                storage_index = get_revealed_file_storage()
                await storage_index.upsert_by_name(
                    user_id=user_id,
                    file_name=filename,
                    source="reveal_file",
                    file_key=upload_result.key,
                    trace_id=trace_id,
                    data={
                        "file_type": file_category,
                        "mime_type": upload_result.content_type or mime_type,
                        "file_size": upload_result.size,
                        "url": proxy_url,
                        "session_id": session_id,
                        "project_id": session_project_id,
                        "description": description or "",
                        "original_path": file_path,
                    },
                )
        except Exception as idx_err:
            logger.warning(f"[reveal_file] Failed to index revealed file: {idx_err}")

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        result = {
            "type": "file_reveal",
            "file": {
                "path": file_path,
                "description": description or "",
                "error": str(e),
            },
        }
        return json.dumps(result, ensure_ascii=False)


def get_reveal_file_tool() -> BaseTool:
    """获取 reveal_file 工具实例"""
    return reveal_file

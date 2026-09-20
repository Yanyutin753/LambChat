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

import hashlib
import json
import os
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.logging.context import TraceContext
from src.infra.revealed_file.storage import get_revealed_file_storage

# 支撑层符号：IO/URL 工具与本地引用解析（测试对部分符号在本模块仍有绑定
# 可 patch；仅支撑模块内部使用的读取以 _reveal_file_support 为准）
from src.infra.tool._reveal_file_support import (  # noqa: F401
    _UPLOAD_SPOOL_MEMORY_LIMIT,
    FileCategory,
    _can_resolve_local_filesystem_refs,
    _download_file_from_backend,
    _extract_self_upload_key,
    _get_backend_file_size,
    _get_filename_from_path,
    _get_reveal_file_upload_max_bytes,
    _get_storage,
    _is_file_path,
    _is_remote_url,
    _is_sandbox_backend,
    _local_filesystem_fallback_enabled,
    _needs_local_ref_resolution,
    _probe_download_error,
    _read_file_from_filesystem,
    _resolve_local_references,
    _self_upload_url_missing,
    _upload_filesystem_file,
    get_file_category,
    get_mime_type,
)
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_delivery_source_from_runtime,
    get_session_id_from_runtime,
    get_trace_id_from_runtime,
    get_user_id_from_runtime,
)

logger = get_logger(__name__)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


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
    content_hash: str | None = None,
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
        if content_hash:
            data["content_hash"] = content_hash
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


def _reveal_user_id(runtime: ToolRuntime | None) -> str | None:
    """索引/复用共用的 user_id 提取（请求上下文优先，回退 runtime）。"""
    try:
        req_ctx = TraceContext.get_request_context()
    except Exception:
        req_ctx = None
    user_id = getattr(req_ctx, "user_id", None) or get_user_id_from_runtime(runtime)
    return user_id if isinstance(user_id, str) and user_id else None


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _hash_local_file(file_path: str) -> str | None:
    """流式哈希本地文件（不整读进内存）；失败返回 None（放弃复用直传）。"""
    try:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception as e:
        logger.debug(f"[reveal_file] Failed to hash local file {file_path}: {e}")
        return None


async def _try_reuse_upload(
    user_id: str | None,
    original_path: str,
    content_hash: str | None,
    mime_type: str,
    storage: Any | None = None,
) -> Any | None:
    """同路径同内容 → 复用既有存储对象，跳过重传（防存储孤儿累积）。

    依赖文件库行的 content_hash（本特性起写入）；旧行无该字段即不命中，
    安全回退为正常上传。命中要求行 file_key 是真实 storage key（非 URL），
    且对象在存储中仍存在——行命中但对象已被删时放弃复用重传，upsert
    顺带修复行（否则哈希永远命中死 key，产物永久 404）。存储不可用时
    保持复用（与代理 URL 透传校验同策略：可用性故障不该拖死交付）。
    """
    if not user_id or not content_hash:
        return None
    try:
        row = await get_revealed_file_storage().find_by_original(
            user_id, original_path, "reveal_file"
        )
    except Exception as e:
        logger.debug(f"[reveal_file] Reuse lookup failed for {original_path}: {e}")
        return None
    if not isinstance(row, dict) or row.get("content_hash") != content_hash:
        return None
    file_key = row.get("file_key")
    if not isinstance(file_key, str) or not file_key or _is_remote_url(file_key):
        return None
    if storage is not None:
        try:
            if not await storage.file_exists(file_key):
                logger.info(f"[reveal_file] Reuse hit but object missing, re-uploading: {file_key}")
                return None
        except Exception as e:
            logger.debug(f"[reveal_file] Reuse existence check failed for {file_key}: {e}")
    raw_size = row.get("file_size")
    raw_mime = row.get("mime_type")
    raw_url = row.get("url")
    file_size = raw_size if isinstance(raw_size, int) else 0
    row_mime = raw_mime if isinstance(raw_mime, str) else None
    row_url = raw_url if isinstance(raw_url, str) else ""
    logger.info(f"[reveal_file] Reusing existing object for {original_path}: {file_key}")
    return _ReusableUploadResult(
        key=file_key, url=row_url, size=file_size, content_type=row_mime or mime_type
    )


class _ReusableUploadResult:
    """duck-typed UploadResult：reveal 主流程只消费 key/url/size/content_type。"""

    def __init__(self, *, key: str, url: str, size: int, content_type: str) -> None:
        self.key = key
        self.url = url
        self.size = size
        self.content_type = content_type


async def _reverse_map_self_upload_row(
    user_id: str | None, file_path: str
) -> dict[str, Any] | None:
    """本站代理 URL → 反查文件库原始行（file_name/original_path/file_key）。

    模型按 ARTIFACT_POLICY 复述 reveal 返回的 URL 时，该 URL 再进
    reveal_file 按原始行归一索引，避免同一文件裂成 path:/url: 两行。
    """
    proxy_key = _extract_self_upload_key(file_path)
    if not proxy_key or not user_id:
        return None
    try:
        return await get_revealed_file_storage().find_by_file_key(user_id, proxy_key)
    except Exception as e:
        logger.debug(f"[reveal_file] Reverse map lookup failed for {file_path}: {e}")
        return None


@tool
async def reveal_file(
    file_path: Annotated[
        str, "Single file path or http(s) URL; use reveal_project for directories"
    ],
    description: Annotated[Optional[str], "Optional file caption"] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Show the user one clickable file or URL; replying with a bare path is not
    enough. Directories and multi-file projects must use reveal_project."""
    if _is_remote_url(file_path):
        self_upload_key = _extract_self_upload_key(file_path)
        if self_upload_key is not None:
            missing = await _self_upload_url_missing(self_upload_key)
            if missing:
                logger.warning(
                    f"[reveal_file] Self-hosted upload URL not found in storage: {file_path}"
                )
                return await _json_dumps_result(
                    {
                        "type": "file_reveal",
                        "file": {
                            "path": file_path,
                            "description": description or "",
                            "error": "remote_url_not_found",
                            "hint": (
                                "This upload URL does not match any stored file "
                                "(ids are easy to mistype when re-copying long URLs). "
                                "Re-copy the exact url from the original tool result and retry."
                            ),
                        },
                    }
                )
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
        # URL echo 归一：本站代理 URL 反查原始行，索引并入原行（不裂第二行）；
        # 并入时保留原行的真实元数据（尺寸/URL/mime），不得用 echo 的零值覆盖
        index_file_name = filename
        index_file_key: str = file_path
        index_original_path = file_path
        index_file_size = 0
        index_url = file_path
        index_mime_type = mime_type
        origin_row = await _reverse_map_self_upload_row(_reveal_user_id(runtime), file_path)
        if isinstance(origin_row, dict):
            row_name = origin_row.get("file_name")
            if isinstance(row_name, str) and row_name:
                index_file_name = row_name
            row_key = origin_row.get("file_key")
            if isinstance(row_key, str) and row_key and not _is_remote_url(row_key):
                index_file_key = row_key
            row_path = origin_row.get("original_path")
            if (
                isinstance(row_path, str)
                and row_path
                and not _is_remote_url(row_path)
                and not _extract_self_upload_key(row_path)
            ):
                index_original_path = row_path
            row_size = origin_row.get("file_size")
            if isinstance(row_size, int) and row_size > 0:
                index_file_size = row_size
            row_url = origin_row.get("url")
            if isinstance(row_url, str) and row_url:
                index_url = row_url
            row_mime = origin_row.get("mime_type")
            if isinstance(row_mime, str) and row_mime:
                index_mime_type = row_mime
        await _index_revealed_file(
            runtime=runtime,
            file_name=index_file_name,
            file_category=file_category,
            mime_type=index_mime_type,
            file_size=index_file_size,
            url=index_url,
            file_key=index_file_key,
            description=description or "",
            original_path=index_original_path,
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
            # Distinguish a directory from a missing file so the agent can stop
            # retrying / switch to reveal_project (issue #196). Sandbox only —
            # the local filesystem fallback path doesn't classify directories.
            if _is_sandbox_backend(backend):
                probe_error = await _probe_download_error(backend, file_path)
                if probe_error == "is_directory":
                    logger.warning(
                        "[reveal_file] Path is a directory, not a file: %s",
                        file_path,
                    )
                    return await _json_dumps_result(
                        {
                            "type": "file_reveal",
                            "file": {
                                "path": file_path,
                                "description": description or "",
                                "error": "path_is_directory",
                                "hint": "Path is a directory. Use reveal_project(project_path=...) for directories instead of reveal_file.",
                            },
                        }
                    )
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

        # 同路径同内容 → 复用既有对象（内容哈希，防重复上传孤儿）
        reuse_user_id = _reveal_user_id(runtime)
        content_hash: str | None = None
        upload_result = None
        if use_filesystem_stream:
            content_hash = await run_blocking_io(_hash_local_file, file_path)
            upload_result = await _try_reuse_upload(
                reuse_user_id, file_path, content_hash, mime_type, storage
            )
            if upload_result is None:
                upload_result = await _upload_filesystem_file(
                    file_path, storage, filename, mime_type
                )
        else:
            content_hash = await run_blocking_io(_sha256_hex, file_content)
            upload_result = await _try_reuse_upload(
                reuse_user_id, file_path, content_hash, mime_type, storage
            )
            if upload_result is None:
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
            content_hash=content_hash,
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

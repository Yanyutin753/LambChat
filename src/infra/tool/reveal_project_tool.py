"""
Reveal Project 工具

让 Agent 可以向用户展示整个项目或文件夹（多文件）。
前端项目会使用 Sandpack 进行浏览器预览；没有可运行前端入口的普通目录会以文件夹模式展示，
方便用户浏览大量代码、文档、配置或其他文本文件。

工作流程：
1. Agent 调用 reveal_project 指定项目目录
2. 后端递归扫描目录，将所有文件上传到 OSS/S3
3. 返回文件清单（manifest）给前端
4. 前端从 OSS 拉取文本文件内容，前端项目用 Sandpack 渲染，普通文件夹用文件树/代码浏览展示

返回格式（v2）：
{
    "type": "project_reveal",
    "version": 2,
    "name": "项目名称",
    "mode": "project" | "folder",
    "template": "react" | "vue" | "vanilla" | "static" | "angular" | "svelte" | "solid" | "nextjs",
    "files": {
        "/App.js": {"url": "/api/upload/file/...", "is_binary": false, "size": 123},
        "/logo.png": {"url": "/api/upload/file/...", "is_binary": true, "size": 4567, "content_type": "image/png"},
    },
    "entry": "/index.html"
}
"""

import asyncio
import inspect
import json
import os
import uuid
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
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
from src.infra.tool.reveal_project_detection import (
    ProjectTemplate,
    _find_entry,
    _get_mime_type,
    _is_binary,
    _resolve_reveal_mode,
    _should_skip,
    detect_template,
)

# 上传并发数。每个 worker 会短暂持有一个下载后的 bytes 缓冲，默认值需要保守。
UPLOAD_CONCURRENCY = 4

# 同名项目最大保留版本数，超出时清理最旧的
MAX_PROJECT_VERSIONS = 5
PROJECT_UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024
MAX_PROJECT_FILES = 200
_project_cleanup_tasks = BestEffortTaskLimiter("project cleanup", max_tasks=4)


async def drain_project_cleanup_tasks() -> None:
    await _project_cleanup_tasks.drain()


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


logger = get_logger(__name__)


def _get_project_scan_limit() -> int:
    return max(int(MAX_PROJECT_FILES), 1)


def _get_storage_internal_upload_max_size(storage: Any) -> int:
    config = getattr(storage, "_config", None)
    configured = (
        getattr(config, "internal_max_upload_size", 50 * 1024 * 1024)
        if config
        else 50 * 1024 * 1024
    )
    return max(int(configured or 50 * 1024 * 1024), 1)


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
            logger.debug(f"[reveal_project] aget_file_size failed for {file_path}: {e}")

    sync_method = getattr(backend, "get_file_size", None)
    if callable(sync_method):
        try:
            return _coerce_file_size(await run_blocking_io(sync_method, file_path))
        except Exception as e:
            logger.debug(f"[reveal_project] get_file_size failed for {file_path}: {e}")

    private_method = getattr(backend, "_file_size", None)
    if callable(private_method):
        try:
            return _coerce_file_size(await run_blocking_io(private_method, file_path))
        except Exception as e:
            logger.debug(f"[reveal_project] _file_size failed for {file_path}: {e}")

    return None


def _append_capped(files: list[str], file_path: str | None, seen: set[str] | None = None) -> bool:
    if not file_path:
        return len(files) >= _get_project_scan_limit()
    if seen is not None:
        if file_path in seen:
            return len(files) >= _get_project_scan_limit()
        seen.add(file_path)
    files.append(file_path)
    return len(files) >= _get_project_scan_limit()


def _is_single_file_project_path(project_path: str, all_files: list[str]) -> bool:
    return len(all_files) == 1 and os.path.normpath(all_files[0]) == os.path.normpath(project_path)


def _to_project_rel_path(project_path: str, file_path: str, *, single_file_path: bool) -> str:
    if single_file_path:
        return f"/{os.path.basename(file_path)}"

    rel_path = file_path[len(project_path) :] if file_path.startswith(project_path) else file_path
    if not rel_path.startswith("/"):
        rel_path = "/" + rel_path
    return rel_path


async def _get_storage():
    """获取已初始化的 storage 服务（复用 upload 模块的初始化逻辑）"""
    from src.infra.storage.s3.service import get_or_init_storage

    return await get_or_init_storage()


def _is_sandbox_backend(backend: Any) -> bool:
    """判断 backend 是否为沙箱类型（支持 shell 命令执行）"""
    return hasattr(backend, "execute") or hasattr(backend, "aexecute")


async def _download_file_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """通过 download_files 获取原始文件内容（沙箱/非沙箱均适用，无行号）"""
    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses and responses[0].content is not None:
                return responses[0].content
        except Exception as e:
            logger.debug(f"adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            responses = await run_blocking_io(backend.download_files, [file_path])
            if responses and responses[0].content is not None:
                return responses[0].content
        except Exception as e:
            logger.debug(f"download_files failed for {file_path}: {e}")

    return None


async def _execute_command(backend: Any, command: str) -> Optional[str]:
    """在沙箱 backend 中执行 shell 命令并返回 stdout，非沙箱返回 None"""
    if hasattr(backend, "aexecute"):
        try:
            result = await backend.aexecute(command)
            if hasattr(result, "output"):
                return result.output
            if isinstance(result, str):
                return result
        except Exception as e:
            logger.debug(f"aexecute failed: {e}")
            return None

    if hasattr(backend, "execute"):
        try:
            result = await run_blocking_io(backend.execute, command)
            if hasattr(result, "output"):
                return result.output
            if isinstance(result, str):
                return result
        except Exception as e:
            logger.debug(f"execute failed: {e}")

    return None


async def _list_project_files_via_glob(backend: Any, project_path: str) -> list[str]:
    """使用 glob 递归列出项目文件（适用于非沙箱 backend，效率高于逐级 ls）"""
    pattern = "**/*"

    if hasattr(backend, "aglob"):
        try:
            result = await backend.aglob(pattern, path=project_path)
            entries = result.matches or []
            aglob_files: list[str] = []
            for entry in entries:
                file_path = (
                    entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", None)
                )
                if _append_capped(aglob_files, file_path):
                    break
            return aglob_files
        except Exception as e:
            logger.debug(f"aglob failed for {project_path}: {e}")

    if hasattr(backend, "glob"):
        try:
            result = await run_blocking_io(backend.glob, pattern, project_path)
            entries = result.matches or []
            sync_glob_files: list[str] = []
            for entry in entries:
                file_path = (
                    entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", None)
                )
                if _append_capped(sync_glob_files, file_path):
                    break
            return sync_glob_files
        except Exception as e:
            logger.debug(f"glob failed for {project_path}: {e}")

    return []


async def _list_project_files_via_backend_api(
    backend: Any, project_path: str
) -> tuple[list[str], bool]:
    """使用 backend 的原生 ls 递归列出项目文件（glob 不可用时的兜底方案）"""
    files: list[str] = []
    seen_files: set[str] = set()
    pending = [project_path]
    visited: set[str] = set()
    had_errors = False

    while pending and len(files) < _get_project_scan_limit():
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)

        if hasattr(backend, "als"):
            try:
                result = await backend.als(current)
                entries = result.entries or []
            except Exception as e:
                logger.debug(f"als failed for {current}: {e}")
                had_errors = True
                continue
        elif hasattr(backend, "ls"):
            try:
                result = await run_blocking_io(backend.ls, current)
                entries = result.entries or []
            except Exception as e:
                logger.debug(f"ls failed for {current}: {e}")
                had_errors = True
                continue
        else:
            had_errors = True
            continue

        for entry in entries:
            if isinstance(entry, dict):
                entry_path = entry.get("path")
                is_dir = bool(entry.get("is_dir"))
            else:
                entry_path = getattr(entry, "path", None)
                is_dir = bool(getattr(entry, "is_dir", False))

            if not entry_path:
                continue
            normalized_path = str(entry_path).rstrip("/") if is_dir else str(entry_path)
            if is_dir:
                pending.append(normalized_path)
            else:
                if _append_capped(files, str(entry_path), seen_files):
                    break

    return sorted(files), had_errors


async def _list_project_files(backend: Any, project_path: str) -> list[str]:
    """递归列出项目目录下的所有文件，根据 backend 类型选择最优策略。

    - 沙箱 backend（Daytona/E2B）：shell find 为主，原生 API 补充
    - 非沙箱 backend（State/Store）：glob 为主，递归 ls 兜底
    """
    if _is_sandbox_backend(backend):
        # 沙箱模式：shell find 最可靠
        scan_limit = _get_project_scan_limit()
        output = await _execute_command(
            backend,
            f'LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 find "{project_path}" -type f 2>/dev/null | head -{scan_limit}',
        )
        files: list[str] = []
        seen_files: set[str] = set()
        if output:
            for line in output.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("find:"):
                    if _append_capped(files, line, seen_files):
                        break

        # 用原生 API 补充（处理 find 可能遗漏的情况）
        api_files: list[str] = []
        if len(files) < _get_project_scan_limit():
            api_files, _ = await _list_project_files_via_backend_api(backend, project_path)
            for file_path in api_files:
                if _append_capped(files, file_path, seen_files):
                    break

        logger.debug(
            f"_list_project_files({project_path}) [sandbox]: find={len(files) - len(api_files)}, api={len(api_files)}, total={len(files)}"
        )
        return sorted(files)
    else:
        # 非沙箱模式：glob 高效递归
        glob_files = await _list_project_files_via_glob(backend, project_path)

        if glob_files:
            logger.debug(
                f"_list_project_files({project_path}) [non-sandbox]: glob={len(glob_files)}"
            )
            return sorted(glob_files)

        # glob 不可用时回退到递归 ls
        api_files, _ = await _list_project_files_via_backend_api(backend, project_path)
        logger.debug(
            f"_list_project_files({project_path}) [non-sandbox]: ls_fallback={len(api_files)}"
        )
        return api_files


def _get_base_url(runtime: Any) -> str:
    """从 ToolRuntime 提取 base_url"""
    return get_base_url_from_runtime(runtime)


async def _cleanup_old_versions(storage: Any, project_name: str) -> None:
    """清理同名项目的旧版本上传，保留最近 MAX_PROJECT_VERSIONS 个"""
    try:
        existing = await storage.list_files("revealed_projects/")
        # 提取同名项目的文件夹名
        folders = set()
        for key in existing:
            # key 格式: revealed_projects/{name}_{uuid}/path/to/file
            parts = key.split("/")
            if len(parts) >= 2 and parts[1].startswith(f"{project_name}_"):
                folders.add(parts[1])
        # 按名称排序（uuid hex 字典序即为时间序），保留最新的 N 个
        sorted_folders = sorted(folders)
        if len(sorted_folders) > MAX_PROJECT_VERSIONS:
            for old_folder in sorted_folders[:-MAX_PROJECT_VERSIONS]:
                old_prefix = f"revealed_projects/{old_folder}/"
                old_keys = await storage.list_files(old_prefix)
                for key in old_keys:
                    await storage.delete_file(key)
                logger.info(f"Cleaned up old version: {old_prefix} ({len(old_keys)} files)")
    except Exception as e:
        logger.warning(f"Failed to cleanup old versions for {project_name}: {e}")


async def _upload_file(
    storage: Any,
    backend: Any,
    file_path: str,
    rel_path: str,
    folder_name: str,
    base_url: str,
    semaphore: asyncio.Semaphore,
) -> Optional[tuple[str, dict[str, Any], Optional[str], Optional[str]]]:
    """下载并上传单个文件到 OSS，返回 (rel_path, file_info, package_json_content)"""
    async with semaphore:
        max_size = _get_storage_internal_upload_max_size(storage)
        known_size = await _get_backend_file_size(backend, file_path)
        if known_size is not None and known_size > max_size:
            logger.info(f"Skipping large file before download: {rel_path} ({known_size} bytes)")
            return None

        content_bytes = await _download_file_from_backend(backend, file_path)
        if content_bytes is None:
            logger.debug(f"Failed to read: {rel_path}")
            return rel_path, {}, None, "read_failed"

        if len(content_bytes) > max_size:
            logger.info(f"Skipping large file: {rel_path} ({len(content_bytes)} bytes)")
            return None

        filename = os.path.basename(rel_path)
        is_binary = _is_binary(filename)
        mime_type = _get_mime_type(filename)

        upload_filename = rel_path.lstrip("/")
        content_type = mime_type if is_binary else "text/plain"
        package_json_content = None
        if rel_path == "/package.json":
            try:
                package_json_content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                pass

        with SpooledTemporaryFile(
            max_size=PROJECT_UPLOAD_SPOOL_MEMORY_LIMIT,
            mode="w+b",
        ) as spooled:
            await run_blocking_io(spooled.write, content_bytes)
            del content_bytes
            await run_blocking_io(spooled.seek, 0)
            upload_result = await storage.upload_file(
                file=spooled,
                folder=folder_name,
                filename=upload_filename,
                content_type=content_type,
                skip_size_limit=True,
            )

        proxy_url = f"{base_url}/api/upload/file/{upload_result.key}"

        file_info: dict[str, Any] = {
            "url": proxy_url,
            "is_binary": is_binary,
            "size": upload_result.size,
        }
        if is_binary:
            file_info["content_type"] = upload_result.content_type or mime_type

        return rel_path, file_info, package_json_content, None


async def _upload_project_files_bounded(
    storage: Any,
    backend: Any,
    upload_tasks: list[tuple[str, str]],
    folder_name: str,
    base_url: str,
) -> list[Optional[tuple[str, dict[str, Any], Optional[str], Optional[str]]]]:
    """Upload project files without creating one coroutine per file up front."""
    if not upload_tasks:
        return []

    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
    results: list[Optional[tuple[str, dict[str, Any], Optional[str], Optional[str]]]] = []
    next_index = 0
    lock = asyncio.Lock()
    worker_count = min(UPLOAD_CONCURRENCY, len(upload_tasks))

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(upload_tasks):
                    return
                file_path, rel_path = upload_tasks[next_index]
                next_index += 1
            results.append(
                await _upload_file(
                    storage,
                    backend,
                    file_path,
                    rel_path,
                    folder_name,
                    base_url,
                    semaphore,
                )
            )

    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return results


@tool
async def reveal_project(
    project_path: Annotated[
        str,
        "项目或文件夹目录路径；单个文件请使用 reveal_file；前端项目可预览，普通文件夹会以 folder 模式展示",
    ],
    name: Annotated[Optional[str], "项目名称（可选，默认使用目录名）"] = None,
    description: Annotated[Optional[str], "项目描述（可选）"] = None,
    template: Annotated[
        Optional[ProjectTemplate],
        "项目模板类型（可选，自动检测：react/vue/vanilla/static）",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    向用户展示一个项目或文件夹（多文件预览 / 文件树浏览）

    当 AI 生成或整理了多个文件时，使用此工具把整个目录展示给用户。
    单个 HTML、Markdown、PDF、图片或其他文件应优先使用 reveal_file。
    对 HTML/CSS/JS、React/Vue 等前端项目，工具会返回 project 模式用于浏览器预览；
    对没有前端入口的非前端普通代码目录、文档目录、配置目录或文件很多的结果，工具会返回 folder
    模式，让用户直接浏览文件夹内容。

    Args:
        project_path: 项目或文件夹目录路径；单个文件请使用 reveal_file
        name: 项目名称（可选，默认使用目录名）
        description: 项目描述（可选）
        template: 项目模板类型（可选，自动检测：react/vue/vanilla/static/angular/svelte/solid/nextjs）
        runtime: 工具运行时（自动注入）

    Returns:
        JSON 格式的项目文件清单，包含每个文件的 OSS URL
    """
    storage = await _get_storage()

    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return await _json_dumps_result(
            {
                "type": "project_reveal",
                "version": 2,
                "error": "backend_not_available",
                "message": "无法访问文件系统",
            }
        )

    project_path = project_path.rstrip("/")
    project_name = name or os.path.basename(project_path)
    base_url = _get_base_url(runtime)

    # 生成唯一文件夹名，避免项目名冲突
    folder_name = f"revealed_projects/{project_name}_{uuid.uuid4().hex[:8]}"

    try:
        all_files = await _list_project_files(backend, project_path)

        if not all_files:
            return await _json_dumps_result(
                {
                    "type": "project_reveal",
                    "version": 2,
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到文件",
                }
            )

        logger.info(f"Found {len(all_files)} files in {project_path}")

        # 预处理：计算 rel_path 并过滤需要跳过的文件
        upload_tasks: list[tuple[str, str]] = []  # (file_path, rel_path)
        skipped_files = 0
        skipped_due_to_file_limit = 0
        single_file_path = _is_single_file_project_path(project_path, all_files)
        for file_path in all_files:
            rel_path = _to_project_rel_path(
                project_path,
                file_path,
                single_file_path=single_file_path,
            )
            if not _should_skip(rel_path):
                if len(upload_tasks) >= MAX_PROJECT_FILES:
                    skipped_due_to_file_limit += 1
                    continue
                upload_tasks.append((file_path, rel_path))
            else:
                skipped_files += 1
        skipped_files += skipped_due_to_file_limit

        # 并发上传到 OSS，但只保留固定数量的 worker/coroutine，避免大目录放大内存。
        results = await _upload_project_files_bounded(
            storage,
            backend,
            upload_tasks,
            folder_name,
            base_url,
        )

        # 构建 manifest
        files_manifest: dict[str, dict[str, Any]] = {}
        package_json_content: Optional[str] = None
        failed_reads: list[str] = []
        for upload in results:
            if upload is None:
                continue
            rel_path, file_info, pkg_content, error = upload
            if error == "read_failed":
                failed_reads.append(rel_path)
                continue
            files_manifest[rel_path] = file_info
            if pkg_content is not None:
                package_json_content = pkg_content

        if not files_manifest:
            return await _json_dumps_result(
                {
                    "type": "project_reveal",
                    "version": 2,
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到可上传的文件",
                    "scanned_files": len(all_files),
                }
            )

        # 异步清理同名项目的旧版本（不阻塞返回）
        _project_cleanup_tasks.create_task(_cleanup_old_versions(storage, project_name))

        # 检测模板
        file_keys = set(files_manifest.keys())
        detected_template = template
        if not detected_template:
            detected_template = await run_blocking_io(
                detect_template,
                package_json_content or "{}",
                file_keys,
            )
        entry = _find_entry(file_keys, detected_template)
        if entry is None and single_file_path and len(file_keys) == 1:
            only_file = next(iter(file_keys))
            if only_file.lower().endswith((".html", ".htm")):
                entry = only_file
        mode = _resolve_reveal_mode(entry)

        result = {
            "type": "project_reveal",
            "version": 2,
            "name": project_name,
            "description": description or "",
            "mode": mode,
            "template": detected_template,
            "files": files_manifest,
            "entry": entry,
            "path": project_path,
            "file_count": len(files_manifest),
            "scanned_file_count": len(all_files),
            "filtered_file_count": len(upload_tasks),
            "skipped_file_count": skipped_files,
            "skipped_due_to_file_limit_count": skipped_due_to_file_limit,
            "read_failed_count": len(failed_reads),
        }
        if failed_reads:
            result["read_failed_files"] = failed_reads[:20]

        logger.info(f"Revealed project {project_name} with {len(files_manifest)} files (v2)")

        # --- Fire-and-forget index write to revealed_files collection ---
        try:
            ctx = TraceContext.get_request_context()
            user_id = ctx.user_id or get_user_id_from_runtime(runtime) or ""
            session_id = ctx.session_id or get_session_id_from_runtime(runtime) or ""
            trace_id = (
                ctx.trace_id
                or TraceContext.get().trace_id
                or get_trace_id_from_runtime(runtime)
                or ""
            )

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

            project_meta = {
                "mode": mode,
                "template": detected_template,
                "entry": entry,
                "file_count": len(files_manifest),
                "files": {k: dict(v) for k, v in files_manifest.items()},
            }
            data: dict[str, Any] = {
                "file_type": "project",
                "mime_type": None,
                "file_size": 0,
                "url": None,
                "session_id": session_id,
                "project_id": session_project_id,
                "description": description or "",
                "original_path": project_path,
                "project_meta": project_meta,
            }
            delivery_source = get_delivery_source_from_runtime(runtime)
            if delivery_source:
                data["delivery_source"] = delivery_source

            await get_revealed_file_storage().upsert_by_name(
                user_id=user_id,
                file_name=project_name,
                source="reveal_project",
                file_key=folder_name,
                trace_id=trace_id,
                data=data,
            )
        except Exception as e:
            logger.warning(f"Failed to index revealed project {project_name}: {e}")

        return await _json_dumps_result(result)

    except Exception as e:
        logger.error(f"Error revealing project {project_path}: {e}", exc_info=True)
        return await _json_dumps_result(
            {
                "type": "project_reveal",
                "version": 2,
                "error": str(e),
                "message": f"读取项目失败: {e}",
            }
        )


def get_reveal_project_tool() -> BaseTool:
    """获取 reveal_project 工具实例"""
    return reveal_project

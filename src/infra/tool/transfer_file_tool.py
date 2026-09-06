"""
Transfer File / Transfer Path 工具

在不同 backend 之间双向转移文本文件（sandbox、skills store、memory store 等）。
仅支持文本文件，不支持二进制文件。
通过 CompositeBackend 的路径前缀路由自动选择源/目标 backend：
  /skills/*  → SkillsStoreBackend (MongoDB)
  /memories/* → StoreBackend (DB)
  其他       → Sandbox (Daytona/E2B) 或 StoreBackend

支持双向传输：
  - sandbox → /skills/、/memories/ 等
  - /skills/ → sandbox
  - 任意两个不同 backend 之间

安全措施：
- 路径穿越防护（.. 规范化检查）
- 文件类型限制（扩展名黑名单 + null 字节检测）
- 文件大小限制（单文件 10MB，批量 100MB）
- 目录深度/文件数限制（深度 5 层，500 文件）
"""

import inspect
import json
import os
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime

# 二进制文件扩展名黑名单
BINARY_EXTENSIONS = frozenset(
    {
        # 图片
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".ico",
        ".svg",
        ".tiff",
        ".avif",
        # 视频
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
        # 音频
        ".mp3",
        ".wav",
        ".ogg",
        ".flac",
        ".aac",
        ".m4a",
        ".wma",
        # 压缩包
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".tgz",
        # 二进制/可执行
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".wasm",
        ".o",
        ".a",
        ".lib",
        # 文档二进制
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        # 数据库
        ".db",
        ".sqlite",
        ".sqlite3",
        # 字体
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        # 其他
        ".pyc",
        ".pyo",
        ".class",
        ".jar",
        ".parquet",
        ".arrow",
        ".feather",
    }
)

logger = get_logger(__name__)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


# ==========================================
# 安全常量
# ==========================================

# 单文件大小上限 (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024
# 批量传输总大小上限 (100MB)
MAX_BATCH_SIZE = 100 * 1024 * 1024
# 目录递归最大深度
MAX_RECURSION_DEPTH = 5
# 批量传输最大文件数
MAX_BATCH_FILES = 500
# 工具响应中最多返回的逐文件明细数，避免大批量传输把 LLM 消息体撑爆。
TRANSFER_PATH_RESULT_FILE_LIMIT = 100


# ==========================================
# 安全工具函数
# ==========================================


def _is_binary_file(filename: str) -> bool:
    """根据扩展名判断是否为二进制文件"""
    _, ext = os.path.splitext(filename.lower())
    return ext in BINARY_EXTENSIONS


def _is_text_content(data: bytes) -> bool:
    """检测内容是否为文本（检查前 8KB 是否包含 null 字节）"""
    chunk = data[:8192]
    return b"\x00" not in chunk


def _check_path_traversal(path: str) -> Optional[str]:
    """检查路径是否存在穿越攻击（.. 组件）。

    Returns:
        错误信息字符串，或 None（路径安全）
    """
    # 规范化路径
    normalized = os.path.normpath(path)
    # 规范化后的路径不应包含 .. 段（normpath 会解析 .. 但保留开头 ../）
    if ".." in normalized.split(os.sep):
        return f"path traversal detected: {path}"
    return None


def _check_file_size(content: bytes, filename: str) -> Optional[str]:
    """检查文件大小是否超限。

    Returns:
        错误信息字符串，或 None（大小合法）
    """
    if len(content) > MAX_FILE_SIZE:
        return f"file too large: {filename} ({len(content)} bytes, limit {MAX_FILE_SIZE} bytes)"
    return None


def _check_known_file_size(size: int | None, filename: str) -> Optional[str]:
    """检查已知文件大小是否超限，避免先下载大文件再拒绝。"""
    if size is not None and size > MAX_FILE_SIZE:
        return f"file too large: {filename} ({size} bytes, limit {MAX_FILE_SIZE} bytes)"
    return None


def _validate_text_file(filename: str, content: bytes) -> Optional[str]:
    """综合校验文件类型和内容。

    Returns:
        错误信息字符串，或 None（校验通过）
    """
    if _is_binary_file(filename):
        return f"binary files are not supported: {filename}"
    if not _is_text_content(content):
        return f"file appears to be binary (contains null bytes): {filename}"
    size_err = _check_file_size(content, filename)
    if size_err:
        return size_err
    return None


def _append_transfer_result(
    results: list[dict[str, Any]],
    result: dict[str, Any],
    omitted_count: int,
) -> int:
    if len(results) < TRANSFER_PATH_RESULT_FILE_LIMIT:
        results.append(result)
        return omitted_count
    return omitted_count + 1


def _entry_path(entry: Any) -> str | None:
    if isinstance(entry, dict):
        path = entry.get("path")
    else:
        path = getattr(entry, "path", None)
    return path if isinstance(path, str) else None


def _entry_is_dir(entry: Any) -> bool:
    if isinstance(entry, dict):
        return bool(entry.get("is_dir"))
    return bool(getattr(entry, "is_dir", False))


def _entry_size(entry: Any) -> int | None:
    value = entry.get("size") if isinstance(entry, dict) else getattr(entry, "size", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _get_backend_file_size(backend: Any, file_path: str) -> int | None:
    """Best-effort size preflight across sandbox/store backends."""
    async_method = getattr(backend, "aget_file_size", None)
    if callable(async_method):
        try:
            size = async_method(file_path)
            if inspect.isawaitable(size):
                size = await size
            return int(size) if size is not None else None
        except Exception as e:
            logger.debug(f"[transfer_file] aget_file_size failed for {file_path}: {e}")

    sync_method = getattr(backend, "get_file_size", None)
    if callable(sync_method):
        try:
            size = await run_blocking_io(sync_method, file_path)
            return int(size) if size is not None else None
        except Exception as e:
            logger.debug(f"[transfer_file] get_file_size failed for {file_path}: {e}")

    private_method = getattr(backend, "_file_size", None)
    if callable(private_method):
        try:
            size = await run_blocking_io(private_method, file_path)
            return int(size) if size is not None else None
        except Exception as e:
            logger.debug(f"[transfer_file] _file_size failed for {file_path}: {e}")

    return None


async def _download_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """从 backend 下载文件内容"""
    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses:
                resp = responses[0]
                if resp.content:
                    return resp.content
                if resp.error:
                    logger.warning(f"[transfer_file] Download error for {file_path}: {resp.error}")
        except Exception as e:
            logger.warning(f"[transfer_file] adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            responses = await run_blocking_io(backend.download_files, [file_path])
            if responses:
                resp = responses[0]
                if resp.content:
                    return resp.content
                if resp.error:
                    logger.warning(f"[transfer_file] Download error for {file_path}: {resp.error}")
        except Exception as e:
            logger.warning(f"[transfer_file] download_files failed for {file_path}: {e}")

    return None


async def _upload_to_backend(backend: Any, target_path: str, content: bytes) -> Optional[str]:
    """上传文件到 backend，返回错误信息或 None"""
    if hasattr(backend, "aupload_files"):
        try:
            responses = await backend.aupload_files([(target_path, content)])
            if responses:
                resp = responses[0]
                if resp.error:
                    return str(resp.error)
                return None
        except Exception as e:
            return str(e)

    if hasattr(backend, "upload_files"):
        try:
            responses = await run_blocking_io(backend.upload_files, [(target_path, content)])
            if responses:
                resp = responses[0]
                if resp.error:
                    return str(resp.error)
                return None
        except Exception as e:
            return str(e)

    return "backend does not support upload_files"


# 确定性上传失败：重试只会原样再失败一轮，直接返回。其余（upload_failed/
# io_error 或异常文本——中继/SDK 瞬时抖动）立即重试一次。
_NON_RETRYABLE_UPLOAD_ERRORS = frozenset(
    {
        "permission_denied",
        "is_directory",
        "invalid_path",
        "too_many_files",
        "file_too_large",
        "declined_by_user",
        "file_not_found",
        "backend does not support upload_files",
    }
)


async def _upload_to_backend_with_retry(
    backend: Any, target_path: str, content: bytes
) -> Optional[str]:
    """带单次重试的上传：瞬时失败立即重试（内容不变，幂等安全）。"""
    error = await _upload_to_backend(backend, target_path, content)
    if error is None or error in _NON_RETRYABLE_UPLOAD_ERRORS:
        return error
    logger.warning(f"[transfer] transient upload failure ({error}), retrying: {target_path}")
    return await _upload_to_backend(backend, target_path, content)


@tool
async def transfer_file(
    source_path: Annotated[
        str,
        "Source text-file path; /skills/* routes to Skill storage, otherwise workspace.",
    ],
    target_path: Annotated[
        str,
        "Target text-file path; /skills/* routes to Skill storage, otherwise workspace.",
    ],
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Transfer one text file between workspace and /skills/ storage. Reusable files
    belong in /workspace/.shared/ (persists across sessions — `ls` first, skip when
    present). Binary files are unsupported; use memory_* for cross-session memory."""
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return await _json_dumps_result({"success": False, "error": "backend not available"})

    # 1. 路径安全检查
    for label, path in [("source", source_path), ("target", target_path)]:
        traversal_err = _check_path_traversal(path)
        if traversal_err:
            return await _json_dumps_result({"success": False, "error": f"{label} {traversal_err}"})

    # 2. 下载
    filename = source_path.split("/")[-1]
    known_size = await _get_backend_file_size(backend, source_path)
    size_err = _check_known_file_size(known_size, filename)
    if size_err:
        return await _json_dumps_result(
            {
                "success": False,
                "error": size_err,
                "source": source_path,
            }
        )

    content = await _download_from_backend(backend, source_path)
    if content is None:
        return await _json_dumps_result(
            {
                "success": False,
                "error": f"file not found or empty: {source_path}",
                "source": source_path,
            }
        )

    # 3. 文件类型 + 大小校验
    validation_err = _validate_text_file(filename, content)
    if validation_err:
        return await _json_dumps_result(
            {
                "success": False,
                "error": validation_err,
                "source": source_path,
            }
        )

    # 4. 上传
    upload_error = await _upload_to_backend_with_retry(backend, target_path, content)
    if upload_error:
        return await _json_dumps_result(
            {
                "success": False,
                "error": upload_error,
                "source": source_path,
                "target": target_path,
            }
        )

    logger.info(
        f"[transfer_file] Transferred {source_path} -> {target_path} ({len(content)} bytes)"
    )

    return await _json_dumps_result(
        {
            "success": True,
            "source": source_path,
            "target": target_path,
            "size": len(content),
        }
    )


def get_transfer_file_tool() -> BaseTool:
    """获取 transfer_file 工具实例"""
    return transfer_file


# ==========================================
# Transfer Path — 批量目录传输
# ==========================================


async def _list_dir_files(
    backend: Any,
    dir_path: str,
    *,
    limit: int | None = None,
) -> list[tuple[str, int | None]]:
    """列出目录下所有文件路径（通过 ls 递归）。

    Returns:
        文件路径列表（相对/绝对路径，取决于 backend 返回格式）
    """
    all_files: list[tuple[str, int | None]] = []
    visited_dirs: set[str] = set()

    async def _recurse(current_dir: str, depth: int) -> None:
        if limit is not None and len(all_files) > limit:
            return
        if depth > MAX_RECURSION_DEPTH:
            return
        if current_dir in visited_dirs:
            return
        visited_dirs.add(current_dir)

        if hasattr(backend, "als"):
            try:
                result = await backend.als(current_dir)
            except Exception as e:
                raise RuntimeError(f"ls failed for {current_dir}: {e}") from e
        elif hasattr(backend, "ls"):
            try:
                result = await run_blocking_io(backend.ls, current_dir)
            except Exception as e:
                raise RuntimeError(f"ls failed for {current_dir}: {e}") from e
        else:
            raise RuntimeError("backend does not provide the v0.7 ls API")

        if getattr(result, "error", None):
            raise RuntimeError(f"ls failed for {current_dir}: {result.error}")
        entries = result.entries or []

        for entry in entries:
            if limit is not None and len(all_files) > limit:
                return
            path = _entry_path(entry)
            if path is None:
                continue
            if _entry_is_dir(entry):
                await _recurse(path, depth + 1)
            else:
                all_files.append((path, _entry_size(entry)))
                if limit is not None and len(all_files) > limit:
                    return

    await _recurse(dir_path, 0)
    return all_files


@tool
async def transfer_path(
    source_dir: Annotated[
        str,
        "Source directory; /skills/* routes to Skill storage, otherwise workspace.",
    ],
    target_prefix: Annotated[
        str,
        (
            "Target prefix; defaults to /skills/ and keeps the source directory name. "
            "Use /workspace/.shared/ for reusable assets."
        ),
    ] = "/skills/",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """Transfer a directory of text files between workspace and /skills/. Reusable
    directories go under /workspace/.shared/ (persists across sessions — `ls` first,
    skip when present). Limits: 10MB/file, 100MB total, depth 5, 500 files; binary
    files and .. traversal are rejected."""
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return await _json_dumps_result({"success": False, "error": "backend not available"})

    # 1. 路径安全检查
    for label, path in [("source_dir", source_dir), ("target_prefix", target_prefix)]:
        traversal_err = _check_path_traversal(path)
        if traversal_err:
            return await _json_dumps_result({"success": False, "error": f"{label} {traversal_err}"})

    # 确保 target_prefix 以 / 结尾
    if not target_prefix.endswith("/"):
        target_prefix += "/"

    # 防止同源传输（不能从 skills 传到 skills）
    if source_dir.startswith("/skills/") and target_prefix.startswith("/skills/"):
        return await _json_dumps_result(
            {
                "success": False,
                "error": "source and target cannot both be /skills/ (same backend)",
            }
        )
    if source_dir.startswith("/memories/") and target_prefix.startswith("/memories/"):
        return await _json_dumps_result(
            {
                "success": False,
                "error": "source and target cannot both be /memories/ (same backend)",
            }
        )

    # 2. 从 source_dir 提取目录名作为目标子路径
    dir_name = source_dir.rstrip("/").rsplit("/", 1)[-1]

    # 清洗 skill name（当目标是 /skills/ 时）
    if target_prefix == "/skills/":
        from src.infra.skill.parser import sanitize_skill_name

        dir_name = sanitize_skill_name(dir_name)

    target_base = f"{target_prefix}{dir_name}"

    # 3. 列出源目录下所有文件
    try:
        file_paths = await _list_dir_files(backend, source_dir, limit=MAX_BATCH_FILES)
    except RuntimeError as exc:
        logger.warning("[transfer_path] %s", exc)
        return await _json_dumps_result({"success": False, "error": str(exc)})

    if not file_paths:
        return await _json_dumps_result(
            {
                "success": True,
                "message": f"no files found in {source_dir}",
                "source_dir": source_dir,
                "target": target_base + "/",
                "transferred": 0,
                "skipped": 0,
                "failed": 0,
            }
        )

    # 文件数限制
    if len(file_paths) > MAX_BATCH_FILES:
        return await _json_dumps_result(
            {
                "success": False,
                "error": f"too many files: {len(file_paths)} (limit {MAX_BATCH_FILES})",
                "source_dir": source_dir,
            }
        )

    # 4. 逐个传输
    results: list[dict[str, Any]] = []
    total_size = 0
    transferred = 0
    skipped = 0
    failed = 0
    files_omitted = 0

    for file_path, known_size in file_paths:
        filename = file_path.rsplit("/", 1)[-1]

        # 计算相对路径，映射到目标
        rel_path = file_path
        source_dir_stripped = source_dir.rstrip("/")
        if file_path.startswith(source_dir_stripped):
            rel_path = file_path[len(source_dir_stripped) :].lstrip("/")
        target_path = f"{target_base}/{rel_path}" if rel_path else f"{target_base}/{filename}"

        size_err = _check_known_file_size(known_size, filename)
        if size_err:
            files_omitted = _append_transfer_result(
                results,
                {"file": file_path, "status": "skipped", "error": size_err},
                files_omitted,
            )
            skipped += 1
            continue
        if known_size is not None and total_size + known_size > MAX_BATCH_SIZE:
            files_omitted = _append_transfer_result(
                results,
                {
                    "file": file_path,
                    "status": "skipped",
                    "error": (
                        f"batch size limit exceeded ({total_size + known_size} > {MAX_BATCH_SIZE})"
                    ),
                },
                files_omitted,
            )
            skipped += 1
            continue

        # 下载
        try:
            content = await _download_from_backend(backend, file_path)
        except Exception as e:
            logger.warning(f"[transfer_path] Download failed for {file_path}: {e}")
            files_omitted = _append_transfer_result(
                results,
                {"file": file_path, "status": "failed", "error": str(e)},
                files_omitted,
            )
            failed += 1
            continue

        if content is None:
            files_omitted = _append_transfer_result(
                results,
                {"file": file_path, "status": "skipped", "error": "file not found or empty"},
                files_omitted,
            )
            skipped += 1
            continue

        # 文件校验
        validation_err = _validate_text_file(filename, content)
        if validation_err:
            files_omitted = _append_transfer_result(
                results,
                {"file": file_path, "status": "skipped", "error": validation_err},
                files_omitted,
            )
            skipped += 1
            continue

        # 总大小检查
        total_size += len(content)
        if total_size > MAX_BATCH_SIZE:
            files_omitted = _append_transfer_result(
                results,
                {
                    "file": file_path,
                    "status": "skipped",
                    "error": f"batch size limit exceeded ({total_size} > {MAX_BATCH_SIZE})",
                },
                files_omitted,
            )
            skipped += 1
            continue

        # 上传
        upload_err = await _upload_to_backend_with_retry(backend, target_path, content)
        if upload_err:
            files_omitted = _append_transfer_result(
                results,
                {"file": file_path, "status": "failed", "error": upload_err},
                files_omitted,
            )
            failed += 1
        else:
            files_omitted = _append_transfer_result(
                results,
                {
                    "file": file_path,
                    "status": "transferred",
                    "target": target_path,
                    "size": len(content),
                },
                files_omitted,
            )
            transferred += 1

    logger.info(
        f"[transfer_path] {source_dir} -> {target_base}/ "
        f"(transferred={transferred}, skipped={skipped}, failed={failed}, "
        f"total_size={total_size})"
    )

    return await _json_dumps_result(
        {
            "success": failed == 0,
            "source_dir": source_dir,
            "target": target_base + "/",
            "transferred": transferred,
            "skipped": skipped,
            "failed": failed,
            "total_size": total_size,
            "files": results,
            "files_omitted": files_omitted,
        }
    )


def get_transfer_path_tool() -> BaseTool:
    """获取 transfer_path 工具实例"""
    return transfer_path

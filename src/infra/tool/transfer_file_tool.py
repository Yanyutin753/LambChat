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
- 文件大小限制（单文件 1MB，批量 10MB）
- 目录深度/文件数限制（深度 5 层，200 文件）
"""

import asyncio
import json
import os
from typing import Annotated, Any, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

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
MAX_BATCH_FILES = 200


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
            responses = await asyncio.to_thread(backend.download_files, [file_path])
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
            responses = await asyncio.to_thread(backend.upload_files, [(target_path, content)])
            if responses:
                resp = responses[0]
                if resp.error:
                    return str(resp.error)
                return None
        except Exception as e:
            return str(e)

    return "backend does not support upload_files"


@tool
async def transfer_file(
    source_path: Annotated[
        str,
        "源文件路径。路径前缀决定源 backend：/skills/* → 技能存储, 其他 → 沙箱/工作区。跨会话语义记忆请使用 memory_* 工具。",
    ],
    target_path: Annotated[
        str,
        "目标文件路径。路径前缀决定目标 backend：/skills/* → 技能存储, 其他 → 沙箱/工作区。跨会话语义记忆请使用 memory_* 工具。",
    ],
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    在不同 backend 之间转移文本文件

    仅支持文本文件（代码、配置、Markdown 等），不支持二进制文件（图片、视频、压缩包等）。
    通过路径前缀自动路由到对应的存储后端：
    - /skills/* 路由到技能存储 (MongoDB)
    - 其他路径路由到沙箱 (Daytona/E2B) 或持久化存储

    常见用途：
    - 从沙箱转移生成的代码到技能目录
    - 从技能目录复制文件到沙箱工作区

    Args:
        source_path: 源文件路径（路径前缀决定源 backend）
        target_path: 目标文件路径（路径前缀决定目标 backend）

    Returns:
        JSON 格式的操作结果
    """
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return json.dumps({"success": False, "error": "backend not available"}, ensure_ascii=False)

    # 1. 路径安全检查
    for label, path in [("source", source_path), ("target", target_path)]:
        traversal_err = _check_path_traversal(path)
        if traversal_err:
            return json.dumps(
                {"success": False, "error": f"{label} {traversal_err}"},
                ensure_ascii=False,
            )

    # 2. 下载
    content = await _download_from_backend(backend, source_path)
    if content is None:
        return json.dumps(
            {
                "success": False,
                "error": f"file not found or empty: {source_path}",
                "source": source_path,
            },
            ensure_ascii=False,
        )

    # 3. 文件类型 + 大小校验
    filename = source_path.split("/")[-1]
    validation_err = _validate_text_file(filename, content)
    if validation_err:
        return json.dumps(
            {
                "success": False,
                "error": validation_err,
                "source": source_path,
            },
            ensure_ascii=False,
        )

    # 4. 上传
    upload_error = await _upload_to_backend(backend, target_path, content)
    if upload_error:
        return json.dumps(
            {
                "success": False,
                "error": upload_error,
                "source": source_path,
                "target": target_path,
            },
            ensure_ascii=False,
        )

    logger.info(
        f"[transfer_file] Transferred {source_path} -> {target_path} ({len(content)} bytes)"
    )

    return json.dumps(
        {
            "success": True,
            "source": source_path,
            "target": target_path,
            "size": len(content),
        },
        ensure_ascii=False,
    )


def get_transfer_file_tool() -> BaseTool:
    """获取 transfer_file 工具实例"""
    return transfer_file


# ==========================================
# Transfer Path — 批量目录传输
# ==========================================


async def _list_dir_files(backend: Any, dir_path: str) -> list[str]:
    """列出目录下所有文件路径（通过 ls 递归）。

    Returns:
        文件路径列表（相对/绝对路径，取决于 backend 返回格式）
    """
    all_files: list[str] = []
    visited_dirs: set[str] = set()

    async def _recurse(current_dir: str, depth: int) -> None:
        if depth > MAX_RECURSION_DEPTH:
            return
        if current_dir in visited_dirs:
            return
        visited_dirs.add(current_dir)

        try:
            if hasattr(backend, "als"):
                result = await backend.als(current_dir)
                entries = result.entries or []
            elif hasattr(backend, "ls"):
                result = await asyncio.to_thread(backend.ls, current_dir)
                entries = result.entries or []
            else:
                return
        except Exception as e:
            logger.warning(f"[transfer_path] ls failed for {current_dir}: {e}")
            return

        for entry in entries:
            if entry.get("is_dir"):
                await _recurse(entry["path"], depth + 1)
            else:
                all_files.append(entry["path"])

    await _recurse(dir_path, 0)
    return all_files


@tool
async def transfer_path(
    source_dir: Annotated[
        str,
        "源目录路径（如 /home/user/my-project/ 或 /skills/MySkill/）。路径前缀决定源 backend：/skills/* → 技能存储, 其他 → 沙箱。",
    ],
    target_prefix: Annotated[
        str,
        "目标路径前缀。默认 /skills/，会将源目录下所有文件传输到 skills 数据库，目录名作为 skill 名称。也可指定其他沙箱/工作区路径。",
    ] = "/skills/",
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    批量传输目录下所有文本文件到目标 backend（双向）

    在任意两个 backend 之间批量传输目录文件：
    - 沙箱 → /skills/ (批量创建 skill)
    - /skills/ → 沙箱 (将 skill 文件复制到工作区)

    目录名自动作为目标子路径名称（如 /skills/Foo/ → /home/user/Foo/）。

    安全限制：
    - 仅支持文本文件，不支持二进制文件
    - 单文件上限 1MB，总大小上限 10MB
    - 递归深度最大 5 层，最多 200 个文件
    - 禁止路径穿越（..）

    常见用途：
    - 从沙箱目录批量创建 skill（如 /home/user/my-skill/ → /skills/my-skill/）
    - 将 skill 文件批量复制到沙箱工作区（如 /skills/MySkill/ → /home/user/MySkill/）

    Args:
        source_dir: 源目录路径
        target_prefix: 目标路径前缀（默认 /skills/）

    Returns:
        JSON 格式的操作结果，包含每个文件的传输状态
    """
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return json.dumps({"success": False, "error": "backend not available"}, ensure_ascii=False)

    # 1. 路径安全检查
    for label, path in [("source_dir", source_dir), ("target_prefix", target_prefix)]:
        traversal_err = _check_path_traversal(path)
        if traversal_err:
            return json.dumps(
                {"success": False, "error": f"{label} {traversal_err}"},
                ensure_ascii=False,
            )

    # 确保 target_prefix 以 / 结尾
    if not target_prefix.endswith("/"):
        target_prefix += "/"

    # 防止同源传输（不能从 skills 传到 skills）
    if source_dir.startswith("/skills/") and target_prefix.startswith("/skills/"):
        return json.dumps(
            {
                "success": False,
                "error": "source and target cannot both be /skills/ (same backend)",
            },
            ensure_ascii=False,
        )
    if source_dir.startswith("/memories/") and target_prefix.startswith("/memories/"):
        return json.dumps(
            {
                "success": False,
                "error": "source and target cannot both be /memories/ (same backend)",
            },
            ensure_ascii=False,
        )

    # 2. 从 source_dir 提取目录名作为目标子路径
    dir_name = source_dir.rstrip("/").rsplit("/", 1)[-1]

    # 清洗 skill name（当目标是 /skills/ 时）
    if target_prefix == "/skills/":
        from src.infra.skill.parser import sanitize_skill_name

        dir_name = sanitize_skill_name(dir_name)

    target_base = f"{target_prefix}{dir_name}"

    # 3. 列出源目录下所有文件
    file_paths = await _list_dir_files(backend, source_dir)

    if not file_paths:
        return json.dumps(
            {
                "success": True,
                "message": f"no files found in {source_dir}",
                "source_dir": source_dir,
                "target": target_base + "/",
                "transferred": 0,
                "skipped": 0,
                "failed": 0,
            },
            ensure_ascii=False,
        )

    # 文件数限制
    if len(file_paths) > MAX_BATCH_FILES:
        return json.dumps(
            {
                "success": False,
                "error": f"too many files: {len(file_paths)} (limit {MAX_BATCH_FILES})",
                "source_dir": source_dir,
            },
            ensure_ascii=False,
        )

    # 4. 逐个传输
    results: list[dict[str, Any]] = []
    total_size = 0
    transferred = 0
    skipped = 0
    failed = 0

    for file_path in file_paths:
        filename = file_path.rsplit("/", 1)[-1]

        # 计算相对路径，映射到目标
        rel_path = file_path
        source_dir_stripped = source_dir.rstrip("/")
        if file_path.startswith(source_dir_stripped):
            rel_path = file_path[len(source_dir_stripped) :].lstrip("/")
        target_path = f"{target_base}/{rel_path}" if rel_path else f"{target_base}/{filename}"

        # 下载
        try:
            content = await _download_from_backend(backend, file_path)
        except Exception as e:
            logger.warning(f"[transfer_path] Download failed for {file_path}: {e}")
            results.append({"file": file_path, "status": "failed", "error": str(e)})
            failed += 1
            continue

        if content is None:
            results.append(
                {"file": file_path, "status": "skipped", "error": "file not found or empty"}
            )
            skipped += 1
            continue

        # 文件校验
        validation_err = _validate_text_file(filename, content)
        if validation_err:
            results.append({"file": file_path, "status": "skipped", "error": validation_err})
            skipped += 1
            continue

        # 总大小检查
        total_size += len(content)
        if total_size > MAX_BATCH_SIZE:
            results.append(
                {
                    "file": file_path,
                    "status": "skipped",
                    "error": f"batch size limit exceeded ({total_size} > {MAX_BATCH_SIZE})",
                }
            )
            skipped += 1
            continue

        # 上传
        upload_err = await _upload_to_backend(backend, target_path, content)
        if upload_err:
            results.append({"file": file_path, "status": "failed", "error": upload_err})
            failed += 1
        else:
            results.append(
                {
                    "file": file_path,
                    "status": "transferred",
                    "target": target_path,
                    "size": len(content),
                }
            )
            transferred += 1

    logger.info(
        f"[transfer_path] {source_dir} -> {target_base}/ "
        f"(transferred={transferred}, skipped={skipped}, failed={failed}, "
        f"total_size={total_size})"
    )

    return json.dumps(
        {
            "success": failed == 0,
            "source_dir": source_dir,
            "target": target_base + "/",
            "transferred": transferred,
            "skipped": skipped,
            "failed": failed,
            "total_size": total_size,
            "files": results,
        },
        ensure_ascii=False,
    )


def get_transfer_path_tool() -> BaseTool:
    """获取 transfer_path 工具实例"""
    return transfer_path

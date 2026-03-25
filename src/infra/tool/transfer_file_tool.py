"""
Transfer File 工具

在不同 backend 之间转移文本文件（sandbox、skills store、memory store 等）。
仅支持文本文件，不支持二进制文件。
通过 CompositeBackend 的路径前缀路由自动选择源/目标 backend：
  /skills/*  → SkillsStoreBackend (MongoDB)
  /memories/* → StoreBackend (DB)
  其他       → Sandbox (Daytona/E2B) 或 StoreBackend
"""

import asyncio
import json
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


def _is_binary_file(filename: str) -> bool:
    """根据扩展名判断是否为二进制文件"""
    import os

    _, ext = os.path.splitext(filename.lower())
    return ext in BINARY_EXTENSIONS


def _is_text_content(data: bytes) -> bool:
    """检测内容是否为文本（检查前 8KB 是否包含 null 字节）"""
    chunk = data[:8192]
    return b"\x00" not in chunk


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
        "源文件路径。路径前缀决定源 backend：/skills/* → 技能存储, /memories/* → 记忆存储, 其他 → 沙箱",
    ],
    target_path: Annotated[
        str,
        "目标文件路径。路径前缀决定目标 backend：/skills/* → 技能存储, /memories/* → 记忆存储, 其他 → 沙箱",
    ],
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    在不同 backend 之间转移文本文件

    仅支持文本文件（代码、配置、Markdown 等），不支持二进制文件（图片、视频、压缩包等）。
    通过路径前缀自动路由到对应的存储后端：
    - /skills/* 路由到技能存储 (MongoDB)
    - /memories/* 路由到记忆存储 (数据库)
    - 其他路径路由到沙箱 (Daytona/E2B) 或持久化存储

    常见用途：
    - 从沙箱转移生成的代码到技能目录
    - 在沙箱和记忆存储之间共享文本文件
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

    # 1. 下载
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

    # 2. 检查是否为文本文件
    filename = source_path.split("/")[-1]
    if _is_binary_file(filename):
        return json.dumps(
            {
                "success": False,
                "error": f"binary files are not supported: {filename}",
                "source": source_path,
            },
            ensure_ascii=False,
        )
    if not _is_text_content(content):
        return json.dumps(
            {
                "success": False,
                "error": f"file appears to be binary (contains null bytes): {filename}",
                "source": source_path,
            },
            ensure_ascii=False,
        )

    # 2. 上传
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

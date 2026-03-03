"""
Reveal File 工具

让 Agent 可以向用户展示/推荐文件，前端会自动展开文件树并可以点击查看内容。
文件会自动从 backend 下载并上传到 S3，返回 S3 URL。

支持两种模式：
1. 沙箱模式：使用 download_files 方法下载文件
2. 非沙箱模式（PostgreSQL）：使用 read 方法读取文件内容

返回格式与前端 UploadResult 一致：
{
    "key": "...",
    "url": "...",
    "name": "...",
    "type": "image" | "video" | "audio" | "document",
    "mimeType": "...",
    "size": ...
}

分布式安全设计：
- 不依赖 ContextVar（无法跨进程/Worker 工作）
- 通过 ToolRuntime 注入 backend
- 使用 asyncio.Lock 防止并发初始化
"""

import json
import logging
import mimetypes
from typing import Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.tool.backend_utils import get_backend_from_runtime

logger = logging.getLogger(__name__)

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
    # 精确匹配
    if mime_type in MIME_TYPE_CATEGORIES:
        return MIME_TYPE_CATEGORIES[mime_type]

    # 前缀匹配
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"

    # 默认为文档
    return "document"


def get_mime_type(filename: str) -> str:
    """根据文件名获取 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


async def _ensure_storage_initialized() -> None:
    """确保 S3 storage 已初始化"""
    from src.infra.storage.s3 import get_storage_service, init_storage
    from src.kernel.config import settings

    storage = get_storage_service()
    if storage._backend is None:
        config = settings.get_s3_config()
        await init_storage(config)


async def _read_file_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """
    从 backend 读取文件内容

    支持两种模式：
    1. 沙箱模式：使用 download_files 方法
    2. 非沙箱模式（StoreBackend/CompositeBackend）：使用 read 方法

    Args:
        backend: Backend 实例
        file_path: 文件路径

    Returns:
        文件内容的字节，如果失败返回 None
    """
    # 方式1: 沙箱模式 - 使用 download_files
    if hasattr(backend, "adownload_files"):
        try:
            download_responses = await backend.adownload_files([file_path])
            if download_responses and download_responses[0].content:
                logger.debug(f"Read file {file_path} via adownload_files")
                return download_responses[0].content
        except Exception as e:
            logger.debug(f"adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            download_responses = backend.download_files([file_path])
            if download_responses and download_responses[0].content:
                logger.debug(f"Read file {file_path} via download_files")
                return download_responses[0].content
        except Exception as e:
            logger.debug(f"download_files failed for {file_path}: {e}")

    # 方式2: 非沙箱模式 - 使用 read 方法 (StoreBackend/CompositeBackend)
    if hasattr(backend, "read"):
        try:
            # read 方法返回文件内容（字符串或对象）
            content = backend.read(file_path)
            if content is not None:
                # 如果是字符串，转换为字节
                if isinstance(content, str):
                    logger.debug(f"Read file {file_path} via read (string)")
                    return content.encode("utf-8")
                # 如果是字节，直接返回
                elif isinstance(content, bytes):
                    logger.debug(f"Read file {file_path} via read (bytes)")
                    return content
                # 如果是字典（文件信息），尝试获取内容
                elif isinstance(content, dict):
                    # 可能是文件信息对象
                    if "content" in content:
                        file_content = content["content"]
                        if isinstance(file_content, str):
                            return file_content.encode("utf-8")
                        elif isinstance(file_content, bytes):
                            return file_content
        except Exception as e:
            logger.debug(f"read failed for {file_path}: {e}")

    # 方式3: 尝试 aread 方法（异步版本）
    if hasattr(backend, "aread"):
        try:
            content = await backend.aread(file_path)
            if content is not None:
                if isinstance(content, str):
                    logger.debug(f"Read file {file_path} via aread (string)")
                    return content.encode("utf-8")
                elif isinstance(content, bytes):
                    logger.debug(f"Read file {file_path} via aread (bytes)")
                    return content
        except Exception as e:
            logger.debug(f"aread failed for {file_path}: {e}")

    return None


@tool
async def reveal_file(
    file_path: str,
    description: Optional[str] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    向用户展示/推荐一个文件（用户要求展示的时候，一定要调用）

    当你想让用户查看某个文件时，使用此工具。
    前端自动给用户显示可点击的文件。

    Args:
        file_path: 要展示的文件路径（绝对路径或相对于工作目录的路径）
        description: 对文件内容的简要描述，帮助用户理解为什么要查看这个文件（可选）

    Returns:
        JSON 格式的结果，包含文件信息
    """
    from src.infra.storage.s3 import get_storage_service

    # 初始化 S3 存储服务
    await _ensure_storage_initialized()
    storage = get_storage_service()

    # 从 runtime 获取 backend（分布式安全的方式）
    backend = get_backend_from_runtime(runtime)

    # 如果获取不到 backend，返回原始路径信息
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
        # 从 backend 读取文件内容（支持沙箱和非沙箱模式）
        file_content = await _read_file_from_backend(backend, file_path)

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

        # 从路径提取文件名
        filename = file_path.split("/")[-1]

        # 获取 MIME 类型
        mime_type = get_mime_type(filename)

        # 上传到 S3
        upload_result = await storage.upload_bytes(
            data=file_content,
            folder="revealed_files",
            filename=filename,
            content_type=mime_type,
        )

        # 获取文件类别
        file_category = get_file_category(upload_result.content_type or mime_type)

        # 生成后端代理 URL（与 /api/upload 返回格式一致）
        proxy_url = f"/api/upload/file/{upload_result.key}"

        # 返回与前端 UploadResult 一致的格式
        result = {
            "key": upload_result.key,
            "url": proxy_url,
            "name": filename,
            "type": file_category,
            "mimeType": upload_result.content_type or mime_type,
            "size": upload_result.size,
            # 保留额外信息供前端参考
            "_meta": {
                "path": file_path,
                "description": description or "",
            },
        }
        logger.info(f"Successfully uploaded {file_path} to S3: {upload_result.url}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")
        # 出错时返回原始路径信息
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

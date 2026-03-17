"""
Reveal File 工具

让 Agent 可以向用户展示/推荐文件，前端会自动展开文件树并可以点击查看内容。
文件会自动从 backend 下载并上传到 S3，返回 S3 URL。

统一通过 download_files 获取原始文件内容（沙箱/非沙箱均适用）。

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

import asyncio
import json
import mimetypes
from typing import Annotated, Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime

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


async def _ensure_storage_initialized() -> None:
    """确保 S3 storage 已初始化"""
    from src.infra.storage.s3 import get_storage_service, init_storage
    from src.kernel.config import settings

    storage = get_storage_service()
    if storage._backend is None:
        config = settings.get_s3_config()
        await init_storage(config)


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
                logger.info(f"[reveal_file] adownload_files response: path={resp.path}, error={resp.error}, content_len={len(resp.content) if resp.content else 0}")
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
                logger.info(f"[reveal_file] download_files response: path={resp.path}, error={resp.error}, content_len={len(resp.content) if resp.content else 0}")
                if resp.content:
                    return resp.content
                elif resp.error:
                    logger.warning(f"[reveal_file] Download error: {resp.error}")
        except Exception as e:
            logger.warning(f"[reveal_file] download_files failed for {file_path}: {e}")

    return None


@tool
async def reveal_file(
    file_path: Annotated[str, "要展示的文件路径（绝对路径或相对于工作目录的路径）"],
    description: Annotated[
        Optional[str], "对文件内容的简要描述，帮助用户理解为什么要查看这个文件"
    ] = None,
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

    await _ensure_storage_initialized()
    storage = get_storage_service()

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

        upload_result = await storage.upload_bytes(
            data=file_content,
            folder="revealed_files",
            filename=filename,
            content_type=mime_type,
        )

        file_category = get_file_category(upload_result.content_type or mime_type)

        base_url = ""
        if runtime:
            if hasattr(runtime, "config"):
                config = runtime.config
                if isinstance(config, dict):
                    configurable = config.get("configurable", {})
                    base_url = configurable.get("base_url", "")
            else:
                logger.warning("[reveal_file] runtime has no 'config' attribute")

        proxy_path = f"/api/upload/file/{upload_result.key}"
        proxy_url = f"{base_url}{proxy_path}" if base_url else proxy_path

        result = {
            "key": upload_result.key,
            "url": proxy_url,
            "name": filename,
            "type": file_category,
            "mimeType": upload_result.content_type or mime_type,
            "size": upload_result.size,
            "_meta": {
                "path": file_path,
                "description": description or "",
            },
        }
        logger.info(f"Successfully uploaded {file_path} to S3: {upload_result.url}")
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

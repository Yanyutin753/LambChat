"""
Reveal File 工具

让 Agent 可以向用户展示/推荐文件，前端会自动展开文件树并可以点击查看内容。
文件会自动从 sandbox 下载并上传到 S3，返回 S3 URL。

分布式安全设计：
- 不依赖 ContextVar（无法跨进程/Worker 工作）
- 通过 ToolRuntime 注入 backend
- 使用 asyncio.Lock 防止并发初始化
"""

import json
import logging
from typing import Optional

from deepagents.backends.protocol import BackendProtocol
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


async def _ensure_storage_initialized() -> None:
    """确保 S3 storage 已初始化"""
    from src.infra.storage.s3 import get_storage_service, init_storage
    from src.kernel.config import settings

    storage = get_storage_service()
    if storage._backend is None:
        config = settings.get_s3_config()
        await init_storage(config)


def _get_backend_from_runtime(runtime: Optional[ToolRuntime]) -> Optional[BackendProtocol]:
    """从 ToolRuntime 获取 backend（分布式安全）

    Backend 通过 runtime.config["configurable"]["backend"] 传递
    """
    if runtime is None:
        return None

    try:
        # 方式1: 从 runtime.config["configurable"]["backend"] 获取（主要方式）
        if hasattr(runtime, "config") and runtime.config:
            config = runtime.config
            # 检查 configurable 字典
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                if isinstance(configurable, dict):
                    backend: Optional[BackendProtocol] = configurable.get("backend")  # type: ignore[assignment]
                    if backend is not None:
                        logger.debug("Got backend from runtime.config['configurable']['backend']")
                        return backend
                # 也检查直接的 backend 键
                backend = config.get("backend")  # type: ignore[assignment]
                if backend is not None:
                    logger.debug("Got backend from runtime.config['backend']")
                    return backend

        # 方式2: 从 runtime 的 attributes 中获取
        if hasattr(runtime, "attributes"):
            backend = runtime.attributes.get("backend")  # type: ignore[assignment]
            if backend is not None:
                logger.debug("Got backend from runtime.attributes['backend']")
                return backend

        # 方式3: 从 configurable 属性获取
        if hasattr(runtime, "configurable"):
            config = runtime.configurable
            if isinstance(config, dict):
                backend = config.get("backend")  # type: ignore[assignment]
                if backend is not None:
                    logger.debug("Got backend from runtime.configurable['backend']")
                    return backend

    except Exception as e:
        logger.warning(f"Failed to get backend from runtime: {e}")

    return None


@tool
async def reveal_file(
    path: str,
    description: Optional[str] = None,
    runtime: Optional[ToolRuntime] = None,
) -> str:
    """
    向用户展示/推荐一个文件。

    当你想让用户查看某个文件时，使用此工具。
    前端会自动展开文件树，并显示可点击的文件路径。

    Args:
        path: 要展示的文件路径（绝对路径或相对于工作目录的路径）
        description: 对文件内容的简要描述，帮助用户理解为什么要查看这个文件（可选）

    Returns:
        JSON 格式的结果，包含文件信息
    """
    from src.infra.storage.s3 import get_storage_service

    # 初始化 S3 存储服务
    await _ensure_storage_initialized()
    storage = get_storage_service()

    # 从 runtime 获取 backend（分布式安全的方式）
    backend = _get_backend_from_runtime(runtime)

    # 如果获取不到 backend，返回原始路径信息
    if backend is None:
        logger.warning("Backend not available from runtime, returning raw path")
        result = {
            "type": "file_reveal",
            "file": {
                "path": path,
                "description": description or "",
            },
        }
        return json.dumps(result, ensure_ascii=False)

    # 检查 backend 是否支持 download_files
    if not hasattr(backend, "download_files") and not hasattr(backend, "adownload_files"):
        logger.warning("Backend does not support download_files, returning raw path")
        result = {
            "type": "file_reveal",
            "file": {
                "path": path,
                "description": description or "",
            },
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        # 1. 从 sandbox 下载文件
        if hasattr(backend, "adownload_files"):
            download_responses = await backend.adownload_files([path])
        else:
            download_responses = backend.download_files([path])
        download_response = download_responses[0]

        if download_response.error:
            logger.error(f"Failed to download file {path}: {download_response.error}")
            result = {
                "type": "file_reveal",
                "file": {
                    "path": path,
                    "description": description or "",
                    "error": download_response.error,
                },
            }
            return json.dumps(result, ensure_ascii=False)

        if download_response.content is None:
            logger.error(f"File content is None for {path}")
            result = {
                "type": "file_reveal",
                "file": {
                    "path": path,
                    "description": description or "",
                    "error": "empty_content",
                },
            }
            return json.dumps(result, ensure_ascii=False)

        # 2. 从路径提取文件名
        filename = path.split("/")[-1]

        # 3. 上传到 S3 (使用已初始化的 storage)
        upload_result = await storage.upload_bytes(
            data=download_response.content,
            folder="revealed_files",
            filename=filename,
        )

        # 4. 返回 S3 URL
        result = {
            "type": "file_reveal",
            "file": {
                "path": path,
                "description": description or "",
                "s3_url": upload_result.url,
                "s3_key": upload_result.key,
                "size": upload_result.size,
            },
        }
        logger.info(f"Successfully uploaded {path} to S3: {upload_result.url}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error processing file {path}: {e}")
        # 出错时返回原始路径信息
        result = {
            "type": "file_reveal",
            "file": {
                "path": path,
                "description": description or "",
                "error": str(e),
            },
        }
        return json.dumps(result, ensure_ascii=False)


def get_reveal_file_tool() -> BaseTool:
    """获取 reveal_file 工具实例"""
    return reveal_file

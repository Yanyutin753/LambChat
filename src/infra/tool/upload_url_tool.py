"""
URL 文件上传到沙箱工具

下载指定 URL 的文件内容，上传到沙箱文件系统的指定路径。
仅在沙箱模式下加载。

通过 ToolRuntime 注入 backend，复用 backend_utils 获取沙箱后端。
"""

import json
from typing import Annotated

import httpx
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime, get_base_url_from_runtime

logger = get_logger(__name__)

# 下载超时（秒）
_DOWNLOAD_TIMEOUT = 60

# 最大文件大小（50MB，与 S3_INTERNAL_UPLOAD_MAX_SIZE 保持一致）
_MAX_FILE_SIZE = 50 * 1024 * 1024


@tool
async def upload_url_to_sandbox(
    url: Annotated[str, "要下载的文件 URL"],
    file_path: Annotated[str, "沙箱内的目标文件路径（绝对路径）"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Download a file from a URL and upload it to the sandbox filesystem.

    Use this tool to transfer external files (user uploads, web resources) into the sandbox
    so they can be accessed by shell commands and scripts.
    """
    if not file_path.startswith("/"):
        return json.dumps({"success": False, "error": "file_path must be an absolute path"})

    # 获取 backend
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return json.dumps({"success": False, "error": "No sandbox backend available"})

    # 如果 url 是相对路径，拼接 base_url
    if url.startswith("/"):
        base_url = get_base_url_from_runtime(runtime)
        if base_url:
            url = f"{base_url}{url}"
        else:
            logger.warning("[upload_url_to_sandbox] url is relative but base_url is empty: %s", url)

    # 下载文件
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning(f"[upload_url_to_sandbox] HTTP error downloading {url}: {e}")
        return json.dumps(
            {
                "success": False,
                "error": f"Download failed: HTTP {e.response.status_code}",
            }
        )
    except Exception as e:
        logger.warning(f"[upload_url_to_sandbox] Failed to download {url}: {e}")
        return json.dumps({"success": False, "error": f"Download failed: {e}"})

    content = resp.content
    if len(content) > _MAX_FILE_SIZE:
        return json.dumps(
            {
                "success": False,
                "error": f"File too large: {len(content)} bytes (max {_MAX_FILE_SIZE})",
            }
        )

    # 上传到沙箱
    try:
        results = await backend.aupload_files([(file_path, content)])
        result = results[0]
        if result.error:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Upload failed: {result.error}",
                    "path": file_path,
                }
            )
        logger.info(f"[upload_url_to_sandbox] Uploaded {url} -> {file_path} ({len(content)} bytes)")
        return json.dumps({"success": True, "path": file_path, "size": len(content)})
    except Exception as e:
        logger.error(f"[upload_url_to_sandbox] Failed to upload to {file_path}: {e}")
        return json.dumps({"success": False, "error": f"Upload failed: {e}"})


def get_upload_url_tool() -> BaseTool:
    """获取 upload_url_to_sandbox 工具实例"""
    return upload_url_to_sandbox

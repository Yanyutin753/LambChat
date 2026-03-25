"""
Reveal Project 工具

让 Agent 可以向用户展示整个前端项目（多文件），前端使用 Sandpack 进行预览。
支持纯 HTML/CSS/JS 项目和 React/Vue 等框架项目。

工作流程：
1. Agent 调用 reveal_project 指定项目目录
2. 后端递归扫描目录，将所有文件上传到 OSS/S3
3. 返回文件清单（manifest）给前端
4. 前端从 OSS 拉取文本文件内容，替换二进制文件引用，用 Sandpack 渲染

返回格式（v2）：
{
    "type": "project_reveal",
    "version": 2,
    "name": "项目名称",
    "template": "react" | "vue" | "vanilla" | "static",
    "files": {
        "/App.js": {"url": "/api/upload/file/...", "is_binary": false, "size": 123},
        "/logo.png": {"url": "/api/upload/file/...", "is_binary": true, "size": 4567, "content_type": "image/png"},
    },
    "entry": "/index.html"
}
"""

import asyncio
import json
import mimetypes
import os
import uuid
from typing import Annotated, Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime

logger = get_logger(__name__)

ProjectTemplate = Literal["react", "vue", "vanilla", "static"]

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".bmp",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".mp3",
    ".mp4",
    ".webm",
    ".zip",
    ".mpg",
    ".mpeg",
    ".mov",
    ".avi",
    ".wav",
    ".ogg",
    ".flac",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".gz",
    ".tar",
    ".bz2",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".wasm",
}

IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "__pycache__",
    ".DS_Store",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
}

IGNORE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
}

# 入口文件候选顺序
ENTRY_CANDIDATES = [
    "/index.html",
    "/src/index.html",
    "/public/index.html",
    "/src/index.tsx",
    "/src/index.jsx",
    "/src/main.tsx",
    "/src/main.jsx",
    "/index.tsx",
    "/index.jsx",
    "/App.tsx",
    "/App.jsx",
]


def detect_template(package_json_content: str) -> ProjectTemplate:
    """根据 package.json 内容检测项目模板类型"""
    try:
        package = json.loads(package_json_content)
        deps = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        if "react" in deps:
            return "react"
        if "vue" in deps:
            return "vue"
    except (json.JSONDecodeError, AttributeError):
        pass
    return "vanilla"


def _should_skip(rel_path: str) -> bool:
    """检查文件是否应该跳过（仅忽略目录和特定文件，不再按扩展名过滤）"""
    parts = rel_path.strip("/").split("/")
    filename = parts[-1] if parts else ""

    if any(p in IGNORE_DIRS or (p.startswith(".") and p not in IGNORE_DIRS) for p in parts[:-1]):
        return True
    if filename.startswith(".") and filename not in IGNORE_FILES:
        return True
    if filename in IGNORE_FILES:
        return True

    return False


def _is_binary(filename: str) -> bool:
    """根据扩展名判断是否为二进制文件"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in BINARY_EXTENSIONS


def _get_mime_type(filename: str) -> str:
    """根据文件名获取 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


async def _ensure_storage_initialized() -> None:
    """确保 storage 已初始化（S3 或本地存储）"""
    from src.infra.storage.s3 import S3Config, S3Provider, get_storage_service, init_storage
    from src.kernel.config import settings

    storage = get_storage_service()
    if storage._backend is None:
        if settings.S3_ENABLED:
            config = settings.get_s3_config()
        else:
            config = S3Config(
                provider=S3Provider.LOCAL,
                storage_path=getattr(settings, "LOCAL_STORAGE_PATH", "./uploads") or "./uploads",
            )
        await init_storage(config)


async def _download_file_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """通过 download_files 获取原始文件内容（沙箱/非沙箱均适用，无行号）"""
    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses and responses[0].content:
                return responses[0].content
        except Exception as e:
            logger.debug(f"adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            responses = await asyncio.to_thread(backend.download_files, [file_path])
            if responses and responses[0].content:
                return responses[0].content
        except Exception as e:
            logger.debug(f"download_files failed for {file_path}: {e}")

    return None


async def _execute_command(backend: Any, command: str) -> Optional[str]:
    """在 backend 中执行 shell 命令并返回 stdout"""
    if hasattr(backend, "aexecute"):
        try:
            result = await backend.aexecute(command)
            if hasattr(result, "output"):
                return result.output
            if isinstance(result, str):
                return result
        except Exception as e:
            logger.debug(f"aexecute failed: {e}")

    if hasattr(backend, "execute"):
        try:
            result = await asyncio.to_thread(backend.execute, command)
            if hasattr(result, "output"):
                return result.output
            if isinstance(result, str):
                return result
        except Exception as e:
            logger.debug(f"execute failed: {e}")

    return None


async def _list_project_files(backend: Any, project_path: str) -> list[str]:
    """递归列出项目目录下的所有文件（使用 find 命令）"""
    output = await _execute_command(
        backend,
        f'LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 find "{project_path}" -type f 2>/dev/null | head -200',
    )
    if not output:
        return []

    files = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("find:"):
            files.append(line)
    return files


def _find_entry(file_keys: list[str]) -> Optional[str]:
    """查找项目入口文件"""
    for candidate in ENTRY_CANDIDATES:
        if candidate in file_keys:
            return candidate
    return None


def _get_base_url(runtime: Any) -> str:
    """从 ToolRuntime 提取 base_url"""
    if not runtime:
        return ""
    if hasattr(runtime, "config"):
        config = runtime.config
        if isinstance(config, dict):
            return config.get("configurable", {}).get("base_url", "")
    return ""


@tool
async def reveal_project(
    project_path: Annotated[str, "项目目录路径，包含 index.html 或 package.json 的目录"],
    name: Annotated[Optional[str], "项目名称（可选，默认使用目录名）"] = None,
    description: Annotated[Optional[str], "项目描述（可选）"] = None,
    template: Annotated[
        Optional[ProjectTemplate],
        "项目模板类型（可选，自动检测：react/vue/vanilla/static）",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    向用户展示一个前端项目（多文件预览）

    当 AI 生成了包含多个文件的前端项目（HTML/CSS/JS 或 React/Vue 项目）时，
    使用此工具让用户可以在沙箱环境中预览整个项目。

    Args:
        project_path: 项目目录路径（包含 index.html 或 package.json 的目录）
        name: 项目名称（可选，默认使用目录名）
        description: 项目描述（可选）
        template: 项目模板类型（可选，自动检测：react/vue/vanilla/static）
        runtime: 工具运行时（自动注入）

    Returns:
        JSON 格式的项目文件清单，包含每个文件的 OSS URL
    """
    from src.infra.storage.s3 import get_storage_service

    await _ensure_storage_initialized()
    storage = get_storage_service()

    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return json.dumps(
            {
                "type": "project_reveal",
                "version": 2,
                "error": "backend_not_available",
                "message": "无法访问文件系统",
            },
            ensure_ascii=False,
        )

    project_path = project_path.rstrip("/")
    project_name = name or os.path.basename(project_path)
    base_url = _get_base_url(runtime)

    # 生成唯一文件夹名，避免项目名冲突
    folder_name = f"revealed_projects/{project_name}_{uuid.uuid4().hex[:8]}"

    try:
        all_files = await _list_project_files(backend, project_path)

        if not all_files:
            return json.dumps(
                {
                    "type": "project_reveal",
                    "version": 2,
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到文件",
                },
                ensure_ascii=False,
            )

        logger.info(f"Found {len(all_files)} files in {project_path}")

        # 上传所有文件到 OSS，构建 manifest
        files_manifest: dict[str, dict[str, Any]] = {}
        package_json_content: Optional[str] = None

        for file_path in all_files:
            rel_path = (
                file_path[len(project_path) :] if file_path.startswith(project_path) else file_path
            )
            if not rel_path.startswith("/"):
                rel_path = "/" + rel_path

            if _should_skip(rel_path):
                continue

            content_bytes = await _download_file_from_backend(backend, file_path)
            if not content_bytes:
                logger.debug(f"Failed to read: {rel_path}")
                continue

            filename = os.path.basename(rel_path)
            is_binary = _is_binary(filename)
            mime_type = _get_mime_type(filename)

            # 保留目录结构：用 rel_path 的目录部分作为文件名前缀
            # 例如 /src/App.tsx -> 文件名用 src/App.tsx（去掉开头的 /）
            upload_filename = rel_path.lstrip("/")
            content_type = mime_type if is_binary else "text/plain"

            upload_result = await storage.upload_bytes(
                data=content_bytes,
                folder=folder_name,
                filename=upload_filename,
                content_type=content_type,
            )

            proxy_url = f"{base_url}/api/upload/file/{upload_result.key}" if base_url else f"/api/upload/file/{upload_result.key}"

            file_info: dict[str, Any] = {
                "url": proxy_url,
                "is_binary": is_binary,
                "size": upload_result.size,
            }
            if is_binary:
                file_info["content_type"] = upload_result.content_type or mime_type

            files_manifest[rel_path] = file_info

            # 缓存 package.json 内容用于模板检测
            if rel_path == "/package.json":
                try:
                    package_json_content = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    pass

        if not files_manifest:
            return json.dumps(
                {
                    "type": "project_reveal",
                    "version": 2,
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到可上传的文件",
                    "scanned_files": len(all_files),
                },
                ensure_ascii=False,
            )

        # 检测模板
        detected_template = template
        if not detected_template:
            if package_json_content:
                detected_template = detect_template(package_json_content)
            elif "/index.html" in files_manifest:
                detected_template = "vanilla"
            else:
                detected_template = "static"

        result = {
            "type": "project_reveal",
            "version": 2,
            "name": project_name,
            "description": description or "",
            "template": detected_template,
            "files": files_manifest,
            "entry": _find_entry(list(files_manifest.keys())),
            "path": project_path,
            "file_count": len(files_manifest),
        }

        logger.info(f"Revealed project {project_name} with {len(files_manifest)} files (v2)")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error revealing project {project_path}: {e}", exc_info=True)
        return json.dumps(
            {
                "type": "project_reveal",
                "version": 2,
                "error": str(e),
                "message": f"读取项目失败: {e}",
            },
            ensure_ascii=False,
        )


def get_reveal_project_tool() -> BaseTool:
    """获取 reveal_project 工具实例"""
    return reveal_project

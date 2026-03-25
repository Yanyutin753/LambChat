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

# 上传并发数
UPLOAD_CONCURRENCY = 10

# 同名项目最大保留版本数，超出时清理最旧的
MAX_PROJECT_VERSIONS = 5

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

# 前端相关扩展名白名单，不在列表中的非二进制文件会被跳过
FRONTEND_EXTENSIONS = {
    # Web 核心
    ".html",
    ".htm",
    ".css",
    # JavaScript / TypeScript
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    # 框架 / 预处理器
    ".vue",
    ".svelte",
    ".less",
    ".scss",
    ".sass",
    ".styl",
    # 数据 / 配置
    ".json",
    ".json5",
    ".toml",
    ".yaml",
    ".yml",
    # 模板 / 标记
    ".md",
    ".mdx",
    ".txt",
    ".graphql",
    ".gql",
    # 其他前端资源
    ".map",
    ".xml",
}

IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".DS_Store",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".turbo",
    ".cache",
    ".parcel-cache",
}

IGNORE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "tsconfig.tsbuildinfo",
    ".eslintcache",
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
    """检查文件是否应该跳过（忽略目录、隐藏文件、非前端文件）"""
    parts = rel_path.strip("/").split("/")
    filename = parts[-1] if parts else ""

    if any(p in IGNORE_DIRS or (p.startswith(".") and p not in IGNORE_DIRS) for p in parts[:-1]):
        return True
    if filename.startswith(".") and filename not in IGNORE_FILES:
        return True
    if filename in IGNORE_FILES:
        return True

    # 跳过不在白名单中的非二进制文件
    ext = os.path.splitext(filename)[1].lower()
    if ext not in BINARY_EXTENSIONS and ext not in FRONTEND_EXTENSIONS:
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


async def _get_storage():
    """获取已初始化的 storage 服务（复用 upload 模块的初始化逻辑）"""
    from src.api.routes.upload import get_or_init_storage

    return await get_or_init_storage()


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


def _find_entry(file_keys: set[str]) -> Optional[str]:
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
) -> Optional[tuple[str, dict[str, Any], Optional[str]]]:
    """下载并上传单个文件到 OSS，返回 (rel_path, file_info, package_json_content)"""
    async with semaphore:
        content_bytes = await _download_file_from_backend(backend, file_path)
        if not content_bytes:
            logger.debug(f"Failed to read: {rel_path}")
            return None

        max_size = getattr(storage, "_config", None)
        max_size = (
            getattr(max_size, "internal_max_upload_size", 50 * 1024 * 1024)
            if max_size
            else 50 * 1024 * 1024
        )
        if len(content_bytes) > max_size:
            logger.info(f"Skipping large file: {rel_path} ({len(content_bytes)} bytes)")
            return None

        filename = os.path.basename(rel_path)
        is_binary = _is_binary(filename)
        mime_type = _get_mime_type(filename)

        upload_filename = rel_path.lstrip("/")
        content_type = mime_type if is_binary else "text/plain"

        upload_result = await storage.upload_bytes(
            data=content_bytes,
            folder=folder_name,
            filename=upload_filename,
            content_type=content_type,
        )

        proxy_url = (
            f"{base_url}/api/upload/file/{upload_result.key}"
            if base_url
            else f"/api/upload/file/{upload_result.key}"
        )

        file_info: dict[str, Any] = {
            "url": proxy_url,
            "is_binary": is_binary,
            "size": upload_result.size,
        }
        if is_binary:
            file_info["content_type"] = upload_result.content_type or mime_type

        # 提取 package.json 内容
        package_json_content = None
        if rel_path == "/package.json":
            try:
                package_json_content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                pass

        return rel_path, file_info, package_json_content


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
    storage = await _get_storage()

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

        # 预处理：计算 rel_path 并过滤需要跳过的文件
        upload_tasks: list[tuple[str, str]] = []  # (file_path, rel_path)
        for file_path in all_files:
            rel_path = (
                file_path[len(project_path) :] if file_path.startswith(project_path) else file_path
            )
            if not rel_path.startswith("/"):
                rel_path = "/" + rel_path
            if not _should_skip(rel_path):
                upload_tasks.append((file_path, rel_path))

        # 并发上传所有文件到 OSS
        semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
        results = await asyncio.gather(
            *[
                _upload_file(storage, backend, fp, rp, folder_name, base_url, semaphore)
                for fp, rp in upload_tasks
            ],
        )

        # 构建 manifest
        files_manifest: dict[str, dict[str, Any]] = {}
        package_json_content: Optional[str] = None
        for upload in results:
            if upload is None:
                continue
            rel_path, file_info, pkg_content = upload
            files_manifest[rel_path] = file_info
            if pkg_content is not None:
                package_json_content = pkg_content

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

        # 异步清理同名项目的旧版本（不阻塞返回）
        asyncio.create_task(_cleanup_old_versions(storage, project_name))

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
            "entry": _find_entry(set(files_manifest.keys())),
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

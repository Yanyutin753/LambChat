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
    "template": "react" | "vue" | "vanilla" | "static" | "angular" | "svelte" | "solid" | "nextjs",
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
from src.infra.logging.context import TraceContext
from src.infra.revealed_file.storage import get_revealed_file_storage
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_user_id_from_runtime,
)

logger = get_logger(__name__)

ProjectTemplate = Literal[
    "react", "vue", "vanilla", "static", "angular", "svelte", "solid", "nextjs"
]

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

# 入口文件候选顺序（按模板类型分组，避免 React 项目误选 /index.html）
ENTRY_CANDIDATES_BY_TEMPLATE: dict[str, list[str]] = {
    "nextjs": [
        "/pages/index.tsx",
        "/pages/index.jsx",
        "/pages/_app.tsx",
        "/pages/_app.jsx",
        "/index.html",
    ],
    "react": [
        "/src/main.tsx",
        "/src/main.jsx",
        "/src/index.tsx",
        "/src/index.jsx",
        "/src/main.ts",
        "/src/main.js",
        "/main.tsx",
        "/main.jsx",
        "/main.js",
        "/src/App.tsx",
        "/src/App.jsx",
        "/App.tsx",
        "/App.jsx",
        "/index.html",
    ],
    "vue": [
        "/src/main.js",
        "/src/main.ts",
        "/main.js",
        "/main.ts",
        "/src/main.vue",
        "/src/App.vue",
        "/App.vue",
        "/index.html",
    ],
    "svelte": [
        "/src/App.svelte",
        "/App.svelte",
        "/src/main.svelte",
        "/main.svelte",
        "/index.html",
    ],
    "angular": [
        "/src/main.ts",
        "/src/main.js",
        "/main.ts",
        "/main.js",
        "/index.html",
    ],
    "solid": [
        "/src/index.tsx",
        "/src/index.jsx",
        "/src/main.tsx",
        "/src/main.jsx",
        "/index.html",
    ],
    # static / vanilla / fallback：index.html 优先
    "_default": [
        "/index.html",
        "/src/index.html",
        "/public/index.html",
        "/src/main.ts",
        "/src/index.ts",
        "/src/index.tsx",
        "/src/index.jsx",
        "/src/main.tsx",
        "/src/main.jsx",
        "/src/main.js",
        "/main.ts",
        "/index.ts",
        "/index.js",
        "/main.js",
        "/src/main.vue",
        "/src/App.svelte",
        "/index.tsx",
        "/index.jsx",
        "/App.tsx",
        "/App.jsx",
    ],
}


def _has_any_file(file_keys: set[str], candidates: tuple[str, ...]) -> bool:
    return any(path in file_keys for path in candidates)


def detect_template(
    package_json_content: str, file_keys: Optional[set[str]] = None
) -> ProjectTemplate:
    """根据 package.json 内容和文件结构检测项目模板类型"""
    normalized_file_keys = file_keys or set()

    try:
        package = json.loads(package_json_content)
        deps = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        if "next" in deps:
            return "nextjs"
        if "solid-js" in deps:
            return "solid"
        if "svelte" in deps:
            return "svelte"
        if any(name.startswith("@angular/") for name in deps):
            return "angular"
        if "react" in deps:
            return "react"
        if "vue" in deps:
            # 如果有 vite.config，使用 vite-vue 模板以获得更好的支持
            if file_keys and any(
                f.endswith(("vite.config.js", "vite.config.ts")) for f in file_keys
            ):
                return "vue"  # 前端会自动检测为 vite-vue
            return "vue"
    except (json.JSONDecodeError, AttributeError):
        pass

    if _has_any_file(
        normalized_file_keys,
        (
            "/pages/index.tsx",
            "/pages/index.jsx",
            "/pages/_app.tsx",
            "/pages/_app.jsx",
        ),
    ):
        return "nextjs"

    if _has_any_file(
        normalized_file_keys,
        (
            "/src/App.svelte",
            "/App.svelte",
            "/src/main.svelte",
            "/main.svelte",
        ),
    ):
        return "svelte"

    if "/angular.json" in normalized_file_keys and _has_any_file(
        normalized_file_keys,
        (
            "/src/main.ts",
            "/src/main.js",
            "/main.ts",
            "/main.js",
        ),
    ):
        return "angular"

    if _has_any_file(
        normalized_file_keys,
        (
            "/src/main.jsx",
            "/src/main.tsx",
            "/src/index.jsx",
            "/src/index.tsx",
            "/main.jsx",
            "/main.tsx",
            "/index.jsx",
            "/index.tsx",
            "/App.jsx",
            "/App.tsx",
        ),
    ):
        return "react"

    if _has_any_file(
        normalized_file_keys,
        (
            "/src/main.vue",
            "/src/App.vue",
            "/App.vue",
        ),
    ):
        return "vue"

    if "/index.html" in normalized_file_keys:
        return "static"

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
    ext = os.path.splitext(filename)[1].lower()

    # 为前端文件扩展名提供明确的 MIME 类型映射
    frontend_mime_types = {
        ".vue": "text/plain",
        ".svelte": "text/plain",
        ".jsx": "text/plain",
        ".tsx": "text/plain",
        ".ts": "text/plain",
        ".mts": "text/plain",
        ".cts": "text/plain",
        ".mjs": "text/plain",
        ".cjs": "text/plain",
        ".scss": "text/plain",
        ".sass": "text/plain",
        ".less": "text/plain",
        ".styl": "text/plain",
        ".json5": "text/plain",
        ".toml": "text/plain",
        ".yaml": "text/plain",
        ".yml": "text/plain",
        ".md": "text/plain",
        ".mdx": "text/plain",
        ".graphql": "text/plain",
        ".gql": "text/plain",
    }

    if ext in frontend_mime_types:
        return frontend_mime_types[ext]

    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


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
            responses = await asyncio.to_thread(backend.download_files, [file_path])
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
            result = await asyncio.to_thread(backend.execute, command)
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
            files = [
                entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", None)
                for entry in entries
            ]
            return [f for f in files if f]
        except Exception as e:
            logger.debug(f"aglob failed for {project_path}: {e}")

    if hasattr(backend, "glob"):
        try:
            result = await asyncio.to_thread(backend.glob, pattern, project_path)
            entries = result.matches or []
            files = [
                entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", None)
                for entry in entries
            ]
            return [f for f in files if f]
        except Exception as e:
            logger.debug(f"glob failed for {project_path}: {e}")

    return []


async def _list_project_files_via_backend_api(
    backend: Any, project_path: str
) -> tuple[list[str], bool]:
    """使用 backend 的原生 ls 递归列出项目文件（glob 不可用时的兜底方案）"""
    files: set[str] = set()
    pending = [project_path]
    visited: set[str] = set()
    had_errors = False

    while pending:
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
                result = await asyncio.to_thread(backend.ls, current)
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
                files.add(str(entry_path))

    return sorted(files), had_errors


async def _list_project_files(backend: Any, project_path: str) -> list[str]:
    """递归列出项目目录下的所有文件，根据 backend 类型选择最优策略。

    - 沙箱 backend（Daytona/E2B）：shell find 为主，原生 API 补充
    - 非沙箱 backend（State/Store）：glob 为主，递归 ls 兜底
    """
    if _is_sandbox_backend(backend):
        # 沙箱模式：shell find 最可靠
        output = await _execute_command(
            backend,
            f'LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 find "{project_path}" -type f 2>/dev/null | head -200',
        )
        files: list[str] = []
        if output:
            for line in output.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("find:"):
                    files.append(line)

        # 用原生 API 补充（处理 find 可能遗漏的情况）
        api_files, _ = await _list_project_files_via_backend_api(backend, project_path)
        if api_files:
            files.extend(api_files)

        logger.debug(
            f"_list_project_files({project_path}) [sandbox]: find={len(files) - len(api_files)}, api={len(api_files)}, total={len(set(files))}"
        )
        return sorted(set(files))
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


def _find_entry(file_keys: set[str], template: Optional[str] = None) -> Optional[str]:
    """查找项目入口文件，优先使用模板对应的候选列表"""
    # 按模板类型选择候选列表
    candidates = ENTRY_CANDIDATES_BY_TEMPLATE.get(template or "_default", [])
    if not candidates:
        candidates = ENTRY_CANDIDATES_BY_TEMPLATE["_default"]
    for candidate in candidates:
        if candidate in file_keys:
            return candidate
    return None


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
        content_bytes = await _download_file_from_backend(backend, file_path)
        if content_bytes is None:
            logger.debug(f"Failed to read: {rel_path}")
            return rel_path, {}, None, "read_failed"

        max_size = getattr(storage, "_config", None)
        max_size = (
            getattr(max_size, "internal_max_upload_size", 50 * 1024 * 1024)
            if max_size
            else 50 * 1024 * 1024
        )
        if len(content_bytes) > max_size:  # type: ignore[operator]
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

        proxy_url = f"{base_url}/api/upload/file/{upload_result.key}"

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

        return rel_path, file_info, package_json_content, None


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
        template: 项目模板类型（可选，自动检测：react/vue/vanilla/static/angular/svelte/solid/nextjs）
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
        skipped_files = 0
        for file_path in all_files:
            rel_path = (
                file_path[len(project_path) :] if file_path.startswith(project_path) else file_path
            )
            if not rel_path.startswith("/"):
                rel_path = "/" + rel_path
            if not _should_skip(rel_path):
                upload_tasks.append((file_path, rel_path))
            else:
                skipped_files += 1

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
        task = asyncio.create_task(_cleanup_old_versions(storage, project_name))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        # 检测模板
        file_keys = set(files_manifest.keys())
        detected_template = template
        if not detected_template:
            detected_template = detect_template(package_json_content or "{}", file_keys)

        result = {
            "type": "project_reveal",
            "version": 2,
            "name": project_name,
            "description": description or "",
            "template": detected_template,
            "files": files_manifest,
            "entry": _find_entry(file_keys, detected_template),
            "path": project_path,
            "file_count": len(files_manifest),
            "scanned_file_count": len(all_files),
            "filtered_file_count": len(upload_tasks),
            "skipped_file_count": skipped_files,
            "read_failed_count": len(failed_reads),
        }
        if failed_reads:
            result["read_failed_files"] = failed_reads[:20]

        logger.info(f"Revealed project {project_name} with {len(files_manifest)} files (v2)")

        # --- Fire-and-forget index write to revealed_files collection ---
        try:
            ctx = TraceContext.get_request_context()
            user_id = ctx.user_id or get_user_id_from_runtime(runtime) or ""
            session_id = ctx.session_id or ""
            trace_id = TraceContext.get().trace_id or ""

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
                "template": detected_template,
                "entry": result.get("entry"),
                "file_count": len(files_manifest),
                "files": {
                    k: {"url": v.get("url"), "size": v.get("size")}
                    for k, v in files_manifest.items()
                },
            }

            await get_revealed_file_storage().upsert_by_name(
                user_id=user_id,
                file_name=project_name,
                source="reveal_project",
                file_key=folder_name,
                trace_id=trace_id,
                data={
                    "file_type": "project",
                    "mime_type": None,
                    "file_size": 0,
                    "url": None,
                    "session_id": session_id,
                    "project_id": session_project_id,
                    "description": description or "",
                    "original_path": project_path,
                    "project_meta": project_meta,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to index revealed project {project_name}: {e}")

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

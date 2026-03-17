"""
Reveal Project 工具

让 Agent 可以向用户展示整个前端项目（多文件），前端使用 Sandpack 进行预览。
支持纯 HTML/CSS/JS 项目和 React/Vue 等框架项目。

工作流程：
1. Agent 调用 reveal_project 指定项目目录
2. 后端递归扫描目录，读取所有文件内容
3. 返回项目结构给前端
4. 前端用 Sandpack 渲染

返回格式：
{
    "type": "project_reveal",
    "name": "项目名称",
    "template": "react" | "vue" | "vanilla" | "static",
    "files": {
        "/App.js": "内容...",
        "/styles.css": "内容...",
    },
    "entry": "/index.html"
}
"""

import asyncio
import json
import os
from typing import Annotated, Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime

logger = get_logger(__name__)

ProjectTemplate = Literal["react", "vue", "vanilla", "static"]

FRONTEND_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".json",
    ".svg",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".webm",
    ".zip",
    ".mpg",
    ".mpeg",
    ".mov",
    ".avi",
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


def detect_template(files: dict[str, str]) -> ProjectTemplate:
    """根据 package.json 依赖检测项目模板类型"""
    if "/package.json" in files:
        try:
            package = json.loads(files["/package.json"])
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

    if "/index.html" in files:
        return "vanilla"

    return "static"


def _should_skip(rel_path: str) -> bool:
    """检查文件是否应该跳过（忽略目录/文件/二进制/非前端）"""
    parts = rel_path.strip("/").split("/")
    filename = parts[-1] if parts else ""

    if any(
        p in IGNORE_DIRS or (p.startswith(".") and p not in IGNORE_DIRS)
        for p in parts[:-1]
    ):
        return True
    if filename.startswith(".") and filename not in IGNORE_FILES:
        return True
    if filename in IGNORE_FILES:
        return True

    ext = os.path.splitext(filename)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    if ext not in FRONTEND_EXTENSIONS:
        return True

    return False


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
    # 设置 LANG 和 LC_ALL 以正确处理中文文件名
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


def _find_entry(project_files: dict[str, str]) -> Optional[str]:
    """查找项目入口文件"""
    for candidate in ENTRY_CANDIDATES:
        if candidate in project_files:
            return candidate
    return None


@tool
async def reveal_project(
    project_path: Annotated[
        str, "项目目录路径，包含 index.html 或 package.json 的目录"
    ],
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
        JSON 格式的项目信息，包含所有文件内容
    """
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        return json.dumps(
            {
                "type": "project_reveal",
                "error": "backend_not_available",
                "message": "无法访问文件系统",
            },
            ensure_ascii=False,
        )

    project_path = project_path.rstrip("/")
    project_name = name or os.path.basename(project_path)

    try:
        all_files = await _list_project_files(backend, project_path)

        if not all_files:
            return json.dumps(
                {
                    "type": "project_reveal",
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到文件",
                },
                ensure_ascii=False,
            )

        logger.info(f"Found {len(all_files)} files in {project_path}")

        # 收集前端文件
        project_files: dict[str, str] = {}

        for file_path in all_files:
            rel_path = (
                file_path[len(project_path) :]
                if file_path.startswith(project_path)
                else file_path
            )
            if not rel_path.startswith("/"):
                rel_path = "/" + rel_path

            if _should_skip(rel_path):
                continue

            content_bytes = await _download_file_from_backend(backend, file_path)
            if not content_bytes:
                logger.debug(f"Failed to read: {rel_path}")
                continue

            try:
                project_files[rel_path] = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                logger.debug(f"Not UTF-8: {rel_path}")

        if not project_files:
            return json.dumps(
                {
                    "type": "project_reveal",
                    "error": "no_frontend_files",
                    "message": f"在 {project_path} 中没有找到前端文件",
                    "scanned_files": len(all_files),
                },
                ensure_ascii=False,
            )

        result = {
            "type": "project_reveal",
            "name": project_name,
            "description": description or "",
            "template": template or detect_template(project_files),
            "files": project_files,
            "entry": _find_entry(project_files),
            "path": project_path,
            "file_count": len(project_files),
        }

        logger.info(f"Revealed project {project_name} with {len(project_files)} files")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error revealing project {project_path}: {e}", exc_info=True)
        return json.dumps(
            {
                "type": "project_reveal",
                "error": str(e),
                "message": f"读取项目失败: {e}",
            },
            ensure_ascii=False,
        )


def get_reveal_project_tool() -> BaseTool:
    """获取 reveal_project 工具实例"""
    return reveal_project

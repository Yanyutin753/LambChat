"""
Reveal Project 工具

让 Agent 可以向用户展示整个前端项目（多文件），前端使用 Sandpack 进行预览。
支持纯 HTML/CSS/JS 项目和 React/Vue 等框架项目。

工作流程：
1. Agent 调用 reveal_project 指定项目目录
2. 后端扫描目录，读取所有文件内容
3. 上传到 S3（可选，用于持久化）
4. 返回项目结构给前端
5. 前端用 Sandpack 渲染

返回格式：
{
    "type": "project_reveal",
    "name": "项目名称",
    "template": "react" | "vue" | "vanilla" | "static",
    "files": {
        "/App.js": "内容...",
        "/styles.css": "内容...",
    },
    "entry": "/index.html"  // 入口文件
}
"""

import json
import logging
import os
from typing import Any, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.tool.backend_utils import get_backend_from_runtime

logger = logging.getLogger(__name__)

# 支持的项目模板类型
ProjectTemplate = Literal["react", "vue", "vanilla", "static"]

# 常见的前端文件扩展名
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
    ".md",
}

# 需要忽略的目录和文件
IGNORE_PATTERNS = {
    "node_modules",
    ".git",
    ".venv",
    "__pycache__",
    ".DS_Store",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
}

# 二进制文件扩展名（不读取内容）
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
}


def detect_template(files: dict[str, str]) -> ProjectTemplate:
    """根据文件内容检测项目模板类型"""
    has_package_json = "/package.json" in files
    has_index_html = "/index.html" in files

    if has_package_json:
        package_content = files.get("/package.json", "{}")
        try:
            package = json.loads(package_content)
            deps = package.get("dependencies", {})
            dev_deps = package.get("devDependencies", {})

            # 检查是否有 React
            if "react" in deps or "react" in dev_deps:
                return "react"
            # 检查是否有 Vue
            if "vue" in deps or "vue" in dev_deps:
                return "vue"
        except json.JSONDecodeError:
            pass

    # 纯 HTML/CSS/JS 项目
    if has_index_html:
        return "vanilla"

    return "static"


def should_ignore(name: str) -> bool:
    """检查是否应该忽略该文件/目录"""
    if name.startswith("."):
        return True
    return name in IGNORE_PATTERNS


def is_text_file(ext: str) -> bool:
    """检查是否是文本文件"""
    return ext.lower() in FRONTEND_EXTENSIONS or ext.lower() == ".json"


def is_binary_file(ext: str) -> bool:
    """检查是否是二进制文件"""
    return ext.lower() in BINARY_EXTENSIONS


async def _read_file_from_backend(backend: Any, file_path: str) -> Optional[bytes]:
    """从 backend 读取文件内容（复用 reveal_file_tool 的逻辑）"""
    # 方式1: 沙箱模式 - 使用 download_files
    if hasattr(backend, "adownload_files"):
        try:
            download_responses = await backend.adownload_files([file_path])
            if download_responses and download_responses[0].content:
                return download_responses[0].content
        except Exception as e:
            logger.debug(f"adownload_files failed for {file_path}: {e}")

    if hasattr(backend, "download_files"):
        try:
            download_responses = backend.download_files([file_path])
            if download_responses and download_responses[0].content:
                return download_responses[0].content
        except Exception as e:
            logger.debug(f"download_files failed for {file_path}: {e}")

    # 方式2: 非沙箱模式
    if hasattr(backend, "read"):
        try:
            content = backend.read(file_path)
            if content is not None:
                if isinstance(content, str):
                    return content.encode("utf-8")
                elif isinstance(content, bytes):
                    return content
        except Exception as e:
            logger.debug(f"read failed for {file_path}: {e}")

    # 方式3: 异步读取
    if hasattr(backend, "aread"):
        try:
            content = await backend.aread(file_path)
            if content is not None:
                if isinstance(content, str):
                    return content.encode("utf-8")
                elif isinstance(content, bytes):
                    return content
        except Exception as e:
            logger.debug(f"aread failed for {file_path}: {e}")

    return None


def _list_files_from_backend(backend: Any, dir_path: str) -> list[str]:
    """列出目录下的所有文件"""
    files = []

    # 方式1: 使用 list 方法
    if hasattr(backend, "list"):
        try:
            items = backend.list(dir_path)
            for item in items:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    is_dir = item.get("is_dir", False) or item.get("type") == "directory"
                else:
                    path = str(item)
                    is_dir = False

                if path and not is_dir:
                    files.append(path)
        except Exception as e:
            logger.debug(f"list failed for {dir_path}: {e}")

    return files


@tool
async def reveal_project(
    project_path: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    template: Optional[ProjectTemplate] = None,
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
        logger.warning("Backend not available from runtime")
        return json.dumps(
            {
                "type": "project_reveal",
                "error": "backend_not_available",
                "message": "无法访问文件系统",
            },
            ensure_ascii=False,
        )

    # 规范化路径
    project_path = project_path.rstrip("/")
    project_name = name or os.path.basename(project_path)

    try:
        # 收集项目文件
        project_files: dict[str, str] = {}

        # 方式1: 如果 backend 支持 list，递归扫描
        if hasattr(backend, "list"):
            files = _list_files_from_backend(backend, project_path)

            for file_path in files:
                # 计算相对路径
                rel_path = file_path
                if rel_path.startswith(project_path):
                    rel_path = rel_path[len(project_path) :]
                if not rel_path.startswith("/"):
                    rel_path = "/" + rel_path

                # 检查是否应该忽略
                parts = rel_path.split("/")
                if any(should_ignore(part) for part in parts):
                    continue

                # 检查文件扩展名
                ext = os.path.splitext(rel_path)[1].lower()

                if is_binary_file(ext):
                    # 跳过二进制文件
                    logger.debug(f"Skipping binary file: {rel_path}")
                    continue

                if not is_text_file(ext):
                    # 跳过非前端文件
                    continue

                # 读取文件内容
                content_bytes = await _read_file_from_backend(backend, file_path)
                if content_bytes:
                    try:
                        content = content_bytes.decode("utf-8")
                        project_files[rel_path] = content
                    except UnicodeDecodeError:
                        logger.debug(f"Failed to decode file as UTF-8: {rel_path}")
                        continue

        # 方式2: 如果 backend 没有 list，尝试读取常见文件
        else:
            common_files = [
                "index.html",
                "index.js",
                "index.jsx",
                "index.ts",
                "index.tsx",
                "App.js",
                "App.jsx",
                "App.ts",
                "App.tsx",
                "main.js",
                "main.jsx",
                "main.ts",
                "main.tsx",
                "styles.css",
                "style.css",
                "App.css",
                "package.json",
            ]

            for filename in common_files:
                file_path = f"{project_path}/{filename}"
                content_bytes = await _read_file_from_backend(backend, file_path)
                if content_bytes:
                    try:
                        content = content_bytes.decode("utf-8")
                        project_files[f"/{filename}"] = content
                    except UnicodeDecodeError:
                        continue

        if not project_files:
            return json.dumps(
                {
                    "type": "project_reveal",
                    "error": "no_files_found",
                    "message": f"在 {project_path} 中没有找到前端文件",
                },
                ensure_ascii=False,
            )

        # 检测或使用指定的模板
        detected_template = template or detect_template(project_files)

        # 查找入口文件
        entry = None
        if "/index.html" in project_files:
            entry = "/index.html"
        elif f"/{detected_template == 'react' and 'App.jsx' or 'main.js'}" in project_files:
            entry = "/App.jsx" if detected_template == "react" else "/main.js"

        # 构建返回结果
        result = {
            "type": "project_reveal",
            "name": project_name,
            "description": description or "",
            "template": detected_template,
            "files": project_files,
            "entry": entry,
            "path": project_path,
            "file_count": len(project_files),
        }

        logger.info(f"Revealed project {project_name} with {len(project_files)} files")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error revealing project {project_path}: {e}")
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

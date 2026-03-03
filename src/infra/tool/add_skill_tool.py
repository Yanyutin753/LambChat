"""
Add Skill 工具

让 Agent 可以从 backend 目录导入 skill 到用户的 skill 列表。

读取指定目录中的所有文件（包括 SKILL.md 和依赖文件），
创建为用户的 skill，并发送事件通知前端刷新。
"""

import json
import logging
from typing import Optional

from deepagents.backends.protocol import BackendProtocol
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.infra.skill.storage import SkillStorage
from src.infra.tool.backend_utils import get_backend_from_runtime
from src.kernel.schemas.skill import SkillCreate, SkillSource

logger = logging.getLogger(__name__)

# Skill name maximum length
MAX_SKILL_NAME_LENGTH = 100


def _parse_skill_metadata(content: str) -> tuple[str, str]:
    """
    从 SKILL.md 内容解析 skill 名称和描述。

    查找第一个标题作为名称，标题后的第一段作为描述。

    Args:
        content: SKILL.md 文件内容

    Returns:
        (name, description) 元组
    """
    lines = content.split("\n")
    name = ""
    description = ""
    desc_lines = []
    found_title = False
    in_frontmatter = False

    for line in lines:
        # 检测 frontmatter
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        # 跳过 frontmatter 内容
        if in_frontmatter:
            continue
        # 查找第一个标题
        if line.startswith("# ") and not found_title:
            name = line[2:].strip()
            found_title = True
            continue
        # 收集描述（标题后的非空行，直到下一个标题或代码块）
        if found_title:
            if line.startswith("#") or line.startswith("```"):
                break
            if line.strip():
                desc_lines.append(line.strip())

    description = " ".join(desc_lines)[:200]  # 限制描述长度

    return name, description


async def _read_file_content(backend: BackendProtocol, file_path: str) -> Optional[str]:
    """
    从 backend 读取单个文件内容。

    Args:
        backend: Backend 实例
        file_path: 文件路径

    Returns:
        文件内容字符串，如果失败返回 None
    """
    try:
        # 尝试 read 方法
        if hasattr(backend, "read"):
            content = backend.read(file_path)
            if content is not None:
                if isinstance(content, str):
                    return content
                elif isinstance(content, bytes):
                    return content.decode("utf-8")
                elif isinstance(content, dict) and "content" in content:
                    return content["content"]

        # 尝试 aread 方法（异步）
        if hasattr(backend, "aread"):
            content = await backend.aread(file_path)
            if content is not None:
                if isinstance(content, str):
                    return content
                elif isinstance(content, bytes):
                    return content.decode("utf-8")

        # 尝试 download_files 方法（沙箱模式）
        if hasattr(backend, "adownload_files"):
            responses = await backend.adownload_files([file_path])
            if responses and responses[0].content:
                return responses[0].content.decode("utf-8")

        if hasattr(backend, "download_files"):
            responses = backend.download_files([file_path])
            if responses and responses[0].content:
                return responses[0].content.decode("utf-8")

    except Exception as e:
        logger.debug(f"Failed to read file {file_path}: {e}")

    return None


async def _read_directory_files(backend: BackendProtocol, dir_path: str) -> dict[str, str]:
    """
    从 backend 读取目录中的所有文件。

    Args:
        backend: Backend 实例
        dir_path: 目录路径

    Returns:
        文件相对路径到内容的映射
    """
    files = {}

    # 规范化目录路径
    dir_path = dir_path.rstrip("/")

    try:
        # 方式1: 使用 list 方法（同步）
        if hasattr(backend, "list"):
            entries = backend.list(dir_path)
            for entry in entries:
                if isinstance(entry, str):
                    file_path = f"{dir_path}/{entry}"
                elif isinstance(entry, dict):
                    file_path = entry.get("path", "")
                else:
                    continue

                # 读取文件内容
                content = await _read_file_content(backend, file_path)
                if content is not None:
                    # 使用相对路径作为 key
                    relative_path = file_path.replace(f"{dir_path}/", "", 1)
                    files[relative_path] = content

        # 方式2: 使用 alist 方法（异步）
        elif hasattr(backend, "alist"):
            entries = await backend.alist(dir_path)
            for entry in entries:
                if isinstance(entry, str):
                    file_path = f"{dir_path}/{entry}"
                elif isinstance(entry, dict):
                    file_path = entry.get("path", "")
                else:
                    continue

                content = await _read_file_content(backend, file_path)
                if content is not None:
                    relative_path = file_path.replace(f"{dir_path}/", "", 1)
                    files[relative_path] = content

    except Exception as e:
        logger.error(f"Failed to list directory {dir_path}: {e}")

    return files


@tool
async def add_skill_from_path(
    skill_path: str,
    skill_name: Optional[str] = None,
    description: Optional[str] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    从 backend 目录导入 skill 到用户的 skill 列表。

    读取指定目录中的所有文件（包括 SKILL.md 和依赖文件），
    创建为用户的 skill。导入成功后，前端会自动刷新 skill 列表。

    使用场景：
    - 用户想要将 backend 中已有的 skill 文件添加到自己的 skill 列表
    - Agent 发现了一个有用的 skill 目录，想要帮用户导入

    Args:
        skill_path: skill 目录路径（相对于工作目录或绝对路径）
                   目录中应该包含 SKILL.md 文件作为主文件
        skill_name: 自定义 skill 名称（可选，默认从 SKILL.md 解析）
        description: skill 描述（可选，默认从 SKILL.md 解析）

    Returns:
        JSON 格式结果，包含 skill 信息或错误信息
    """
    # 获取 backend
    backend = get_backend_from_runtime(runtime)

    if backend is None:
        logger.warning("Backend not available from runtime")
        result = {
            "type": "skill_added",
            "success": False,
            "error": "backend_unavailable",
            "message": "Backend is not available. Please try again later.",
        }
        return json.dumps(result, ensure_ascii=False)

    # 规范化路径
    skill_path = skill_path.rstrip("/")

    # 基本路径遍历检查
    if ".." in skill_path:
        result = {
            "type": "skill_added",
            "success": False,
            "error": "invalid_path",
            "message": "Path traversal not allowed in skill_path.",
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        # 读取目录中的所有文件
        files = await _read_directory_files(backend, skill_path)

        if not files:
            result = {
                "type": "skill_added",
                "success": False,
                "error": "directory_empty",
                "message": f"No files found in directory: {skill_path}",
            }
            return json.dumps(result, ensure_ascii=False)

        # 查找 SKILL.md 文件
        skill_md_content = files.get("SKILL.md") or files.get("skill.md")

        if skill_md_content is None:
            # 尝试查找任何 .md 文件
            for fname, content in files.items():
                if fname.endswith(".md"):
                    skill_md_content = content
                    break

        # 解析名称和描述
        if skill_md_content:
            parsed_name, parsed_desc = _parse_skill_metadata(skill_md_content)
            if not skill_name:
                skill_name = parsed_name
            if not description:
                description = parsed_desc
        else:
            # 使用目录名作为 skill 名称
            if not skill_name:
                skill_name = skill_path.split("/")[-1]
            if not description:
                description = f"Skill imported from {skill_path}"

        if not skill_name:
            result = {
                "type": "skill_added",
                "success": False,
                "error": "invalid_skill_name",
                "message": "Could not determine skill name. Please provide skill_name parameter.",
            }
            return json.dumps(result, ensure_ascii=False)

        # 验证 skill name 长度
        if len(skill_name) > MAX_SKILL_NAME_LENGTH:
            result = {
                "type": "skill_added",
                "success": False,
                "error": "skill_name_too_long",
                "message": f"Skill name exceeds maximum length of {MAX_SKILL_NAME_LENGTH} characters.",
            }
            return json.dumps(result, ensure_ascii=False)

        # 获取 user_id
        user_id = None
        if runtime and hasattr(runtime, "config"):
            config = runtime.config
            if isinstance(config, dict):
                user_id = config.get("configurable", {}).get("user_id")

        if not user_id:
            result = {
                "type": "skill_added",
                "success": False,
                "error": "user_not_authenticated",
                "message": "User ID not found. Please authenticate first.",
            }
            return json.dumps(result, ensure_ascii=False)

        # 创建 SkillCreate 对象
        skill_create = SkillCreate(
            name=skill_name,
            description=description or "",
            content="",  # 使用 files 字段
            files=files,
            enabled=True,
            source=SkillSource.MANUAL,
        )

        # 存储 skill
        storage = SkillStorage()
        user_skill = await storage.create_user_skill(skill_create, user_id)

        result = {
            "type": "skill_added",
            "success": True,
            "skill": {
                "name": user_skill.name,
                "description": user_skill.description,
                "files_count": len(files),
            },
            "message": f"Successfully imported skill '{skill_name}' with {len(files)} files.",
        }

        logger.info(
            f"[add_skill_from_path] Successfully imported skill '{skill_name}' for user {user_id}"
        )
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[add_skill_from_path] Error importing skill from {skill_path}: {e}")
        result = {
            "type": "skill_added",
            "success": False,
            "error": "import_failed",
            "message": f"Failed to import skill: {str(e)}",
        }
        return json.dumps(result, ensure_ascii=False)


def get_add_skill_tool() -> BaseTool:
    """获取 add_skill_from_path 工具实例"""
    return add_skill_from_path

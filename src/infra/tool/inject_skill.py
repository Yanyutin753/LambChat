"""
Inject Skill 工具

让 Agent 可以按需加载技能到沙箱。
只有当 LLM 需要使用某个技能时，才会将技能文件加载到沙箱中。

分布式安全设计：
- 不依赖 ContextVar（无法跨进程/Worker 工作）
- 通过全局 SkillsMiddleware 实例管理
"""

import json
import logging
from typing import TYPE_CHECKING, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from src.infra.skill.middleware import SkillsMiddleware

logger = logging.getLogger(__name__)

# 全局 SkillsMiddleware 实例，由 agent_node 设置
_global_middleware: Optional["SkillsMiddleware"] = None


def set_skills_middleware(middleware: "SkillsMiddleware") -> None:
    """设置全局 SkillsMiddleware 实例（在 agent_node 中调用）"""
    global _global_middleware
    _global_middleware = middleware


def get_skills_middleware() -> Optional["SkillsMiddleware"]:
    """获取全局 SkillsMiddleware 实例"""
    return _global_middleware


@tool
async def inject_skill(
    skill_name: str,
    runtime: Optional[ToolRuntime] = None,
) -> str:
    """
    Load a skill into sandbox and return its SKILL.md content.

    Call this tool when you want to use a skill. The skill files will be
    loaded into the sandbox at {skill_path}/.

    This tool should be called BEFORE using any skill to ensure the skill
    files are available in the sandbox.

    Args:
        skill_name: Name of the skill to inject (e.g., "fullstack-template-generator")

    Returns:
        JSON with skill information:
        - success: Whether the skill was loaded successfully
        - skill_path: Directory path where skill files are located in sandbox
        - skill_instructions: The full SKILL.md content with usage instructions
        - error: Error message if failed
    """
    middleware = get_skills_middleware()

    if middleware is None:
        result = {
            "success": False,
            "error": "SkillsMiddleware not initialized. Skills feature may be disabled.",
            "available_skills": [],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 检查技能是否已加载
    if middleware.is_skill_loaded(skill_name):
        workspace_dir = await middleware.get_workspace_dir()
        skill_path = f"{workspace_dir}/skills/{skill_name}"
        result = {
            "success": True,
            "skill_name": skill_name,
            "skill_path": skill_path,
            "message": f"Skill '{skill_name}' is already loaded at {skill_path}/. Use read_file to explore files.",
            "already_loaded": True,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 注入技能到沙箱
    inject_result = await middleware.inject_single_skill_to_sandbox(skill_name)

    if inject_result["success"]:
        skill_path = inject_result["skill_path"]
        result = {
            "success": True,
            "skill_name": skill_name,
            "skill_path": skill_path,
            "skill_instructions": inject_result["skill_instructions"],
            "message": f"Skill '{skill_name}' loaded at {skill_path}/. Use read_file to explore additional files.",
        }
    else:
        # 获取可用的技能列表
        available_skills: list[str] = []
        try:
            skills = await middleware.load_all_skills_async()
            available_skills = [s["name"] for s in skills if s.get("name")]
        except Exception:
            pass

        result = {
            "success": False,
            "skill_name": skill_name,
            "error": inject_result.get("error", "Unknown error"),
            "available_skills": available_skills,
        }

    return json.dumps(result, ensure_ascii=False, indent=2)


def get_inject_skill_tool() -> BaseTool:
    """获取 inject_skill 工具实例"""
    return inject_skill

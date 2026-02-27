"""
技能注入模块

从数据库读取技能并注入到系统提示中。
支持用户级别的技能访问。
同时负责将技能注入到 Sandbox 文件系统。
"""

import base64
import logging
from typing import TYPE_CHECKING, Optional

from src.infra.skill.manager import SkillManager
from src.kernel.config import settings

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)


class SkillsMiddleware:
    """
    技能注入中间件

    从数据库读取技能内容，注入到 Agent 的系统提示中。
    支持用户级别的技能访问（系统技能 + 用户技能）。

    如果提供了 user_id，将使用用户级别的技能访问。
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        sandbox: Optional["SandboxBackendProtocol"] = None,
    ):
        """
        初始化技能中间件

        Args:
            user_id: 用户 ID，用于获取用户级别的技能
            sandbox: Sandbox 实例，用于注入技能到沙箱文件系统
        """
        self._user_id = user_id

        # Sandbox 相关（用于注入技能到沙箱）
        self._sandbox = sandbox
        self._workspace_dir: str | None = None

        # 初始化管理器
        self._manager = SkillManager(user_id=user_id)

        # 跟踪已加载的技能，避免重复加载
        self._loaded_skills: set[str] = set()

    async def get_workspace_dir(self) -> str:
        """获取 sandbox 的工作目录"""
        if self._workspace_dir is None:
            if self._sandbox is None:
                return "/"
            result = await self._sandbox.aexecute("pwd")
            if result.exit_code == 0:
                self._workspace_dir = result.output.strip()
            else:
                self._workspace_dir = "/"
                logger.warning(f"Failed to get pwd, using default: {self._workspace_dir}")
        return self._workspace_dir

    async def inject_skills_async(self, system_prompt: str) -> str:
        """
        将技能内容注入到系统提示中（异步版本，包含 MongoDB）

        Args:
            system_prompt: 原始系统提示

        Returns:
            注入技能后的系统提示
        """
        skills_content = await self.load_all_skills_async()

        if not skills_content:
            return system_prompt

        # 构建技能提示
        skills_prompt = await self._build_skills_prompt(skills_content)

        # 将技能插入到系统提示中
        if "{skills}" in system_prompt:
            return system_prompt.replace("{skills}", skills_prompt)
        else:
            # 追加到系统提示末尾
            return f"{system_prompt}\n\n{skills_prompt}"

    async def inject_skills_to_sandbox(self) -> int:
        """
        将用户的有效技能注入到 Sandbox 文件系统

        Returns:
            注入的文件数量
        """
        if self._sandbox is None:
            logger.warning("No sandbox provided, skipping skill injection")
            return 0

        if not self._user_id:
            logger.warning("No user_id provided, skipping skill injection")
            return 0

        # 获取用户的有效技能
        skills = await self._manager.get_effective_skills()
        logger.info(f"effective_skills: {skills}")

        if not skills:
            logger.info(f"No skills to inject for user {self._user_id}")
            return 0

        # 准备文件写入列表
        files_to_write: list[tuple[str, str]] = []

        for skill_name, skill_data in skills.items():
            skill_files = skill_data.get("files", {})
            skill_content = skill_data.get("content", "")

            # 如果有多个文件（新格式）
            if skill_files:
                for file_name, file_content in skill_files.items():
                    path = f"skills/{skill_name}/{file_name}"
                    files_to_write.append((path, file_content))
            # 否则只有主内容（旧格式兼容）
            elif skill_content:
                path = f"skills/{skill_name}/SKILL.md"
                files_to_write.append((path, skill_content))

        if not files_to_write:
            logger.info(f"No skill files to write for user {self._user_id}")
            return 0

        # 获取工作目录
        workspace_dir = await self.get_workspace_dir()

        # 写入到 Sandbox
        try:
            # 收集所有需要创建的目录
            dirs_to_create: set[str] = set()
            for path, _ in files_to_write:
                dir_path = "/".join(path.split("/")[:-1])
                if dir_path:
                    dirs_to_create.add(f"{workspace_dir}/{dir_path}")

            # 一次性创建所有目录
            if dirs_to_create:
                mkdir_cmd = f"mkdir -p {' '.join(sorted(dirs_to_create))}"
                result = await self._sandbox.aexecute(mkdir_cmd)
                if result.exit_code != 0:
                    logger.warning(f"Failed to create directories: {result.output}")
                    return 0

            # 构建批量写入脚本（使用 base64 编码避免转义问题）
            script_parts = ["#!/bin/bash", "set -e", ""]
            for path, content in files_to_write:
                full_path = f"{workspace_dir}/{path}"
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                script_parts.append(f"echo '{content_b64}' | base64 -d > '{full_path}'")

            script = "\n".join(script_parts)
            script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
            result = await self._sandbox.aexecute(f"echo '{script_b64}' | base64 -d | bash")

            if result.exit_code == 0:
                success_count = len(files_to_write)
                logger.info(
                    f"Injected {success_count}/{len(files_to_write)} skill files to sandbox"
                )
                return success_count
            else:
                logger.warning(f"Failed to write skill files: {result.output}")
                return 0

        except Exception as e:
            logger.error(f"Failed to inject skills: {e}", exc_info=True)
            return 0

    async def inject_single_skill_to_sandbox(self, skill_name: str) -> dict:
        """
        将单个技能注入到 Sandbox（按需调用）

        Args:
            skill_name: 技能名称

        Returns:
            {
                "success": bool,
                "skill_path": str,          # e.g., "/workspace/skills/my-skill"
                "skill_instructions": str,  # SKILL.md 内容（使用指南）
                "error": str,               # 错误信息（如果失败）
            }
        """
        result = {
            "success": False,
            "skill_path": "",
            "skill_instructions": "",
            "error": "",
        }

        if self._sandbox is None:
            result["error"] = "No sandbox available"
            return result

        # 检查是否已加载
        if skill_name in self._loaded_skills:
            workspace_dir = await self.get_workspace_dir()
            result["success"] = True
            result["skill_path"] = f"{workspace_dir}/skills/{skill_name}"
            result["error"] = "Skill already loaded"
            logger.info(f"Skill '{skill_name}' already loaded, skipping")
            return result

        # 获取技能数据
        skill_data = await self._manager.get_skill_async(skill_name)
        if not skill_data:
            result["error"] = f"Skill '{skill_name}' not found"
            logger.warning(f"Skill '{skill_name}' not found")
            return result

        # 准备文件写入列表
        files_to_write: list[tuple[str, str]] = []
        skill_files = skill_data.get("files", {})
        skill_content = skill_data.get("content", "")

        if skill_files:
            for file_name, file_content in skill_files.items():
                path = f"skills/{skill_name}/{file_name}"
                files_to_write.append((path, file_content))
        elif skill_content:
            path = f"skills/{skill_name}/SKILL.md"
            files_to_write.append((path, skill_content))

        if not files_to_write:
            result["error"] = f"No files to write for skill '{skill_name}'"
            return result

        # 获取工作目录
        workspace_dir = await self.get_workspace_dir()

        try:
            # 创建目录
            dir_path = f"{workspace_dir}/skills/{skill_name}"
            mkdir_cmd = f"mkdir -p {dir_path}"
            mkdir_result = await self._sandbox.aexecute(mkdir_cmd)
            if mkdir_result.exit_code != 0:
                result["error"] = f"Failed to create directory: {mkdir_result.output}"
                return result

            # 写入文件
            script_parts = ["#!/bin/bash", "set -e", ""]
            for path, content in files_to_write:
                full_path = f"{workspace_dir}/{path}"
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                script_parts.append(f"echo '{content_b64}' | base64 -d > '{full_path}'")

            script = "\n".join(script_parts)
            script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
            write_result = await self._sandbox.aexecute(f"echo '{script_b64}' | base64 -d | bash")

            if write_result.exit_code == 0:
                # 标记为已加载
                self._loaded_skills.add(skill_name)

                # 获取 SKILL.md 内容作为 skill_instructions
                skill_instructions = skill_files.get("SKILL.md", skill_content)

                result["success"] = True
                result["skill_path"] = f"{workspace_dir}/skills/{skill_name}"
                result["skill_instructions"] = skill_instructions

                logger.info(
                    f"Successfully injected skill '{skill_name}' with {len(files_to_write)} files"
                )
            else:
                result["error"] = f"Failed to write files: {write_result.output}"

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Failed to inject skill '{skill_name}': {e}", exc_info=True)

        return result

    def is_skill_loaded(self, skill_name: str) -> bool:
        """检查技能是否已加载到沙箱"""
        return skill_name in self._loaded_skills

    async def load_all_skills_async(self) -> list[dict]:
        """加载所有技能（PostgreSQL/MongoDB）"""
        if not self._user_id:
            logger.warning("No user_id provided, cannot load skills")
            return []

        try:
            effective = await self._manager.get_effective_skills()
            skills = []
            for _, skill in effective.items():
                if hasattr(skill, "model_dump"):
                    skill_dict = skill.model_dump()
                else:
                    skill_dict = dict(skill) if not isinstance(skill, dict) else skill
                skill_dict["is_system"] = skill_dict.get("is_system", True)
                skills.append(skill_dict)
            return [s for s in skills if s.get("enabled", True)]
        except Exception as e:
            logger.warning(f"Failed to load skills for user {self._user_id}: {e}")
            return []

    async def _build_skills_prompt(self, skills: list[dict]) -> str:
        """Build skills prompt text (metadata only, full content loaded via inject_skill tool)"""
        if not skills:
            return ""

        lines = ["# Available Skills", ""]
        lines.append(
            "The following skills are available. To use a skill, call `inject_skill` with the skill name."
        )
        lines.append(
            "This will load the skill files into the sandbox and return the full SKILL.md content."
        )
        lines.append("")

        for skill in skills:
            name = skill.get("name", "unnamed skill")
            description = skill.get("description", "no description")
            lines.append(f"- **{name}**: {description}")

        lines.append("")
        lines.append(
            "**Important**: Always call `inject_skill(skill_name)` before using a skill to ensure it's loaded."
        )
        lines.append("")

        return "\n".join(lines)


def get_skills_middleware(
    user_id: Optional[str] = None,
) -> SkillsMiddleware:
    """
    获取技能中间件实例

    Args:
        user_id: 用户 ID，用于获取用户级别的技能
    """
    return SkillsMiddleware(user_id=user_id)

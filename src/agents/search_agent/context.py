"""
Search Agent 上下文管理 - 支持工具和 Skills
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agents.core.tool_filter import (
    filter_disabled_tools,
    filter_mcp_tools_by_db_state,
    get_db_disabled_mcp_tool_names,
)
from src.infra.logging import get_logger
from src.infra.skill import load_skill_files
from src.infra.tool.human_tool import get_human_tool
from src.infra.tool.internal_registry import get_internal_tools_by_exposure_for_user
from src.infra.tool.mcp_global import get_global_mcp_tools
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.infra.tool.transfer_file_tool import get_transfer_file_tool, get_transfer_path_tool
from src.kernel.config import settings

if TYPE_CHECKING:
    from src.infra.backend import LazySandboxBackend
    from src.infra.tool.deferred_manager import DeferredToolManager
    from src.infra.tool.mcp_client import MCPClientManager

logger = get_logger(__name__)


class SearchAgentContext:
    """
    Search Agent 上下文 - 支持工具和技能

    特点：
    - 支持 Skills
    - 支持 MCP 工具
    """

    def __init__(
        self,
        session_id: str | None = None,
        agent_id: str = "search",
        user_id: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
        disabled_skills: Optional[List[str]] = None,
        enabled_skills: Optional[List[str]] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
        auto_mode: bool = False,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_id = agent_id
        self.user_id = user_id
        self.disabled_tools = disabled_tools
        self.disabled_skills = disabled_skills
        self.enabled_skills = enabled_skills
        self.disabled_mcp_tools = disabled_mcp_tools
        self.auto_mode = auto_mode
        self.mcp_manager: Optional[MCPClientManager] = None
        self._mcp_loaded: bool = False
        self.tools: List[Any] = []
        self.skills: List[dict] = []
        self.skill_files: Dict[str, Any] = {}
        self.deferred_manager: Optional["DeferredToolManager"] = None
        self._deferred_system_tools: List[Any] = []
        self.run_sandbox: Optional["LazySandboxBackend"] = None

    def set_run_sandbox(self, sandbox: "LazySandboxBackend") -> None:
        """Register the run-scoped sandbox owned by this context."""
        self.run_sandbox = sandbox

    def _append_unique_tools(self, tools: List[Any], *, reserved: set[str] | None = None) -> None:
        existing = {getattr(tool, "name", "") for tool in self.tools}
        blocked = reserved or set()
        for tool in tools:
            name = getattr(tool, "name", "")
            if name and name not in existing and name not in blocked:
                self.tools.append(tool)
                existing.add(name)

    def apply_skill_filters(self) -> None:
        """Apply whitelist/blacklist filters to loaded skills and skill files."""
        disabled_set = set(self.disabled_skills or [])
        if self.enabled_skills is not None:
            enabled_set = set(self.enabled_skills)
            self.skills = [
                s
                for s in self.skills
                if s.get("name") in enabled_set and s.get("name") not in disabled_set
            ]
            if self.skill_files:
                self.skill_files = {
                    path: data
                    for path, data in self.skill_files.items()
                    if (skill_name := path.strip("/").split("/", 1)[0]) in enabled_set
                    and skill_name not in disabled_set
                }
            return

        if disabled_set:
            self.skills = [s for s in self.skills if s.get("name") not in disabled_set]
            if self.skill_files:
                self.skill_files = {
                    path: data
                    for path, data in self.skill_files.items()
                    if path.strip("/").split("/", 1)[0] not in disabled_set
                }

    async def _lazy_load_mcp_tools(self) -> None:
        """懒加载 MCP 工具（仅在首次调用 get_tools 时初始化）"""
        if self._mcp_loaded:
            return  # 已经尝试过加载

        self._mcp_loaded = True

        if not settings.ENABLE_MCP:
            logger.debug("[SearchAgentContext] MCP is disabled (ENABLE_MCP=False)")
            return

        try:
            logger.info(f"[SearchAgentContext] Lazy loading MCP tools for user {self.user_id}")
            # 使用全局缓存，避免重复初始化
            assert self.user_id is not None  # Already guarded above
            mcp_tools, self.mcp_manager = await get_global_mcp_tools(self.user_id)
            logger.info(
                f"[SearchAgentContext] Loaded {len(mcp_tools)} MCP tools (before DB filter)"
            )

            # 过滤数据库中标记为 system_disabled / user_disabled 的工具
            db_disabled = await get_db_disabled_mcp_tool_names(self.user_id)
            mcp_tools = filter_mcp_tools_by_db_state(mcp_tools, db_disabled)
            logger.info(
                f"[SearchAgentContext] After DB filter: {len(mcp_tools)} MCP tools "
                f"(removed {len(db_disabled)} disabled names)"
            )

            from src.agents.core.mcp_tool_exposure import split_mcp_tools_for_exposure

            inline_mcp_tools, deferred_mcp_tools = split_mcp_tools_for_exposure(
                mcp_tools,
                getattr(self.mcp_manager, "_server_tool_policies", {}),
            )
            reserved_system_names = {
                getattr(tool, "name", "") for tool in self._deferred_system_tools
            }
            if not settings.ENABLE_DEFERRED_TOOL_LOADING:
                inline_mcp_tools = inline_mcp_tools + deferred_mcp_tools
                deferred_mcp_tools = []

            if inline_mcp_tools:
                self._append_unique_tools(inline_mcp_tools, reserved=reserved_system_names)
                logger.info(
                    "[SearchAgentContext] Inlined %d MCP tool(s) by policy",
                    len(inline_mcp_tools),
                )

            # 延迟加载决策：工具总数超过阈值时延迟 MCP 工具
            if (
                settings.ENABLE_DEFERRED_TOOL_LOADING
                and deferred_mcp_tools
                and (len(self.tools) + len(deferred_mcp_tools)) > settings.DEFERRED_TOOL_THRESHOLD
            ):
                from src.infra.tool.deferred_manager import (
                    DeferredToolManager,
                    merge_discovered_names,
                    restore_discovered_tools,
                )

                # 恢复上次已发现的工具名（跨 turn 持久化，按发现顺序回放，
                # 与在线追加顺序保持一致以稳定 tools 缓存前缀）
                pre_discovered = await restore_discovered_tools(self.session_id)
                if self.deferred_manager is not None:
                    pre_discovered = merge_discovered_names(
                        pre_discovered, self.deferred_manager.discovered_names
                    )

                direct_names = {getattr(tool, "name", "") for tool in self.tools}
                deferred_mcp_tools = [
                    tool
                    for tool in deferred_mcp_tools
                    if getattr(tool, "name", "") not in direct_names
                ]

                self.deferred_manager = DeferredToolManager(
                    all_deferred_tools=deferred_mcp_tools,
                    deferred_system_tools=self._deferred_system_tools,
                    session_id=self.session_id,
                    disabled_tools=self.disabled_tools,
                    disabled_mcp_tools=self.disabled_mcp_tools,
                    pre_discovered_names=pre_discovered,
                )
                logger.info(
                    f"[SearchAgentContext] Deferred {len(deferred_mcp_tools)} MCP tools "
                    f"(builtin={len(self.tools)}, threshold={settings.DEFERRED_TOOL_THRESHOLD}, "
                    f"pre_restored={len(pre_discovered)})"
                )
            else:
                # 低于阈值或未启用延迟：走原有逻辑
                self._append_unique_tools(deferred_mcp_tools, reserved=reserved_system_names)

        except Exception as e:
            logger.error(f"[SearchAgentContext] Failed to load MCP tools: {e}", exc_info=True)

    async def get_tools(self) -> List[Any]:
        """获取所有工具（懒加载 MCP 工具）"""
        await self._lazy_load_mcp_tools()
        return self.tools

    def filter_tools(self) -> List[Any]:
        """根据 disabled_tools 和 disabled_mcp_tools 过滤工具（使用共享过滤逻辑）"""
        filtered = filter_disabled_tools(
            self.tools,
            disabled_tools=self.disabled_tools,
            disabled_mcp_tools=self.disabled_mcp_tools,
            auto_mode=self.auto_mode,
        )
        logger.debug(
            "[SearchAgentContext] Tool filtering: %d/%d tools enabled (auto_mode=%s)",
            len(filtered),
            len(self.tools),
            self.auto_mode,
        )
        return filtered

    async def setup(self) -> None:
        """初始化：工具 + 技能"""
        logger.info(
            f"[SearchAgentContext] Starting setup, ENABLE_SKILLS={settings.ENABLE_SKILLS}, ENABLE_MCP={settings.ENABLE_MCP}"
        )

        # 基础工具
        human_tool = get_human_tool(session_id=self.session_id)
        self.tools.append(human_tool)
        logger.info("[SearchAgentContext] Added human tool")

        reveal_file_tool = get_reveal_file_tool()
        self.tools.append(reveal_file_tool)
        logger.info("[SearchAgentContext] Added reveal_file tool")

        reveal_project_tool = get_reveal_project_tool()
        self.tools.append(reveal_project_tool)
        logger.info("[SearchAgentContext] Added reveal_project tool")

        transfer_file_tool = get_transfer_file_tool()
        self.tools.append(transfer_file_tool)
        logger.info("[SearchAgentContext] Added transfer_file tool")

        transfer_path_tool = get_transfer_path_tool()
        self.tools.append(transfer_path_tool)
        logger.info("[SearchAgentContext] Added transfer_path tool")

        try:
            from src.infra.mcp.quota import resolve_user_mcp_access

            user_roles, is_admin = (
                await resolve_user_mcp_access(self.user_id) if self.user_id else ([], False)
            )
            direct_internal, deferred_internal = await get_internal_tools_by_exposure_for_user(
                user_id=self.user_id,
                user_roles=user_roles,
                is_admin=is_admin,
            )
            if not settings.ENABLE_DEFERRED_TOOL_LOADING:
                direct_internal = direct_internal + deferred_internal
                deferred_internal = []
            self._append_unique_tools(direct_internal)
            direct_names = {getattr(tool, "name", "") for tool in self.tools}
            self._deferred_system_tools = [
                tool for tool in deferred_internal if getattr(tool, "name", "") not in direct_names
            ]
            if self._deferred_system_tools:
                from src.infra.tool.deferred_manager import DeferredToolManager

                self.deferred_manager = DeferredToolManager(
                    all_deferred_tools=[],
                    deferred_system_tools=self._deferred_system_tools,
                    session_id=self.session_id,
                    disabled_tools=self.disabled_tools,
                )
            logger.info(
                "[SearchAgentContext] Added %d direct and %d deferred internal tools",
                len(direct_internal),
                len(self._deferred_system_tools),
            )
        except Exception as e:
            logger.warning(f"[SearchAgentContext] Failed to load internal tools: {e}")

        try:
            from src.infra.tool.env_var_tool import get_env_var_tools

            existing_tool_names = {getattr(tool, "name", "") for tool in self.tools}
            existing_tool_names.update(
                getattr(tool, "name", "") for tool in self._deferred_system_tools
            )
            env_var_tools = [
                tool
                for tool in get_env_var_tools()
                if getattr(tool, "name", "") not in existing_tool_names
            ]
            self.tools.extend(env_var_tools)
            logger.info(f"[SearchAgentContext] Added {len(env_var_tools)} env var tools")
        except Exception as e:
            logger.warning(f"[SearchAgentContext] Failed to load env var tools: {e}")

        # Memory 工具（原生 MongoDB 后端）
        if settings.ENABLE_MEMORY:
            try:
                from src.infra.memory.tools import get_all_memory_tools

                memory_tools = get_all_memory_tools()
                self.tools.extend(memory_tools)
                logger.info(f"[SearchAgentContext] Added {len(memory_tools)} memory tools")
            except ImportError:
                logger.warning("[SearchAgentContext] memory tools import failed, skipping")
            except Exception as e:
                logger.warning(f"[SearchAgentContext] Failed to load memory tools: {e}")

        # 沙箱专属工具
        if settings.ENABLE_SANDBOX:
            from src.infra.tool.upload_url_tool import get_upload_url_tool

            self.tools.append(get_upload_url_tool())
            logger.info("[SearchAgentContext] Added upload_url_to_sandbox tool (sandbox mode)")

        # MCP 工具延迟加载（不在 setup 时初始化）
        logger.info("[SearchAgentContext] MCP tools will be lazy loaded on first use")

        # 加载技能
        if settings.ENABLE_SKILLS:
            try:
                skill_result = await load_skill_files(self.user_id)
                self.skill_files = skill_result["files"]
                self.skills = skill_result["skills"]

                before_count = len(self.skills)
                self.apply_skill_filters()
                if self.enabled_skills is not None:
                    logger.info(
                        f"[SearchAgentContext] Applied enabled_skills whitelist, {len(self.skills)}/{before_count} remaining"
                    )
                elif self.disabled_skills:
                    logger.info(
                        f"[SearchAgentContext] Filtered out {len(self.disabled_skills)} disabled skills, {len(self.skills)} remaining"
                    )

                logger.info(
                    f"[SearchAgentContext] Loaded {len(self.skills)} skills, "
                    f"{len(self.skill_files)} skill files"
                )
            except Exception as e:
                logger.warning(f"[SearchAgentContext] Failed to load skills: {e}")

        if settings.ENABLE_SKILLS and self.skills:
            from src.infra.skill.skill_search_tool import SkillSearchTool

            self._append_unique_tools([SkillSearchTool(self.skills)])

        logger.info(f"[SearchAgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理

        注意：MCP 管理器是全局单例，不在这里关闭。
        如果需要清理全局缓存，使用 invalidate_global_cache()。
        """
        sandbox = self.run_sandbox
        self.run_sandbox = None
        if sandbox is not None:
            await sandbox.aclose()

        # MCP 管理器是全局单例，不在这里关闭
        # 如果需要清理，使用 src.infra.tool.mcp_global.invalidate_global_cache()

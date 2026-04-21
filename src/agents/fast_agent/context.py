"""
Fast Agent 上下文管理 - 无沙箱，支持工具和 Skills

不使用沙箱，但保留工具和技能支持。
"""

import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from src.agents.core.tool_filter import (
    filter_disabled_tools,
    filter_mcp_tools_by_db_state,
    get_db_disabled_mcp_tool_names,
)
from src.infra.logging import get_logger
from src.infra.skill.manager import SkillManager
from src.infra.tool.human_tool import get_human_tool
from src.infra.tool.mcp_global import get_global_mcp_tools
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.infra.tool.transfer_file_tool import get_transfer_file_tool, get_transfer_path_tool
from src.kernel.config import settings

if TYPE_CHECKING:
    from src.infra.tool.deferred_manager import DeferredToolManager
    from src.infra.tool.mcp_client import MCPClientManager

logger = get_logger(__name__)


class FastAgentContext:
    """
    Fast Agent 上下文 - 无沙箱，支持工具和技能

    特点：
    - 不使用沙箱
    - 支持 Skills
    - 支持 MCP 工具
    """

    def __init__(
        self,
        session_id: str = str(uuid.uuid4()),
        agent_id: str = "fast",
        user_id: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
        disabled_skills: Optional[List[str]] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.disabled_tools = disabled_tools
        self.disabled_skills = disabled_skills
        self.disabled_mcp_tools = disabled_mcp_tools
        self.mcp_manager: Optional[MCPClientManager] = None
        self._mcp_loaded: bool = False
        self.tools: List[Any] = []
        self.skills: List[dict] = []
        self.deferred_manager: Optional["DeferredToolManager"] = None

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
        )
        logger.debug(
            "[FastAgentContext] Tool filtering: %d/%d tools enabled",
            len(filtered),
            len(self.tools),
        )
        return filtered

    async def _lazy_load_mcp_tools(self) -> None:
        """懒加载 MCP 工具（仅在首次调用 get_tools 时初始化）"""
        if self._mcp_loaded:
            return  # 已经尝试过加载

        self._mcp_loaded = True

        if not settings.ENABLE_MCP:
            logger.debug("[FastAgentContext] MCP is disabled (ENABLE_MCP=False)")
            return

        try:
            logger.info(f"[FastAgentContext] Lazy loading MCP tools for user {self.user_id}")
            # 使用全局缓存，避免重复初始化
            assert self.user_id is not None  # Already guarded above
            mcp_tools, self.mcp_manager = await get_global_mcp_tools(self.user_id)
            logger.info(f"[FastAgentContext] Loaded {len(mcp_tools)} MCP tools (before DB filter)")

            # 过滤数据库中标记为 system_disabled / user_disabled 的工具
            db_disabled = await get_db_disabled_mcp_tool_names(self.user_id)
            mcp_tools = filter_mcp_tools_by_db_state(mcp_tools, db_disabled)
            logger.info(
                f"[FastAgentContext] After DB filter: {len(mcp_tools)} MCP tools "
                f"(removed {len(db_disabled)} disabled names)"
            )

            if (
                settings.ENABLE_DEFERRED_TOOL_LOADING
                and mcp_tools
                and (len(self.tools) + len(mcp_tools)) > settings.DEFERRED_TOOL_THRESHOLD
            ):
                from src.infra.tool.deferred_manager import (
                    DeferredToolManager,
                    restore_discovered_tools,
                )

                pre_discovered = await restore_discovered_tools(self.session_id)

                self.deferred_manager = DeferredToolManager(
                    all_deferred_tools=mcp_tools,
                    session_id=self.session_id,
                    disabled_tools=self.disabled_tools,
                    disabled_mcp_tools=self.disabled_mcp_tools,
                    pre_discovered_names=pre_discovered,
                )
                logger.info(
                    f"[FastAgentContext] Deferred {len(mcp_tools)} MCP tools "
                    f"(builtin={len(self.tools)}, threshold={settings.DEFERRED_TOOL_THRESHOLD}, "
                    f"pre_restored={len(pre_discovered)})"
                )
            else:
                self.tools.extend(mcp_tools)
        except Exception as e:
            logger.error(f"[FastAgentContext] Failed to load MCP tools: {e}", exc_info=True)

    async def setup(self) -> None:
        """初始化：工具 + 技能"""
        logger.info(
            f"[FastAgentContext] Starting setup, ENABLE_SKILLS={settings.ENABLE_SKILLS}, ENABLE_MCP={settings.ENABLE_MCP}"
        )

        # 基础工具
        human_tool = get_human_tool(session_id=self.session_id)
        self.tools.append(human_tool)
        logger.info("[FastAgentContext] Added human tool")

        reveal_file_tool = get_reveal_file_tool()
        self.tools.append(reveal_file_tool)
        logger.info("[FastAgentContext] Added reveal_file tool")

        reveal_project_tool = get_reveal_project_tool()
        self.tools.append(reveal_project_tool)
        logger.info("[FastAgentContext] Added reveal_project tool")

        transfer_file_tool = get_transfer_file_tool()
        self.tools.append(transfer_file_tool)
        logger.info("[FastAgentContext] Added transfer_file tool")

        transfer_path_tool = get_transfer_path_tool()
        self.tools.append(transfer_path_tool)
        logger.info("[FastAgentContext] Added transfer_path tool")

        # Memory 工具（统一接口，自动选择 Hindsight 或 memU 后端）
        if settings.ENABLE_MEMORY:
            try:
                from src.infra.memory.tools import get_all_memory_tools

                memory_tools = get_all_memory_tools()
                self.tools.extend(memory_tools)
                logger.info(f"[FastAgentContext] Added {len(memory_tools)} memory tools")
            except ImportError:
                logger.warning("[FastAgentContext] memory tools import failed, skipping")
            except Exception as e:
                logger.warning(f"[FastAgentContext] Failed to load memory tools: {e}")

        # MCP 工具延迟加载（不在 setup 时初始化）
        logger.info("[FastAgentContext] MCP tools will be lazy loaded on first use")

        # 沙箱 MCP 管理工具
        if settings.ENABLE_SANDBOX:
            from src.infra.tool.sandbox_mcp_tool import get_sandbox_mcp_tools

            self.tools.extend(get_sandbox_mcp_tools())
            logger.info("[FastAgentContext] Added sandbox_mcp tools (sandbox mode)")

        # 加载技能（使用与 Search Agent 相同的方式，保持一致）
        if settings.ENABLE_SKILLS and self.user_id:
            try:
                manager = SkillManager(user_id=self.user_id)
                skills_data = await manager.get_effective_skills()
                for skill_name, skill_data in skills_data.items():
                    skill_dict = (
                        skill_data.model_dump()
                        if hasattr(skill_data, "model_dump")
                        else (dict(skill_data) if not isinstance(skill_data, dict) else skill_data)
                    )
                    skill_dict["is_system"] = skill_dict.get("is_system", True)
                    if skill_dict.get("enabled", True):
                        self.skills.append(skill_dict)

                # Filter skills by disabled_skills blacklist if provided
                if self.disabled_skills:
                    disabled_set = set(self.disabled_skills)
                    self.skills = [s for s in self.skills if s.get("name") not in disabled_set]
                    logger.info(
                        f"[FastAgentContext] Filtered out {len(self.disabled_skills)} disabled skills, {len(self.skills)} remaining"
                    )

                logger.info(
                    f"[FastAgentContext] Loaded {len(self.skills)} skills for user: {self.user_id}"
                )
            except Exception as e:
                logger.warning(f"[FastAgentContext] Failed to load skills: {e}")

        logger.info(f"[FastAgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理（注意：不关闭 mcp_manager，因为它是全局缓存的）"""
        # mcp_manager 是全局缓存的，不应该在这里关闭
        # 它会在 mcp_global.py 的缓存过期/失效时自动清理
        self.mcp_manager = None

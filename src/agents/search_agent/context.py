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
from src.infra.tool.mcp_global import get_global_mcp_tools
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.infra.tool.transfer_file_tool import get_transfer_file_tool, get_transfer_path_tool
from src.kernel.config import settings

if TYPE_CHECKING:
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
        session_id: str = str(uuid.uuid4()),
        agent_id: str = "search",
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
        self.skill_files: Dict[str, Any] = {}
        self.deferred_manager: Optional["DeferredToolManager"] = None

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

            # 延迟加载决策：工具总数超过阈值时延迟 MCP 工具
            if (
                settings.ENABLE_DEFERRED_TOOL_LOADING
                and mcp_tools
                and (len(self.tools) + len(mcp_tools)) > settings.DEFERRED_TOOL_THRESHOLD
            ):
                from src.infra.tool.deferred_manager import (
                    DeferredToolManager,
                    restore_discovered_tools,
                )

                # 恢复上次已发现的工具名（跨 turn 持久化）
                pre_discovered = await restore_discovered_tools(self.session_id)

                self.deferred_manager = DeferredToolManager(
                    all_deferred_tools=mcp_tools,
                    session_id=self.session_id,
                    disabled_tools=self.disabled_tools,
                    disabled_mcp_tools=self.disabled_mcp_tools,
                    pre_discovered_names=pre_discovered,
                )
                logger.info(
                    f"[SearchAgentContext] Deferred {len(mcp_tools)} MCP tools "
                    f"(builtin={len(self.tools)}, threshold={settings.DEFERRED_TOOL_THRESHOLD}, "
                    f"pre_restored={len(pre_discovered)})"
                )
            else:
                # 低于阈值或未启用延迟：走原有逻辑
                self.tools.extend(mcp_tools)

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
        )
        logger.debug(
            "[SearchAgentContext] Tool filtering: %d/%d tools enabled",
            len(filtered),
            len(self.tools),
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

        # Memory 工具（统一接口，自动选择 Hindsight 或 memU 后端）
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
            from src.infra.tool.sandbox_mcp_tool import get_sandbox_mcp_tools
            from src.infra.tool.upload_url_tool import get_upload_url_tool

            self.tools.append(get_upload_url_tool())
            logger.info("[SearchAgentContext] Added upload_url_to_sandbox tool (sandbox mode)")

            self.tools.extend(get_sandbox_mcp_tools())
            logger.info("[SearchAgentContext] Added sandbox_mcp tools (sandbox mode)")

        # MCP 工具延迟加载（不在 setup 时初始化）
        logger.info("[SearchAgentContext] MCP tools will be lazy loaded on first use")

        # 加载技能
        if settings.ENABLE_SKILLS:
            try:
                skill_result = await load_skill_files(self.user_id)
                self.skill_files = skill_result["files"]
                self.skills = skill_result["skills"]

                # Filter skills by disabled_skills blacklist if provided
                if self.disabled_skills:
                    disabled_set = set(self.disabled_skills)
                    self.skills = [s for s in self.skills if s.get("name") not in disabled_set]
                    logger.info(
                        f"[SearchAgentContext] Filtered out {len(self.disabled_skills)} disabled skills, {len(self.skills)} remaining"
                    )

                logger.info(
                    f"[SearchAgentContext] Loaded {len(self.skills)} skills, "
                    f"{len(self.skill_files)} skill files"
                )
            except Exception as e:
                logger.warning(f"[SearchAgentContext] Failed to load skills: {e}")

        logger.info(f"[SearchAgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理

        注意：MCP 管理器是全局单例，不在这里关闭。
        如果需要清理全局缓存，使用 invalidate_global_cache()。
        """
        # MCP 管理器是全局单例，不在这里关闭
        # 如果需要清理，使用 src.infra.tool.mcp_global.invalidate_global_cache()
        pass

"""
Fast Agent 上下文管理 - 无沙箱，支持工具和 Skills

不使用沙箱，但保留工具和技能支持。
"""

import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from src.infra.logging import get_logger
from src.infra.skill.manager import SkillManager
from src.infra.tool.human_tool import get_human_tool
from src.infra.tool.mcp_global import get_global_mcp_tools
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.infra.tool.transfer_file_tool import get_transfer_file_tool
from src.kernel.config import settings

if TYPE_CHECKING:
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
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.disabled_tools = disabled_tools
        self.mcp_manager: Optional[MCPClientManager] = None
        self._mcp_loaded: bool = False
        self.tools: List[Any] = []
        self.skills: List[dict] = []

    async def get_tools(self) -> List[Any]:
        """获取所有工具（懒加载 MCP 工具）"""
        await self._lazy_load_mcp_tools()
        return self.tools

    def filter_tools(self) -> List[Any]:
        """根据 disabled_tools 过滤工具"""
        if not self.disabled_tools:
            return self.tools

        builtin_tools = frozenset(
            [
                "ask_human",
                "reveal_file",
                "reveal_project",
                "transfer_file",
                "sandbox_mcp_add",
                "sandbox_mcp_update",
                "sandbox_mcp_remove",
            ]
        )

        disabled_set = set(self.disabled_tools)
        mcp_servers = set()
        exact_names = set()

        for tool_name in disabled_set:
            if tool_name.startswith("mcp:"):
                mcp_servers.add(tool_name[4:])
            else:
                exact_names.add(tool_name)

        mcp_prefixes = tuple(f"{s}:" for s in mcp_servers) if mcp_servers else ()

        filtered = []
        for tool in self.tools:
            tool_name = getattr(tool, "name", str(tool))

            if tool_name in builtin_tools:
                filtered.append(tool)
                continue

            if tool_name in exact_names:
                continue

            if mcp_prefixes and tool_name.startswith(mcp_prefixes):
                continue
            if mcp_servers and hasattr(tool, "server") and tool.server in mcp_servers:
                continue

            filtered.append(tool)

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
            logger.info(
                f"[FastAgentContext] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}"
            )
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

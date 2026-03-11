"""
Fast Agent 上下文管理 - 无沙箱，支持工具和 Skills

不使用沙箱，但保留工具和技能支持。
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from src.infra.skill import load_skill_files
from src.infra.tool.add_skill_tool import get_add_skill_tool
from src.infra.tool.human_tool import get_human_tool
from src.infra.tool.mcp_client import MCPClientManager
from src.infra.tool.reveal_file_tool import get_reveal_file_tool
from src.infra.tool.reveal_project_tool import get_reveal_project_tool
from src.kernel.config import settings

logger = logging.getLogger(__name__)


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
        self.tools: List[Any] = []
        self.skills: List[dict] = []
        self.skill_files: Dict[str, Any] = {}

    def filter_tools(self) -> List[Any]:
        """根据 disabled_tools 过滤工具"""
        if not self.disabled_tools:
            return self.tools

        builtin_tools = frozenset(
            ["ask_human", "reveal_file", "reveal_project", "add_skill_from_path"]
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

        add_skill_tool = get_add_skill_tool()
        self.tools.append(add_skill_tool)
        logger.info("[FastAgentContext] Added add_skill_from_path tool")

        # MCP 工具
        if settings.ENABLE_MCP:
            try:
                logger.info(f"[FastAgentContext] Initializing MCP client for user {self.user_id}")
                self.mcp_manager = MCPClientManager(
                    config_path=None, user_id=self.user_id, use_database=True
                )
                await self.mcp_manager.initialize()
                mcp_tools = await self.mcp_manager.get_tools()
                logger.info(
                    f"[FastAgentContext] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}"
                )
                self.tools.extend(mcp_tools)
            except Exception as e:
                logger.error(f"[FastAgentContext] Failed to load MCP tools: {e}", exc_info=True)
        else:
            logger.warning("[FastAgentContext] MCP is disabled (ENABLE_MCP=False)")

        # 加载技能
        if settings.ENABLE_SKILLS:
            try:
                skill_result = await load_skill_files(self.user_id)
                self.skill_files = skill_result["files"]
                self.skills = skill_result["skills"]
                logger.info(
                    f"[FastAgentContext] Loaded {len(self.skills)} skills, "
                    f"{len(self.skill_files)} skill files"
                )
            except Exception as e:
                logger.warning(f"[FastAgentContext] Failed to load skills: {e}")

        logger.info(f"[FastAgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理"""
        if self.mcp_manager:
            try:
                await self.mcp_manager.close()
            except Exception:
                pass

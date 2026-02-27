"""
Search Agent 上下文管理
"""

import logging
import uuid
from typing import Any, List, Optional

from src.agents.search_agent.prompt import DEFAULT_SYSTEM_PROMPT

# Human-in-the-loop 工具
from src.infra.tool.human_tool import get_human_tool

# Inject Skill 工具 - 按需加载技能到沙箱
# 设置全局 middleware 供 inject_skill 工具使用
from src.infra.tool.inject_skill import get_inject_skill_tool
from src.infra.tool.mcp_client import MCPClientManager

# Reveal File 工具 - 向用户展示文件
from src.infra.tool.reveal_file_tool import get_reveal_file_tool

# Sync Conversation 工具 - 恢复 write_file 创建的文件到沙箱
from src.infra.tool.sync_conversation import get_sync_conversation_tool
from src.kernel.config import settings

logger = logging.getLogger(__name__)


class AgentContext:
    """Agent 上下文，管理工具和技能"""

    def __init__(
        self,
        session_id: str = str(uuid.uuid4()),
        agent_id: str = "search",
        user_id: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.disabled_tools = disabled_tools  # 用户禁用的工具列表
        self.skills_middleware = None
        self.mcp_manager: Optional[MCPClientManager] = None
        self.tools: List[Any] = []
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    def filter_tools(self) -> List[Any]:
        """
        根据 disabled_tools 过滤工具

        支持两种模式：
        1. 精确匹配: "read_file" 匹配名为 "read_file" 的工具
        2. MCP 模式匹配: "mcp:server_name" 匹配来自该服务器的所有工具

        注意：ask_human 和 reveal_file 是内置工具，始终可用，不受过滤影响。
        """
        # 如果 disabled_tools 为 None 或空列表，返回所有工具
        if not self.disabled_tools:
            return self.tools

        # 内置工具，始终可用
        builtin_tools = frozenset(["ask_human", "reveal_file", "inject_skill", "sync_conversation"])

        disabled_set = set(self.disabled_tools)
        mcp_servers = set()
        exact_names = set()

        for tool_name in disabled_set:
            if tool_name.startswith("mcp:"):
                mcp_servers.add(tool_name[4:])
            else:
                exact_names.add(tool_name)

        # 构建 MCP 前缀元组，用于 startswith 批量匹配（避免内层循环）
        mcp_prefixes = tuple(f"{s}:" for s in mcp_servers) if mcp_servers else ()

        filtered = []
        for tool in self.tools:
            tool_name = getattr(tool, "name", str(tool))

            if tool_name in builtin_tools:
                filtered.append(tool)
                continue

            if tool_name in exact_names:
                continue

            # MCP 服务器模式匹配（用 tuple startswith 一次性检查所有前缀）
            if mcp_prefixes and tool_name.startswith(mcp_prefixes):
                continue
            if mcp_servers and hasattr(tool, "server") and tool.server in mcp_servers:
                continue

            filtered.append(tool)

        logger.debug(
            "[AgentContext] Tool filtering: %d/%d tools enabled (disabled: %s)",
            len(filtered),
            len(self.tools),
            self.disabled_tools,
        )
        return filtered

    async def setup(self) -> None:
        """初始化：技能 + 工具"""
        logger.info(
            f"[AgentContext] Starting setup, ENABLE_SKILLS={settings.ENABLE_SKILLS}, ENABLE_MCP={settings.ENABLE_MCP}"
        )

        human_tool = get_human_tool(session_id=self.session_id)
        self.tools.append(human_tool)
        logger.info("[AgentContext] Added human tool")

        if settings.ENABLE_SANDBOX:
            reveal_file_tool = get_reveal_file_tool()
            self.tools.append(reveal_file_tool)
            logger.info("[AgentContext] Added reveal_file tool")

        if settings.ENABLE_SKILLS and settings.ENABLE_SANDBOX:
            inject_skill_tool = get_inject_skill_tool()
            self.tools.append(inject_skill_tool)
            logger.info("[AgentContext] Added inject_skill tool")

        if settings.ENABLE_SANDBOX:
            sync_conversation_tool = get_sync_conversation_tool()
            self.tools.append(sync_conversation_tool)
            logger.info("[AgentContext] Added sync_conversation tool")

        # MCP 工具
        if settings.ENABLE_MCP:
            try:
                logger.info(f"[AgentContext] Initializing MCP client for user {self.user_id}")
                self.mcp_manager = MCPClientManager(
                    config_path=None, user_id=self.user_id, use_database=True
                )
                await self.mcp_manager.initialize()
                mcp_tools = await self.mcp_manager.get_tools()
                logger.info(
                    f"[AgentContext] Loaded {len(mcp_tools)} MCP tools: {[t.name for t in mcp_tools]}"
                )
                self.tools.extend(mcp_tools)
            except Exception as e:
                logger.error(f"[AgentContext] Failed to load MCP tools: {e}", exc_info=True)
        else:
            logger.warning("[AgentContext] MCP is disabled (ENABLE_MCP=False)")

        logger.info(f"[AgentContext] Setup complete, total {len(self.tools)} tools available")

    async def close(self) -> None:
        """清理"""
        if self.mcp_manager:
            try:
                await self.mcp_manager.close()
            except Exception:
                pass

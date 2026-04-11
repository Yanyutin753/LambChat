"""
共享工具过滤工具

提取自 FastAgentContext 和 SearchAgentContext 的重复代码。
提供统一的工具过滤逻辑，包括：
- 内置工具保护（不可被禁用）
- 精确名称匹配
- MCP 服务器前缀匹配（mcp:server_name 格式）
- 数据库持久化的 system_disabled / user_disabled 过滤
"""

from typing import Any, List, Optional, Set

# 不可被用户禁用的内置工具
BUILTIN_TOOLS = frozenset(
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


def filter_disabled_tools(
    tools: List[Any],
    disabled_tools: Optional[List[str]] = None,
    disabled_mcp_tools: Optional[List[str]] = None,
) -> List[Any]:
    """
    根据禁用列表过滤工具

    Args:
        tools: 所有可用工具列表
        disabled_tools: 禁用的工具名列表
        disabled_mcp_tools: 禁用的 MCP 工具名列表

    Returns:
        过滤后的工具列表

    过滤策略：
    1. BUILTIN_TOOLS 中的工具永远不被过滤
    2. 精确名称匹配：如果工具名在 disabled 列表中，过滤掉
    3. MCP 服务器匹配：如果 disabled 列表中有 "mcp:server_name" 格式的条目，
       则该服务器下的所有工具都会被过滤掉
    4. MCP 工具的 server 属性匹配：如果工具有 server 属性且在禁用服务器列表中
    """
    if not disabled_tools and not disabled_mcp_tools:
        return tools

    # 合并所有禁用名称
    disabled_set = set(disabled_tools or [])
    disabled_set.update(disabled_mcp_tools or [])

    mcp_servers = set()
    exact_names = set()

    for name in disabled_set:
        if name.startswith("mcp:"):
            mcp_servers.add(name[4:])
        else:
            exact_names.add(name)

    mcp_prefixes = tuple(f"{s}:" for s in mcp_servers) if mcp_servers else ()

    filtered = []
    for tool in tools:
        tool_name = getattr(tool, "name", str(tool))

        # 内置工具永远不过滤
        if tool_name in BUILTIN_TOOLS:
            filtered.append(tool)
            continue

        # 精确名称匹配
        if tool_name in exact_names:
            continue

        # MCP 服务器前缀匹配
        if mcp_prefixes and tool_name.startswith(mcp_prefixes):
            continue

        # MCP server 属性匹配
        if mcp_servers and hasattr(tool, "server") and tool.server in mcp_servers:
            continue

        filtered.append(tool)

    return filtered


async def get_db_disabled_mcp_tool_names(user_id: str) -> Set[str]:
    """
    从数据库查询所有被禁用的 MCP 工具名（合并 system_disabled 和 user_disabled）。

    返回的是全限定名集合（格式: "server_name:tool_name"），
    可直接用于在运行时过滤掉不应传给 agent 的工具。
    如果查询失败，返回空集合（不阻塞 MCP 工具加载）。
    """
    from src.infra.logging import get_logger

    logger = get_logger(__name__)

    try:
        from src.infra.mcp.storage import MCPStorage

        storage = MCPStorage()

        # system 级别：管理员在 system server 上禁用的工具
        system_disabled = await storage.get_system_disabled_tools()
        # user 级别：用户在自己的 server 上禁用的工具
        user_server_disabled = await storage.get_user_server_disabled_tools(user_id)
        # user 级别：用户在 tool_preferences 中禁用的工具（全限定名）
        user_tool_disabled = await storage.get_disabled_tool_names(user_id)

        disabled: Set[str] = set()

        # system 级别的禁用工具 → 构造全限定名
        for server_name, tool_names in system_disabled.items():
            for tool_name in tool_names:
                disabled.add(f"{server_name}:{tool_name}")

        # user server 级别的禁用工具 → 构造全限定名
        for server_name, tool_names in user_server_disabled.items():
            for tool_name in tool_names:
                disabled.add(f"{server_name}:{tool_name}")

        # user tool preference 级别（已经是全限定名）
        disabled.update(user_tool_disabled)

        if disabled:
            logger.info(
                "[tool_filter] DB disabled MCP tools for user %s: %s",
                user_id,
                disabled,
            )

        return disabled

    except Exception as e:
        logger.warning(
            "[tool_filter] Failed to query DB disabled tools for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        return set()


def filter_mcp_tools_by_db_state(
    mcp_tools: List[Any],
    disabled_names: Set[str],
) -> List[Any]:
    """
    根据 get_db_disabled_mcp_tool_names() 返回的禁用集合过滤 MCP 工具列表。

    匹配规则：
    - 精确匹配全限定名（"server:tool" 格式）
    - 短名匹配兜底（如果工具名不含 server 前缀）
    """
    if not disabled_names:
        return mcp_tools

    # 预计算短名集合，用于无前缀工具的兜底匹配
    short_disabled: Set[str] = set()
    for dn in disabled_names:
        if ":" in dn:
            short_disabled.add(dn.split(":", 1)[1])
        else:
            short_disabled.add(dn)

    before_count = len(mcp_tools)
    filtered: List[Any] = []
    for tool in mcp_tools:
        tool_name = getattr(tool, "name", str(tool))

        # 精确匹配全限定名
        if tool_name in disabled_names:
            continue

        # 短名匹配（工具名不含 server 前缀时）
        if ":" not in tool_name and tool_name in short_disabled:
            continue

        filtered.append(tool)

    removed = before_count - len(filtered)
    if removed > 0:
        from src.infra.logging import get_logger

        get_logger(__name__).info(
            "[tool_filter] Filtered %d/%d MCP tools by DB state",
            removed,
            before_count,
        )

    return filtered

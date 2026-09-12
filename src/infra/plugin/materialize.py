"""插件 MCP server 物化：插件声明 → 平台 system_mcp_servers。

激活时把 inline 配置物化为带 source_plugin 标记的平台 server（继承
加密 / allowed_roles / 配额治理）；ref 引用只做存在性校验。
停用插件 → 物化 server 置 enabled=false（可逆）；删除插件 → 物化 server 一并删除。
"""

from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.mcp.storage import MCPStorage
from src.infra.plugin.storage import PluginStorage
from src.kernel.errors import AppError, ErrorCode

logger = get_logger(__name__)


def plugin_server_to_create(server: dict[str, Any]):
    """把插件 MCP 声明转换为 MCPServerCreate（plain headers，由存储层统一加密）。"""
    from src.kernel.schemas.mcp import MCPServerCreate, MCPTransport

    return MCPServerCreate(
        name=server.get("name", ""),
        transport=MCPTransport(server.get("transport", "streamable_http")),
        enabled=True,
        url=server.get("url"),
        headers=server.get("headers"),
    )


async def materialize_plugin_mcp(
    plugin_doc: dict[str, Any],
    *,
    admin_user_id: str,
    mcp_storage: Optional[MCPStorage] = None,
    plugin_storage: Optional[PluginStorage] = None,
) -> list[str]:
    """激活插件时物化/校验其 MCP server，返回物化的 server 名列表。"""
    storage = mcp_storage or MCPStorage()
    plugins = plugin_storage or PluginStorage()
    raw_servers = plugin_doc.get("mcp_servers", []) or []
    if not raw_servers:
        return []

    servers = plugins.decrypt_mcp_headers(raw_servers)
    materialized: list[str] = []
    for server in servers:
        name = server.get("name", "")
        if server.get("ref"):
            target = await storage.get_system_server(name)
            if target is None:
                raise AppError(ErrorCode.PLUGIN_MCP_REF_NOT_FOUND, args={"server": name})
            continue

        existing = await storage.get_system_server(name)
        if existing is not None:
            if existing.source_plugin == plugin_doc["name"]:
                # 本插件此前物化过：重新激活时恢复启用并同步配置
                await storage.update_system_server(
                    name,
                    _plugin_server_to_update(server),
                    admin_user_id,
                )
                materialized.append(name)
                continue
            raise AppError(ErrorCode.PLUGIN_MCP_NAME_CONFLICT, args={"server": name})

        await storage.create_system_server(
            plugin_server_to_create(server),
            admin_user_id,
            source_plugin=plugin_doc["name"],
        )
        materialized.append(name)

    if materialized:
        logger.info(
            "[Plugin] Materialized %d MCP server(s) for plugin %s",
            len(materialized),
            plugin_doc["name"],
        )
    return materialized


async def disable_plugin_mcp(
    plugin_name: str,
    *,
    mcp_storage: Optional[MCPStorage] = None,
) -> int:
    """停用插件：物化的 server 全部置 enabled=false（不删除，可逆）。"""
    storage = mcp_storage or MCPStorage()
    count = 0
    async for server in storage.iter_system_servers_by_plugin(plugin_name):
        await storage.update_system_server(
            server.name,
            _plugin_server_to_update(None),
            plugin_name,
        )
        count += 1
    if count:
        logger.info("[Plugin] Disabled %d materialized MCP server(s) of %s", count, plugin_name)
    return count


async def delete_plugin_mcp(
    plugin_name: str,
    *,
    mcp_storage: Optional[MCPStorage] = None,
) -> int:
    """删除插件：物化的 server 一并删除。"""
    storage = mcp_storage or MCPStorage()
    count = 0
    names = [server.name async for server in storage.iter_system_servers_by_plugin(plugin_name)]
    for name in names:
        if await storage.delete_system_server(name):
            count += 1
    if count:
        logger.info("[Plugin] Deleted %d materialized MCP server(s) of %s", count, plugin_name)
    return count


def _plugin_server_to_update(server: dict[str, Any] | None):
    """构造 update_system_server 的更新对象。server=None 时仅停用。"""
    from src.kernel.schemas.mcp import MCPServerUpdate, MCPTransport

    update = MCPServerUpdate(enabled=bool(server))
    if server is not None:
        update.transport = MCPTransport(server.get("transport", "streamable_http"))
        update.url = server.get("url")
        update.headers = server.get("headers")
    return update

"""插件中心（Plugin Hub）：技能 / MCP / 角色统一插件体系。"""

from src.infra.plugin.types import (
    PluginCreate,
    PluginInstallRecord,
    PluginInstallResponse,
    PluginListResponse,
    PluginMcpServerPayload,
    PluginPersonaPayload,
    PluginResponse,
    PluginSkillPayload,
    PluginStatus,
    PluginUpdate,
)


async def init_plugin_indexes() -> None:
    """启动初始化：建索引 + 旧技能商店幂等迁移。"""
    from src.infra.logging import get_logger
    from src.infra.plugin.migration import _run_migration_with_collections
    from src.infra.plugin.storage import PluginStorage

    logger = get_logger(__name__)
    storage = PluginStorage()
    await storage.ensure_indexes()
    migrated = await _run_migration_with_collections(storage._get_plugins_collection())
    logger.info("Plugin indexes initialized (migrated %d marketplace skill(s))", migrated)


__all__ = [
    "PluginCreate",
    "PluginInstallRecord",
    "PluginInstallResponse",
    "PluginListResponse",
    "PluginMcpServerPayload",
    "PluginPersonaPayload",
    "PluginResponse",
    "PluginSkillPayload",
    "PluginStatus",
    "PluginUpdate",
    "init_plugin_indexes",
]

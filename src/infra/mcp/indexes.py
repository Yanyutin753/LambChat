"""MCP collection index initialization.

Split from storage.py to keep that module under the repo's 1000-line cap.
The indexes match the unique constraints the MCP upsert paths rely on.
"""

from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)


async def ensure_mcp_indexes(storage: Any) -> None:
    """Create unique indexes across the five MCP collections.

    Wrapped in try/except so a failure (e.g. duplicate keys on dirty data) does
    not crash startup — run scripts/pre_deploy_db_checks.py dedup-check first.
    """
    index_specs = [
        (
            storage._get_system_collection(),
            [("name", 1)],
            "mcp_system_name_unique_idx",
        ),
        (
            storage._get_user_collection(),
            [("user_id", 1), ("name", 1)],
            "mcp_user_server_unique_idx",
        ),
        (
            storage._get_preferences_collection(),
            [("user_id", 1), ("server_name", 1)],
            "mcp_user_pref_unique_idx",
        ),
        (
            storage._get_tool_preferences_collection(),
            [("user_id", 1), ("tool_name", 1)],
            "mcp_tool_pref_unique_idx",
        ),
        (
            storage._get_tool_policies_collection(),
            [("server_name", 1), ("tool_name", 1)],
            "mcp_tool_policy_unique_idx",
        ),
    ]
    for collection, keys, name in index_specs:
        try:
            await collection.create_index(
                keys,
                name=name,
                unique=True,
                background=True,
            )
        except Exception as e:
            logger.error(f"Failed to create MCP storage index {name}: {e}")
    logger.info("MCP storage index initialization finished")

"""Tests for MCPStorage.ensure_indexes across the five MCP collections (P0-2).

Lazy init is bypassed by pre-setting the cached collection refs, so we assert
each collection receives its unique index without touching get_mongo_client.
"""

from __future__ import annotations

import pytest


class _FakeCollection:
    def __init__(self) -> None:
        self.created_indexes: list[tuple[object, dict[str, object]]] = []

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, dict(kwargs)))


@pytest.mark.asyncio
async def test_mcp_storage_ensures_unique_indexes_across_five_collections() -> None:
    system = _FakeCollection()
    user = _FakeCollection()
    preferences = _FakeCollection()
    tool_preferences = _FakeCollection()
    tool_policies = _FakeCollection()

    from src.infra.mcp.storage import MCPStorage

    storage = MCPStorage()
    # Bypass lazy init by pre-setting the cached collection refs.
    storage._system_collection = system
    storage._user_collection = user
    storage._preferences_collection = preferences
    storage._tool_preferences_collection = tool_preferences
    storage._tool_policies_collection = tool_policies

    await storage.ensure_indexes()

    assert system.created_indexes == [
        ([("name", 1)], {"name": "mcp_system_name_unique_idx", "unique": True, "background": True}),
    ]
    assert user.created_indexes == [
        ([("user_id", 1), ("name", 1)], {"name": "mcp_user_server_unique_idx", "unique": True, "background": True}),
    ]
    assert preferences.created_indexes == [
        ([("user_id", 1), ("server_name", 1)], {"name": "mcp_user_pref_unique_idx", "unique": True, "background": True}),
    ]
    assert tool_preferences.created_indexes == [
        ([("user_id", 1), ("tool_name", 1)], {"name": "mcp_tool_pref_unique_idx", "unique": True, "background": True}),
    ]
    assert tool_policies.created_indexes == [
        ([("server_name", 1), ("tool_name", 1)], {"name": "mcp_tool_policy_unique_idx", "unique": True, "background": True}),
    ]

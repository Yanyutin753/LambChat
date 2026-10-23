"""MCP server load-status persistence (issue #991).

last_load_status / consecutive_failures / last_load_at / last_load_error
记录每个 server 最近一次工具加载探测结果，供管理面板徽标与熔断回写使用。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.mcp.storage import MCPStorage


class _UpdateCollection:
    def __init__(self) -> None:
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> SimpleNamespace:
        self.updates.append((query, update))
        return SimpleNamespace(matched_count=1, modified_count=1)


@pytest.mark.asyncio
async def test_update_system_server_load_status_failure_increments(monkeypatch) -> None:
    collection = _UpdateCollection()
    storage = MCPStorage()
    monkeypatch.setattr(storage, "_get_system_collection", lambda: collection)

    written = await storage.update_system_server_load_status(
        "mcp_tool_12306", ok=False, error="OSError: connection refused"
    )

    assert written is True
    query, update = collection.updates[0]
    assert query == {"name": "mcp_tool_12306"}
    assert update["$set"]["last_load_status"] == "failed"
    assert update["$set"]["last_load_error"] == "OSError: connection refused"
    assert update["$set"]["last_load_at"]
    assert update["$inc"] == {"consecutive_failures": 1}


@pytest.mark.asyncio
async def test_update_system_server_load_status_success_resets(monkeypatch) -> None:
    collection = _UpdateCollection()
    storage = MCPStorage()
    monkeypatch.setattr(storage, "_get_system_collection", lambda: collection)

    written = await storage.update_system_server_load_status("srv", ok=True)

    assert written is True
    _, update = collection.updates[0]
    assert update["$set"]["last_load_status"] == "ok"
    assert update["$set"]["last_load_error"] is None
    assert update["$set"]["consecutive_failures"] == 0
    assert "$inc" not in update


@pytest.mark.asyncio
async def test_update_user_server_load_status_scopes_by_owner(monkeypatch) -> None:
    collection = _UpdateCollection()
    storage = MCPStorage()
    monkeypatch.setattr(storage, "_get_user_collection", lambda: collection)

    await storage.update_user_server_load_status("my-server", "user-1", ok=False, error="timeout")

    query, update = collection.updates[0]
    assert query == {"name": "my-server", "user_id": "user-1"}
    assert update["$inc"] == {"consecutive_failures": 1}


@pytest.mark.asyncio
async def test_update_load_status_truncates_long_error(monkeypatch) -> None:
    collection = _UpdateCollection()
    storage = MCPStorage()
    monkeypatch.setattr(storage, "_get_system_collection", lambda: collection)

    await storage.update_system_server_load_status("srv", ok=False, error="x" * 2000)

    _, update = collection.updates[0]
    assert len(update["$set"]["last_load_error"]) == 500


def test_doc_to_response_passes_load_status_fields() -> None:
    storage = MCPStorage()
    doc = {
        "name": "srv",
        "transport": "streamable_http",
        "enabled": True,
        "last_load_status": "failed",
        "consecutive_failures": 7,
        "last_load_at": "2026-10-22T01:00:00+00:00",
        "last_load_error": "boom",
    }

    response = storage._doc_to_response(doc, is_system=True, can_edit=False)

    assert response.last_load_status == "failed"
    assert response.consecutive_failures == 7
    assert response.last_load_at == "2026-10-22T01:00:00+00:00"
    assert response.last_load_error == "boom"


def test_doc_to_response_defaults_missing_load_status() -> None:
    storage = MCPStorage()
    doc = {"name": "srv", "transport": "streamable_http", "enabled": True}

    response = storage._doc_to_response(doc, is_system=False, can_edit=True)

    assert response.last_load_status is None
    assert response.consecutive_failures == 0
    assert response.last_load_at is None
    assert response.last_load_error is None

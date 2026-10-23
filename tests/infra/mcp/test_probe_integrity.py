import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.mcp.storage import MCPStorage
from src.infra.tool import mcp_client
from src.infra.tool import mcp_server_breaker as breaker
from src.infra.tool.mcp_load_status import _format_load_error
from src.kernel.schemas.mcp import MCPTransport


async def test_failed_tool_list_probe_is_not_reported_as_healthy(monkeypatch):
    manager = SimpleNamespace(
        _tools=[],
        unavailable_server_names=("broken",),
        server_load_errors={"broken": "TimeoutError: tool list load timed out"},
        _initialize_with_config=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(mcp_client, "MCPClientManager", lambda **kwargs: manager)
    storage = MCPStorage()
    monkeypatch.setattr(
        storage,
        "get_user_server",
        AsyncMock(
            return_value=SimpleNamespace(
                transport=MCPTransport.STREAMABLE_HTTP, url="https://provider/mcp", headers=None
            )
        ),
    )
    ok, _, count, error, scope = await storage.probe_server_connection("broken", "owner")
    assert ok is False and count == 0 and error
    assert error == "TimeoutError: tool list load timed out"
    assert scope == "user"
    manager.close.assert_awaited_once()


async def test_admin_system_probe_ignores_same_named_user_override(monkeypatch):
    manager = SimpleNamespace(
        _tools=[],
        unavailable_server_names=(),
        _initialize_with_config=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(mcp_client, "MCPClientManager", lambda **kwargs: manager)
    storage = MCPStorage()
    monkeypatch.setattr(storage, "get_user_server", AsyncMock())
    monkeypatch.setattr(
        storage,
        "get_system_server",
        AsyncMock(
            return_value=SimpleNamespace(
                transport=MCPTransport.STREAMABLE_HTTP,
                url="https://system/mcp",
                headers=None,
                allowed_roles=[],
                is_system=True,
            )
        ),
    )
    result = await storage.probe_server_connection(
        "same-name", "owner", is_admin=True, system_only=True
    )
    assert result[-1] == "system"
    storage.get_user_server.assert_not_awaited()


def test_load_errors_redact_url_credentials_and_query_secrets():
    error = ValueError("bad upstream https://user:PASS@example.test/mcp?token=TOKEN#SECRET")
    formatted = _format_load_error(error)
    assert "example.test" in formatted
    assert all(secret not in formatted for secret in ("PASS", "TOKEN", "SECRET"))


async def test_cancelled_half_open_load_releases_the_probe_slot(monkeypatch):
    breaker.reset()
    monkeypatch.setattr(breaker.settings, "MCP_BREAKER_FAILURE_THRESHOLD", 1)
    monkeypatch.setattr(breaker.settings, "MCP_BREAKER_COOLDOWN_SECONDS", 1)
    clock = [10.0]
    monkeypatch.setattr(breaker.time, "monotonic", lambda: clock[0])
    breaker.record_failure("sys:cancelled")
    clock[0] = 12.0
    started = asyncio.Event()

    async def load(**kwargs):
        started.set()
        await asyncio.Event().wait()

    adapter = ModuleType("langchain_mcp_adapters.tools")
    adapter.load_mcp_tools = load
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", adapter)
    task = asyncio.create_task(
        mcp_client.MCPClientManager()._create_mcp_client(
            {
                "mcpServers": {
                    "cancelled": {"transport": "streamable_http", "url": "https://provider/mcp"}
                },
                "mcp_system_server_names": ["cancelled"],
            }
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert breaker.acquire_load_slot("sys:cancelled") is None
    finally:
        task.cancel()
        breaker.reset()

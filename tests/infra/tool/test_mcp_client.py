from __future__ import annotations

import asyncio
import builtins
import sys
import types
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_mcp_client_limits_concurrent_server_tool_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import mcp_client

    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return []

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 2, raising=False)

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            f"server-{index}": {
                "transport": "streamable_http",
                "url": f"https://example.test/{index}",
            }
            for index in range(5)
        }
    }

    task = asyncio.create_task(client._create_mcp_client(config))
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    tools, created_client = await task

    assert tools == []
    assert created_client is not None


@pytest.mark.asyncio
async def test_mcp_client_caps_direct_config_server_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import mcp_client

    loaded_servers: list[str] = []
    created_configs: list[dict[str, Any]] = []

    class _FakeMultiServerMCPClient:
        def __init__(self, configs: dict[str, Any]) -> None:
            created_configs.append(configs)

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        loaded_servers.append(kwargs["server_name"])
        return []

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", _FakeMultiServerMCPClient)
    monkeypatch.setattr(mcp_client.settings, "MCP_EFFECTIVE_CONFIG_MAX_SERVERS", 2, raising=False)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 10, raising=False)

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            f"server-{index}": {
                "transport": "streamable_http",
                "url": f"https://example.test/{index}",
            }
            for index in range(5)
        }
    }

    tools, created_client = await client._create_mcp_client(config)

    assert tools == []
    assert created_client is not None
    assert list(created_configs[0]) == ["server-0", "server-1"]
    assert loaded_servers == ["server-0", "server-1"]


@pytest.mark.asyncio
async def test_mcp_client_records_leaf_error_when_server_tool_loading_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import mcp_client

    class _FakeMultiServerMCPClient:
        def __init__(self, configs: dict[str, Any]) -> None:
            self.configs = configs

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionError("no route")])

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", _FakeMultiServerMCPClient)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)

    client = mcp_client.MCPClientManager()
    tools, created_client = await client._create_mcp_client(
        {
            "mcpServers": {
                "server-a": {
                    "transport": "streamable_http",
                    "url": "https://example.test/a",
                }
            }
        }
    )

    assert tools == []
    assert created_client is not None
    assert client.configured_server_count == 1
    assert client.all_configured_servers_failed() is True
    assert client.failed_servers == {"server-a": "[ConnectionError] no route"}


@pytest.mark.asyncio
async def test_mcp_client_caps_total_loaded_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import mcp_client

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeMultiServerMCPClient:
        def __init__(self, configs: dict[str, Any]) -> None:
            self.configs = configs

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        server_name = kwargs["server_name"]
        return [_FakeTool(f"{server_name}:tool-{index}") for index in range(3)]

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", _FakeMultiServerMCPClient)
    monkeypatch.setattr(
        mcp_client,
        "settings",
        types.SimpleNamespace(
            MCP_EFFECTIVE_CONFIG_MAX_SERVERS=10,
            MCP_EFFECTIVE_CONFIG_MAX_TOOLS=3,
            MCP_SERVER_LOAD_CONCURRENCY=1,
        ),
    )

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            "server-a": {
                "transport": "streamable_http",
                "url": "https://example.test/a",
            },
            "server-b": {
                "transport": "streamable_http",
                "url": "https://example.test/b",
            },
        }
    }

    tools, created_client = await client._create_mcp_client(config)

    assert created_client is not None
    assert [tool.name for tool in tools] == [
        "server-a:tool-0",
        "server-a:tool-1",
        "server-a:tool-2",
    ]
    assert ("server-b", "tool-0") not in client._tool_server_map
    assert "server-b:tool-0" not in client._tool_name_server_map


def test_mcp_client_rejects_oversized_file_config_before_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from src.infra.tool import mcp_client

    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        '{"mcpServers":{"demo":{"url":"https://example.test"}}}', encoding="utf-8"
    )

    monkeypatch.setattr(mcp_client, "MCP_CONFIG_FILE_MAX_BYTES", 8, raising=False)
    original_open = builtins.open

    def guarded_open(path, *args, **kwargs):
        if path == str(config_path):
            raise AssertionError("oversized mcp.json should be rejected before open")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    client = mcp_client.MCPClientManager(
        config_path=str(config_path),
        use_database=False,
    )

    assert client._load_config_from_file_sync() is None

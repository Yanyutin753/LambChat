from __future__ import annotations

import asyncio
import builtins
import sys
import time
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


from langchain_core.tools import BaseTool


class _StubTool(BaseTool):
    name: str = "stub"
    description: str = "stub"

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


def test_mcp_is_retryable_error_recognizes_streamable_http() -> None:
    """Streamable HTTP / stream-disconnected errors must be retried (issue #198).

    Previously retryable_patterns omitted these, so SSE reconnect POST failures
    returned immediately with zero retries.
    """
    from src.infra.tool.mcp_client import MCPToolWithRetry

    wrapper = MCPToolWithRetry(original_tool=_StubTool())
    assert wrapper._is_retryable_error(
        Exception("Streamable HTTP error: Error POSTing to endpoint: (POST /mcp)")
    )
    assert wrapper._is_retryable_error(Exception("GET stream disconnected, reconnecting"))


def test_normalize_json_array_args_unwraps_array_string() -> None:
    """A JSON-array string arg is coerced back to a list (issue #198).

    tavily_extract received urls as a JSON array literal string and the remote
    server rejected it as an invalid URL format.
    """
    from src.infra.tool.mcp_client import _normalize_json_array_args

    out = _normalize_json_array_args(
        {
            "urls": '["https://a.com", "https://b.com"]',
            "query": "plain string",
            "depth": 2,
        },
        {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
                "depth": {"type": "integer"},
            },
        },
    )
    assert out["urls"] == ["https://a.com", "https://b.com"]
    assert out["query"] == "plain string"
    assert out["depth"] == 2


@pytest.mark.asyncio
async def test_mcp_arun_retries_streamable_http_and_normalizes_args() -> None:
    """_arun retries streamable-http errors and passes normalized kwargs (issue #198)."""
    from src.infra.tool.mcp_client import MCPToolWithRetry

    received: list[dict] = []

    class _RecordingTool(BaseTool):
        name: str = "tavily_extract"
        description: str = "extract"
        args_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "urls": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ]
                }
            },
        }

        def _run(self, *a, **k):
            raise NotImplementedError

        async def _arun(self, *args, config=None, **kwargs):
            received.append(kwargs)
            raise Exception("Streamable HTTP error: Error POSTing to endpoint")

    wrapper = MCPToolWithRetry(original_tool=_RecordingTool(), max_retries=2, retry_delay=0)
    result = await wrapper._arun(urls='["https://x.com"]')

    assert len(received) == 2  # retried once after the first failure
    assert received[0]["urls"] == ["https://x.com"]
    assert "Streamable HTTP error" in result


@pytest.mark.asyncio
async def test_mcp_arun_propagates_graph_interrupt() -> None:
    """LangGraph control-flow interrupts must not become MCP tool errors."""
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Interrupt

    from src.infra.tool.mcp_client import MCPToolWithRetry

    graph_interrupt = GraphInterrupt((Interrupt(value={"kind": "ask_human"}),))

    class _InterruptTool(BaseTool):
        name: str = "ask_human"
        description: str = "pause for human input"

        def _run(self, *args, **kwargs):
            raise NotImplementedError

        async def _arun(self, *args, config=None, **kwargs):
            raise graph_interrupt

    wrapper = MCPToolWithRetry(original_tool=_InterruptTool())

    with pytest.raises(GraphInterrupt) as captured:
        await wrapper._arun()
    assert captured.value is graph_interrupt


@pytest.mark.asyncio
async def test_mcp_arun_preserves_json_array_text_for_string_arguments() -> None:
    """JSON-looking text is still valid input for a schema-declared string."""
    from src.infra.tool.mcp_client import MCPToolWithRetry

    received: list[dict] = []

    class _StringTool(BaseTool):
        name: str = "string_payload"
        description: str = "accepts literal JSON text"
        args_schema: dict[str, Any] = {
            "type": "object",
            "properties": {"payload": {"type": "string"}},
        }

        def _run(self, *a, **k):
            raise NotImplementedError

        async def _arun(self, *args, config=None, **kwargs):
            received.append(kwargs)
            return "ok"

    wrapper = MCPToolWithRetry(original_tool=_StringTool())
    result = await wrapper._arun(payload='["literal", "json"]')

    assert result == "ok"
    assert received == [{"payload": '["literal", "json"]'}]


def test_mcp_tool_timeout_defaults_to_900() -> None:
    """单次工具调用超时默认 900s 且可经 settings 覆盖（原硬编码 300）。

    生产事故 2026-10-08：image_analyze 的 vision 调用持续生成 5 分钟以上，
    300s 硬超时把外层三次重试全部掐断（3×300s=15 分钟全部作废），上游还在
    正常输出。默认放宽到 900s 并允许 MCP_TOOL_TIMEOUT 覆盖。
    """
    from src.infra.tool import mcp_client
    from src.kernel.config import settings

    assert settings.MCP_TOOL_TIMEOUT == 900
    assert mcp_client._mcp_tool_timeout() == 900.0


@pytest.mark.asyncio
async def test_mcp_arun_enforces_configured_tool_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """settings.MCP_TOOL_TIMEOUT 生效于 _arun 的 wait_for：超时即返回错误信息。"""
    from src.infra.tool import mcp_client
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "MCP_TOOL_TIMEOUT", 1, raising=False)

    class _HangingTool(BaseTool):
        name: str = "hang"
        description: str = "hangs forever"

        def _run(self, *a, **k):
            raise NotImplementedError

        async def _arun(self, *args, config=None, **kwargs):
            await asyncio.sleep(30)
            return "never"

    wrapper = mcp_client.MCPToolWithRetry(
        original_tool=_HangingTool(), max_retries=1, retry_delay=0
    )
    result = await wrapper._arun()

    assert "timed out after 1 attempts" in result


def test_mcp_server_load_timeout_defaults_to_30() -> None:
    """单 server 工具加载超时默认 30s 且可经 settings 覆盖。

    mcp SDK 的 ClientSession read_timeout_seconds 默认 None（无请求级超时），
    挂死型上游（TCP 通但不响应）会永久挂起 initialize/list_tools（issue #991 /
    python-sdk #2432），加载路径必须有外层预算。
    """
    from src.infra.tool import mcp_client
    from src.kernel.config import settings

    assert settings.MCP_SERVER_LOAD_TIMEOUT == 30
    assert mcp_client._mcp_server_load_timeout() == 30.0


@pytest.mark.asyncio
async def test_mcp_client_load_timeout_marks_hung_server_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """挂死 server 被超时标记失败，同批其它 server 照常加载（隔离不回归）。"""
    from src.infra.tool import mcp_client

    loaded: list[str] = []

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        name = kwargs["server_name"]
        loaded.append(name)
        if name == "hung-server":
            await asyncio.Event().wait()  # 永不返回，模拟挂死上游
        return []

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_TIMEOUT", 0.2, raising=False)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            "hung-server": {
                "transport": "streamable_http",
                "url": "https://example.test/hung",
            },
            "healthy-server": {
                "transport": "streamable_http",
                "url": "https://example.test/ok",
            },
        }
    }

    tools, _ = await asyncio.wait_for(client._create_mcp_client(config), timeout=5)

    assert tools == []
    assert client.unavailable_server_names == ("hung-server",)
    assert sorted(loaded) == ["healthy-server", "hung-server"]


def test_format_load_error_expands_exception_group() -> None:
    """TaskGroup 的 ExceptionGroup 必须递归展开子异常（issue #991）。"""
    from src.infra.tool.mcp_client import _format_load_error

    inner = ExceptionGroup(
        "taskgroup", [OSError("connection refused"), TimeoutError("read timed out")]
    )
    outer = ExceptionGroup("outer", [inner])

    text = _format_load_error(outer)

    assert "OSError: connection refused" in text
    assert "TimeoutError: read timed out" in text
    assert _format_load_error(ValueError("plain")) == "ValueError: plain"


@pytest.mark.asyncio
async def test_mcp_client_failure_log_expands_error_and_hides_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失败日志展开子异常并带上 url；headers 等敏感配置不得进日志。"""
    from src.infra.tool import mcp_client

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        raise ExceptionGroup("taskgroup", [ValueError("boom-detail")])

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)

    warnings: list[str] = []

    def fake_warning(msg: Any, *args: Any, **kwargs: Any) -> None:
        warnings.append(msg % args if args else str(msg))

    monkeypatch.setattr(mcp_client.logger, "warning", fake_warning)

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            "secret-server": {
                "transport": "streamable_http",
                "url": "https://example.test/secret",
                "headers": {"Authorization": "secret-token-value"},
            }
        }
    }

    await client._create_mcp_client(config)

    joined = "\n".join(warnings)
    assert "ValueError: boom-detail" in joined
    assert "https://example.test" in joined
    assert "secret-token-value" not in joined


@pytest.mark.asyncio
async def test_mcp_client_skips_open_breaker_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """熔断打开的 server 不再连接，直接进 unavailable（issue #991）。"""
    from src.infra.tool import mcp_client
    from src.infra.tool import mcp_server_breaker as breaker

    breaker.reset()
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)
    for _ in range(3):
        breaker.record_failure("sys:dead-server", "e")

    loaded: list[str] = []

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        loaded.append(kwargs["server_name"])
        return []

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)

    try:
        client = mcp_client.MCPClientManager()
        config = {
            "mcpServers": {
                "dead-server": {
                    "transport": "streamable_http",
                    "url": "https://example.test/dead",
                },
                "healthy": {
                    "transport": "streamable_http",
                    "url": "https://example.test/ok",
                },
            },
            "mcp_system_server_names": ["dead-server"],
        }

        await client._create_mcp_client(config)

        assert loaded == ["healthy"]
        assert client.unavailable_server_names == ("dead-server",)
    finally:
        breaker.reset()


@pytest.mark.asyncio
async def test_mcp_client_breaker_recovers_on_successful_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冷却到期的半开探测 = 正常加载本身；成功即闭合。"""
    from src.infra.tool import mcp_client
    from src.infra.tool import mcp_server_breaker as breaker

    breaker.reset()
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)
    monkeypatch.setattr(breaker, "_cooldown_seconds", lambda: 0.05)
    for _ in range(3):
        breaker.record_failure("sys:flaky", "e")
    time.sleep(0.06)

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)

    try:
        client = mcp_client.MCPClientManager()
        config = {
            "mcpServers": {
                "flaky": {
                    "transport": "streamable_http",
                    "url": "https://example.test/flaky",
                },
            },
            "mcp_system_server_names": ["flaky"],
        }

        await client._create_mcp_client(config)

        assert client.unavailable_server_names == ()
        assert breaker.acquire_load_slot("sys:flaky") is None  # closed
    finally:
        breaker.reset()


@pytest.mark.asyncio
async def test_mcp_client_persists_status_on_breaker_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """达到阈值的跳闸迁移触发一次 fire-and-forget 状态落库。"""
    from src.infra.tool import mcp_client
    from src.infra.tool import mcp_server_breaker as breaker

    breaker.reset()
    monkeypatch.setattr(mcp_client.settings, "MCP_SERVER_LOAD_CONCURRENCY", 1, raising=False)

    async def fake_load_mcp_tools(*args: Any, **kwargs: Any) -> list[Any]:
        raise OSError("connection refused")

    fake_tools_module = types.ModuleType("langchain_mcp_adapters.tools")
    fake_tools_module.load_mcp_tools = fake_load_mcp_tools
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", fake_tools_module)

    writes: list[dict] = []

    class _FakeStorage:
        async def update_system_server_load_status(self, name, *, ok, error=None):
            writes.append({"name": name, "ok": ok, "error": error})

    import src.infra.mcp.storage as mcp_storage_module

    monkeypatch.setattr(mcp_storage_module, "MCPStorage", _FakeStorage)

    client = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {
            "doomed": {
                "transport": "streamable_http",
                "url": "https://example.test/doomed",
            },
        },
        "mcp_system_server_names": ["doomed"],
    }

    try:
        await client._create_mcp_client(config)
        await client._create_mcp_client(config)
        await client._create_mcp_client(config)
        await asyncio.sleep(0.05)  # 让 fire-and-forget 写任务落地

        assert len(writes) == 3  # 每次实际失败都计数，熔断跳过不计数
        assert writes[0]["name"] == "doomed"
        assert writes[0]["ok"] is False
        assert "connection refused" in writes[0]["error"]
    finally:
        breaker.reset()

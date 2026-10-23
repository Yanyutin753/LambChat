"""MCP requests must validate and pin every destination, including redirects."""

import socket

import httpx
import pytest


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "[::1]", "[::ffff:127.0.0.1]", "169.254.169.254", "172.17.0.1", "198.18.0.1"],
)
async def test_private_mcp_destinations_never_reach_transport(monkeypatch, host):
    from src.infra.mcp.network import public_mcp_http_client

    async def forbidden(*_):
        pytest.fail("private connection reached HTTP transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    async with public_mcp_http_client() as client:
        with pytest.raises(ValueError, match="public"):
            await client.get(f"http://{host}/mcp")


async def test_dns_is_pinned_and_host_header_cannot_select_an_internal_vhost(monkeypatch):
    import asyncio

    from src.infra.mcp.network import public_mcp_http_client

    destinations = []

    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    async def respond(self, request):
        destinations.append(request)
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", respond)
    async with public_mcp_http_client(headers={"Host": "internal-admin"}) as client:
        await client.get("https://mcp.example/tools")
    assert destinations[0].url.host == "8.8.8.8"
    assert destinations[0].headers["host"] == "mcp.example"
    assert destinations[0].extensions["sni_hostname"] == "mcp.example"


async def test_redirect_to_private_address_is_blocked(monkeypatch):
    from src.infra.mcp.network import public_mcp_http_client

    calls = []

    async def redirect(self, request):
        calls.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", redirect)
    async with public_mcp_http_client() as client:
        with pytest.raises(ValueError, match="public"):
            await client.get("https://8.8.8.8/mcp", follow_redirects=True)
    assert calls == ["8.8.8.8"]


@pytest.mark.parametrize("host", ["8.8.8.8", "[::ffff:8.8.8.8]"])
async def test_own_public_interface_is_not_a_remote_mcp_server(monkeypatch, host):
    from types import SimpleNamespace

    from src.infra.mcp import network

    async def forbidden(*_):
        pytest.fail("self connection reached HTTP transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(
        network.psutil,
        "net_if_addrs",
        lambda: {"eth0": [SimpleNamespace(family=socket.AF_INET, address="8.8.8.8")]},
    )
    async with network.public_mcp_http_client() as client:
        with pytest.raises(ValueError, match="public"):
            await client.get(f"http://{host}:27017/")


@pytest.mark.parametrize("transport", ["sse", "streamable_http"])
@pytest.mark.parametrize("trusted", [False, True])
async def test_every_user_mcp_connection_receives_the_guard(monkeypatch, transport, trusted):
    import sys
    from types import ModuleType

    from src.infra.mcp.network import public_mcp_http_client
    from src.infra.tool.mcp_client import MCPClientManager

    connections = []

    async def load(**kwargs):
        connections.append(kwargs["connection"])
        return []

    adapter = ModuleType("langchain_mcp_adapters.tools")
    adapter.load_mcp_tools = load
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", adapter)
    manager = MCPClientManager(use_database=False)
    try:
        await manager._initialize_with_config(
            {
                "mcpServers": {
                    "server": {
                        "transport": transport,
                        "url": "http://127.0.0.1/mcp",
                        "_trusted_network": trusted,
                    }
                }
            }
        )
        factory = connections[0].get("httpx_client_factory")
        assert factory is (None if trusted else public_mcp_http_client)
    finally:
        await manager.close()

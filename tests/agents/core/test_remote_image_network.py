"""Remote model images obey the same DNS and redirect boundary as user MCP."""

import asyncio
import socket
from types import SimpleNamespace

import httpx
import pytest

from src.agents.core import node_utils
from src.infra.mcp import network


@pytest.fixture(autouse=True)
def _isolate_image_bytes_and_local_interfaces(monkeypatch):
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {})
    monkeypatch.setattr(
        node_utils, "compress_image_bytes_if_needed", lambda data, mime: (data, mime)
    )


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "172.17.0.1"])
async def test_remote_image_dns_cannot_reach_private_addresses(monkeypatch, address):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    async def forbidden(self, request):
        pytest.fail("remote image reached a forbidden network destination")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    with pytest.raises(ValueError, match="public"):
        await node_utils._download_image_url_as_data_url(
            "https://images.example/photo.png", "image/png"
        )


async def test_remote_image_redirect_to_loopback_is_blocked_before_connect(monkeypatch):
    calls = []

    async def redirect(self, request):
        calls.append(request.url.host)
        if request.url.host != "8.8.8.8":
            pytest.fail("remote image followed an internal redirect")
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private.png"})

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", redirect)
    with pytest.raises(ValueError, match="public"):
        await node_utils._download_image_url_as_data_url("https://8.8.8.8/photo.png", "image/png")
    assert calls == ["8.8.8.8"]


async def test_remote_image_fetch_pins_public_dns_and_preserves_tls_identity(monkeypatch):
    calls = []

    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    async def image(self, request):
        calls.append(request)
        return httpx.Response(200, content=b"image-bytes", headers={"Content-Type": "image/png"})

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", image)
    result = await node_utils._download_image_url_as_data_url(
        "https://images.example/photo.png", "image/png"
    )
    assert result == "data:image/png;base64,aW1hZ2UtYnl0ZXM="
    assert len(calls) == 1
    assert calls[0].url.host == "8.8.8.8"
    assert calls[0].headers["host"] == "images.example"
    assert calls[0].extensions["sni_hostname"] == "images.example"


@pytest.mark.parametrize("host", ["8.8.8.8", "[::ffff:8.8.8.8]"])
async def test_remote_images_cannot_scan_the_servers_public_interface(monkeypatch, host):
    monkeypatch.setattr(
        network.psutil,
        "net_if_addrs",
        lambda: {"eth0": [SimpleNamespace(family=socket.AF_INET, address="8.8.8.8")]},
    )

    async def forbidden(self, request):
        pytest.fail("remote image reached the server's own public address")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    with pytest.raises(ValueError, match="public"):
        await node_utils._download_image_url_as_data_url(
            f"http://{host}:8013/private.png", "image/png"
        )

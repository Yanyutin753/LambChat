"""Public-only HTTP transport for user-configured MCP servers."""

import asyncio
import ipaddress
import socket

import httpx
import psutil


def _normalize_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value.split("%")[0])
    return getattr(address, "ipv4_mapped", None) or address


class PublicMCPTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme not in ("http", "https") or not url.host or url.userinfo:
            raise ValueError("MCP requires a public HTTP(S) destination")
        try:
            addresses = [_normalize_address(url.host)]
        except ValueError:
            resolved = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    url.host,
                    url.port or (443 if url.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                ),
                timeout=5,
            )
            addresses = [_normalize_address(str(item[4][0])) for item in resolved]
        local_addresses = {
            _normalize_address(address.address)
            for interfaces in psutil.net_if_addrs().values()
            for address in interfaces
            if address.family in (socket.AF_INET, socket.AF_INET6)
        }
        if not addresses or any(
            not ip.is_global or ip.is_multicast or ip in local_addresses for ip in addresses
        ):
            raise ValueError("MCP requires a public HTTP(S) destination")
        # Pin DNS for the actual connection; preserve TLS identity and ignore supplied Host.
        headers = request.headers.copy()
        headers["host"] = url.netloc.decode("ascii")
        pinned = httpx.Request(
            request.method,
            url.copy_with(host=str(addresses[0])),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": url.host},
        )
        return await super().handle_async_request(pinned)


def public_mcp_http_client(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout or httpx.Timeout(30, read=300),
        auth=auth,
        trust_env=False,
        follow_redirects=True,
        # A pinned IP must not reuse a TLS connection opened for another hostname.
        transport=PublicMCPTransport(limits=httpx.Limits(max_keepalive_connections=0)),
    )

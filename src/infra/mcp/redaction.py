"""Credential-safe MCP views and preservation of unchanged edit placeholders."""

from urllib.parse import urlsplit

from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.mcp import MCPServerUpdate

MASKED_SECRET = "***"


def redact_mcp_url(url: str | None) -> str | None:
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return MASKED_SECRET
        return parts._replace(
            netloc=parts.netloc.rsplit("@", 1)[-1], path="/***", query="", fragment=""
        ).geturl()
    except ValueError:
        return MASKED_SECRET


def preserve_mcp_secrets(data: MCPServerUpdate, server) -> MCPServerUpdate:
    updates = {}
    if data.url is not None:
        if data.url == redact_mcp_url(server.url):
            updates["url"] = server.url
        elif MASKED_SECRET in data.url:
            raise AppError(ErrorCode.BAD_REQUEST)
    if data.headers is not None:
        saved = {key.lower(): value for key, value in (server.headers or {}).items()}
        headers = {}
        for key, value in data.headers.items():
            if value == MASKED_SECRET:
                if key.lower() not in saved:
                    raise AppError(ErrorCode.BAD_REQUEST)
                value = saved[key.lower()]
            headers[key] = value
        updates["headers"] = headers
    return data.model_copy(update=updates)

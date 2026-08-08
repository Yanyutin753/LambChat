"""Conservative Tavily usage monitoring helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr

from src.kernel.config import settings


@dataclass(frozen=True)
class TavilyUsageContext:
    """Trusted provider context without a plaintext identifier."""

    server_name: str
    api_key: SecretStr
    credential_fingerprint: str
    project_id: str = ""


def get_tavily_poll_seconds() -> int:
    """Return a polling interval that cannot exceed Tavily's request budget."""
    configured = getattr(settings, "TAVILY_USAGE_POLL_SECONDS", 600)
    try:
        return max(600, int(configured or 600))
    except (TypeError, ValueError):
        return 600


def _is_tavily_host(hostname: str | None) -> bool:
    host = (hostname or "").rstrip(".").lower()
    return host == "tavily.com" or host.endswith(".tavily.com")


def _valid_api_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip()
    return key if key.startswith("tvly-") and len(key) > len("tvly-") else None


def resolve_tavily_context(
    server_name: str,
    server_config: dict[str, Any],
) -> TavilyUsageContext | None:
    """Resolve a key only from explicit settings or a trusted Tavily HTTPS URL."""
    parsed = urlparse(str(server_config.get("url") or ""))
    trusted_url = parsed.scheme.lower() == "https" and _is_tavily_host(parsed.hostname)
    named_tavily = "tavily" in server_name.lower()
    if not trusted_url and not named_tavily:
        return None

    key = _valid_api_key(getattr(settings, "TAVILY_USAGE_API_KEY", ""))
    if key is None and trusted_url:
        query_values = parse_qs(parsed.query, keep_blank_values=True).get("tavilyApiKey", [])
        key = _valid_api_key(query_values[0]) if len(query_values) == 1 else None

    if key is None and trusted_url:
        headers = server_config.get("headers")
        authorization = headers.get("Authorization") if isinstance(headers, dict) else None
        if isinstance(authorization, str) and authorization.startswith("Bearer "):
            key = _valid_api_key(authorization.removeprefix("Bearer "))

    if key is None:
        return None

    return TavilyUsageContext(
        server_name=server_name,
        api_key=SecretStr(key),
        credential_fingerprint=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        project_id=str(getattr(settings, "TAVILY_USAGE_PROJECT_ID", "") or ""),
    )

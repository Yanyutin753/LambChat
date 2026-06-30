"""Runtime policy helpers for the workflow plugin."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.kernel.config import settings

PLUGIN_ID = "workflow"
HTTP_POLICY_DISABLED = "disabled"
HTTP_POLICY_ALLOWLIST = "allowlist"
HTTP_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


@dataclass(frozen=True)
class HttpRequestPolicy:
    policy: str = HTTP_POLICY_DISABLED
    allowlist: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 10.0
    max_response_bytes: int = 65536

    @property
    def enabled(self) -> bool:
        return self.policy == HTTP_POLICY_ALLOWLIST

    def validate_method(self, method: str) -> str:
        normalized = method.strip().upper() or "GET"
        if normalized not in HTTP_ALLOWED_METHODS:
            raise ValueError(f"workflow_http_method_not_allowed:{normalized}")
        return normalized

    def validate_url(self, url: str) -> str:
        if not self.enabled:
            raise ValueError("workflow_http_policy_disabled")
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("workflow_http_url_scheme_not_allowed")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("workflow_http_host_missing")
        if "{{" in host or "}}" in host:
            raise ValueError("workflow_http_host_must_be_static")
        if _is_local_or_private_host(host):
            raise ValueError(f"workflow_http_host_blocked:{host}")
        if host not in self.allowlist:
            raise ValueError(f"workflow_http_host_not_allowlisted:{host}")
        return url.strip()


async def resolve_http_request_policy() -> HttpRequestPolicy:
    """Resolve the HTTP node policy from manifest-driven plugin settings."""
    try:
        from src.infra.extensions.plugin_settings import PluginSettingsResolver
        from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

        manifest = build_workflow_plugin_manifest()
        manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / PLUGIN_ID)
        resolver = PluginSettingsResolver(plugin_id=PLUGIN_ID, manifests=(manifest,))
        raw_policy = await resolver.get_str("HTTP_NODE_POLICY", HTTP_POLICY_DISABLED)
        raw_allowlist = await resolver.get("HTTP_ALLOWLIST", [])
        timeout_seconds = await resolver.get_int("DEFAULT_TIMEOUT_SECONDS", 10)
        max_response_bytes = await resolver.get_int("MAX_EVENT_PAYLOAD_BYTES", 65536)
    except Exception:
        raw_policy = HTTP_POLICY_DISABLED
        raw_allowlist = []
        timeout_seconds = 10
        max_response_bytes = 65536

    return build_http_request_policy(
        policy=raw_policy,
        allowlist=raw_allowlist,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )


def build_http_request_policy(
    *,
    policy: Any = HTTP_POLICY_DISABLED,
    allowlist: Any = None,
    timeout_seconds: Any = 10,
    max_response_bytes: Any = 65536,
) -> HttpRequestPolicy:
    normalized_policy = str(policy or HTTP_POLICY_DISABLED).strip().lower()
    if normalized_policy not in {HTTP_POLICY_DISABLED, HTTP_POLICY_ALLOWLIST}:
        normalized_policy = HTTP_POLICY_DISABLED
    return HttpRequestPolicy(
        policy=normalized_policy,
        allowlist=tuple(_normalize_allowlist(allowlist)),
        timeout_seconds=_positive_float(timeout_seconds, default=10.0, maximum=60.0),
        max_response_bytes=int(
            _positive_float(max_response_bytes, default=65536.0, maximum=1048576.0)
        ),
    )


def _normalize_allowlist(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list | tuple | set):
        items = [str(item).strip() for item in value]
    else:
        items = []
    return sorted({item.lower() for item in items if item})


def _positive_float(value: Any, *, default: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum)


def _is_local_or_private_host(host: str) -> bool:
    if host in LOCAL_HOSTNAMES or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )

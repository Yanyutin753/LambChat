"""Runtime guards for plugin-owned API route surfaces."""

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request


def plugin_unavailable_http_error(
    plugin_id: str | None,
    exc: Exception,
) -> HTTPException:
    """Translate a plugin runtime availability failure into a stable API error."""
    resolved_plugin_id = getattr(exc, "plugin_id", None) or plugin_id or "unknown"
    return HTTPException(
        status_code=503,
        detail={
            "error": "plugin_unavailable",
            "plugin_id": resolved_plugin_id,
            "message": str(exc),
        },
    )


def ensure_plugin_route_available(request: Request, plugin_id: str) -> None:
    """Fail closed when a plugin-owned route is called while disabled.

    Tests and compatibility paths can still include a plugin router without a
    runtime attached; production app startup attaches ``app.state.plugin_runtime``.
    """
    runtime = getattr(request.app.state, "plugin_runtime", None)
    ensure_enabled = getattr(runtime, "ensure_enabled", None)
    if not callable(ensure_enabled):
        return
    try:
        ensure_enabled(plugin_id)
    except Exception as exc:  # noqa: BLE001 - runtime boundary normalizes the error
        raise plugin_unavailable_http_error(plugin_id, exc) from exc


def plugin_route_guard(plugin_id: str) -> Callable[[Request], None]:
    """Create a FastAPI dependency for a plugin-owned router module."""

    def dependency(request: Request) -> None:
        ensure_plugin_route_available(request, plugin_id)

    return dependency


def plugin_enabled_dependency(runtime: Any, plugin_id: str) -> Callable[[], None]:
    """Create a FastAPI dependency for routes registered by Plugin Runtime."""

    def dependency() -> None:
        try:
            runtime.ensure_enabled(plugin_id)
        except Exception as exc:  # noqa: BLE001 - runtime boundary normalizes the error
            raise plugin_unavailable_http_error(plugin_id, exc) from exc

    return dependency

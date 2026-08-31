"""Langfuse tracing client.

Self-hosted Langfuse replaces the LangSmith cloud tenant: the langfuse SDK
reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from the
environment (synced by Settings), and its LangChain CallbackHandler picks
the special langfuse_* metadata keys off each run's metadata.
"""

import os
from typing import Any, Dict, Optional


class LangfuseTracer:
    """
    Langfuse tracing integration.

    Environment variables (synced from Settings at startup):
    - LANGFUSE_ENABLED: enable tracing (true/false)
    - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY: API key pair
    - LANGFUSE_HOST: self-hosted server base URL
    """

    def __init__(self) -> None:
        self._enabled: Optional[bool] = None

    def _ensure_initialized(self) -> None:
        """Lazily evaluate the gate on first use."""
        if self._enabled is not None:
            return
        enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        has_keys = bool(os.getenv("LANGFUSE_PUBLIC_KEY")) and bool(os.getenv("LANGFUSE_SECRET_KEY"))
        self._enabled = enabled and has_keys

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled and fully configured."""
        self._ensure_initialized()
        return self._enabled or False

    def callback_handler(self) -> Optional[Any]:
        """Build a fresh CallbackHandler for one agent stream."""
        if not self.enabled:
            return None
        try:
            from langfuse.langchain import CallbackHandler

            return CallbackHandler()
        except Exception:
            return None


def build_langfuse_metadata(
    metadata: Dict[str, Any],
    *,
    session_id: Optional[str],
    user_id: Optional[str],
    trace_name: Optional[str],
) -> Dict[str, Any]:
    """Add the special keys the CallbackHandler maps onto trace attributes."""
    enriched = dict(metadata)
    if session_id:
        enriched["langfuse_session_id"] = session_id
    if user_id:
        enriched["langfuse_user_id"] = user_id
    if trace_name:
        enriched["langfuse_trace_name"] = trace_name
    return enriched


# Global tracer instance (lazy initialization)
langfuse_tracer = LangfuseTracer()

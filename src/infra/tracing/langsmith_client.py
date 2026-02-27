"""LangSmith tracing client."""

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

from langsmith import Client

from src.kernel.config import settings


class LangSmithTracer:
    """
    LangSmith tracing integration.

    Environment variables:
    - LANGSMITH_API_KEY: API key for authentication
    - LANGSMITH_PROJECT: Project name for organizing traces
    - LANGSMITH_TRACING: Enable tracing (true/false)
    """

    def __init__(self) -> None:
        self._enabled: Optional[bool] = None
        self._client: Optional[Client] = None

    def _ensure_initialized(self) -> None:
        """Lazily initialize the tracer on first use."""
        if self._enabled is not None:
            return

        self._enabled = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

        # settings.LANGSMITH_API_KEY 已在 initialize_settings 时从数据库加载
        if self._enabled and settings.LANGSMITH_API_KEY:
            self._client = Client(
                api_key=settings.LANGSMITH_API_KEY,
                api_url=os.getenv("LANGSMITH_API_URL", "https://api.smith.langchain.com"),
            )

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled."""
        self._ensure_initialized()
        return self._enabled or False

    @property
    def client(self) -> Optional[Client]:
        """Get the LangSmith client."""
        self._ensure_initialized()
        return self._client

    @contextmanager
    def trace_run(self, name: str, run_type: str = "chain") -> Generator[Optional[Any], None, None]:
        """Context manager for tracing a run."""
        if not self.enabled or not self.client:
            yield None
            return

        try:
            # Create run with required inputs parameter
            self.client.create_run(
                name=name,
                run_type=run_type,  # type: ignore[arg-type]
                inputs={},
                project_name=os.getenv("LANGSMITH_PROJECT", "lamb-agent"),
            )
            yield None
            # Note: For proper tracing, use @traceable decorator instead
        except Exception:
            raise

    def get_trace_url(self, run_id: str) -> Optional[str]:
        """Get URL to view trace in LangSmith."""
        if not self.enabled or not run_id:
            return None

        project = os.getenv("LANGSMITH_PROJECT", "default")
        return f"https://smith.langchain.com/o/default/projects/p/{project}/r/{run_id}"

    def flush(self) -> None:
        """Flush pending traces."""
        if self.client:
            self.client.flush()


# Global tracer instance (lazy initialization)
tracer = LangSmithTracer()

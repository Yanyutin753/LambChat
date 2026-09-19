"""Invalidate memory scope caches when session ownership changes."""

from __future__ import annotations


def invalidate_memory_scope_caches(
    *, user_id: str, session_id: str | None = None, all_sessions: bool = False
) -> None:
    """Best-effort cache invalidation for session project moves."""
    try:
        from src.infra.memory.scope import invalidate_session_project_cache

        invalidate_session_project_cache(None if all_sessions else session_id)
        from src.infra.agent.middleware.prompt_injection import (
            invalidate_memory_index_snapshot,
        )

        invalidate_memory_index_snapshot(user_id)
    except Exception:
        pass

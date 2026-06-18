"""Read-only internal tools owned by the Feedback plugin."""

from __future__ import annotations

import json
from typing import Annotated, Optional

from langchain.tools import tool

from src.infra.feedback.manager import FeedbackManager


@tool("feedback.summary")
async def feedback_summary(
    session_id: Annotated[Optional[str], "Optional session id to scope feedback stats."] = None,
    run_id: Annotated[Optional[str], "Optional run id to scope feedback stats."] = None,
) -> str:
    """Return read-only Feedback plugin statistics for admins and operators."""
    manager = FeedbackManager()
    try:
        stats = await manager.get_stats(session_id=session_id, run_id=run_id)
        return json.dumps(
            {
                "plugin_id": "feedback",
                "scope": {
                    "session_id": session_id,
                    "run_id": run_id,
                },
                "stats": stats.model_dump(),
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        return json.dumps(
            {
                "plugin_id": "feedback",
                "error": f"Failed to load feedback summary: {exc}",
            },
            ensure_ascii=False,
        )
    finally:
        await manager.close()


def get_feedback_tools():
    """Return internal tools contributed by the built-in Feedback plugin."""
    return [feedback_summary]


__all__ = ["FeedbackManager", "feedback_summary", "get_feedback_tools"]

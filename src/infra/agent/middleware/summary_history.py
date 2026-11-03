"""Require durable history before committing a conversation summary."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from langchain_core.messages import get_buffer_string

from src.infra.async_utils.loop_bridge import run_coro_sync
from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def protect_summary_history(middleware: Any) -> Any:
    """Keep upstream compaction, but fail closed if its raw archive cannot be saved."""
    if not hasattr(middleware, "_aoffload_to_backend"):
        return middleware

    async def archive(backend, messages, session_id):
        path = middleware._get_history_path(session_id)
        filtered = middleware._filter_summary_messages(messages)
        section = (
            f"## Summarized at {datetime.now(UTC).isoformat()}\n\n"
            f"{get_buffer_string(filtered, format='xml')}\n\n"
        )
        for attempt in range(3):
            try:
                responses = await backend.adownload_files([path])
                if not responses:
                    raise OSError("history download returned no result")
                response = responses[0]
                if response.error == "file_not_found":
                    existing = ""
                elif response.error is None and response.content is not None:
                    existing = response.content.decode("utf-8")
                else:
                    raise OSError(f"history download failed: {response.error or 'missing content'}")
                # A lost write response must not duplicate an already committed section.
                if section in existing:
                    return path
                result = (
                    await backend.aedit(path, existing, existing + section)
                    if existing
                    else await backend.awrite(path, section)
                )
                if result is None or result.error:
                    raise OSError(result.error if result else "history write returned no result")
                return path
            except Exception as exc:
                logger.warning(
                    "Conversation history archive failed (%s, attempt %d/3): %s: %s",
                    path,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                )
                if attempt == 2:
                    raise AppError(ErrorCode.CONVERSATION_HISTORY_SAVE_FAILED) from exc
                await asyncio.sleep(0.25 * (attempt + 1))

    middleware._offload_to_backend = lambda backend, messages, session_id: run_coro_sync(
        archive(backend, messages, session_id)
    )

    original_summary = middleware._acreate_summary
    original_wrap = middleware.awrap_model_call
    pending: ContextVar[set[asyncio.Task] | None] = ContextVar(
        "history_summary_tasks", default=None
    )

    def track(operation):
        @wraps(operation)
        async def tracked(*args, **kwargs):
            tasks = pending.get()
            task = asyncio.current_task()
            if tasks is not None and task is not None:
                tasks.add(task)
            try:
                return await operation(*args, **kwargs)
            finally:
                if tasks is not None and task is not None:
                    tasks.discard(task)

        return tracked

    async def wrap(request, handler):
        tasks: set[asyncio.Task] = set()
        token = pending.set(tasks)
        try:
            return await original_wrap(request, handler)
        finally:
            # Upstream gather leaves its sibling running when either operation fails.
            remaining = [task for task in tasks if task is not asyncio.current_task()]
            for task in remaining:
                task.cancel()
            if remaining:
                await asyncio.gather(*remaining, return_exceptions=True)
            pending.reset(token)

    middleware._aoffload_to_backend = track(archive)
    middleware._acreate_summary = track(original_summary)
    middleware.awrap_model_call = wrap
    return middleware

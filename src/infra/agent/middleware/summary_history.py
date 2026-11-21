"""Require durable history before committing a conversation summary."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from io import StringIO
from typing import Any
from uuid import uuid4

from langchain_core.messages import get_buffer_string

from src.infra.async_utils.loop_bridge import run_coro_sync
from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
_SEGMENT_CHARS = 1024 * 1024
_RECONNECT_TIMEOUT = 120.0
_LOCAL_CONNECTION_ERRORS = {
    ErrorCode.DAEMON_OFFLINE,
    ErrorCode.SANDBOX_MACHINE_OFFLINE,
    ErrorCode.SANDBOX_TIMEOUT,
}


def _archive_parts(messages, now):
    def fragments():
        yield f"## Summarized at {now.isoformat()}\n\n"
        for index, message in enumerate(messages):
            if index:
                yield "\n"
            yield get_buffer_string([message], format="xml")
        yield "\n\n"

    buffer = StringIO()
    for text in fragments():
        offset = 0
        while offset < len(text):
            end = offset + _SEGMENT_CHARS - buffer.tell()
            buffer.write(text[offset:end])
            offset = end
            if buffer.tell() == _SEGMENT_CHARS:
                yield buffer.getvalue().encode("utf-8")
                buffer = StringIO()
    if buffer.tell():
        yield buffer.getvalue().encode("utf-8")


def protect_summary_history(middleware: Any) -> Any:
    """Keep upstream compaction, but fail closed if its raw archive cannot be saved."""
    if not hasattr(middleware, "_aoffload_to_backend"):
        return middleware

    async def archive(backend, messages, session_id):
        path = middleware._get_history_path(session_id)
        filtered = middleware._filter_summary_messages(messages)
        now = datetime.now(UTC)
        prefix = f"{path.removesuffix('.md')}.{now:%Y%m%dT%H%M%S%fZ}-{uuid4().hex}"
        for number, part in enumerate(_archive_parts(filtered, now)):
            path = f"{prefix}-{number:08d}.md"
            await save_segment(backend, path, part)
        return path

    async def save_segment(backend, path, part):
        retrying = False
        reconnect_error: AppError | None = None
        try:
            async with asyncio.timeout(None) as recovery:
                attempt = 0
                while True:
                    try:
                        uploads = await backend.aupload_files([(path, part)])
                        if retrying and uploads and "file_conflict" in str(uploads[0].error):
                            # A guarded backend may have committed before losing its reply.
                            existing = await backend.adownload_files([path])
                            if (
                                existing
                                and existing[0].error is None
                                and existing[0].content == part
                            ):
                                return path
                        if not uploads or uploads[0].error:
                            raise OSError(uploads[0].error if uploads else "no upload result")
                        return path
                    except Exception as exc:
                        retrying = True
                        if isinstance(exc, AppError) and exc.error_code in _LOCAL_CONNECTION_ERRORS:
                            reconnect_error = exc
                            if recovery.when() is None:
                                recovery.reschedule(
                                    asyncio.get_running_loop().time() + _RECONNECT_TIMEOUT
                                )
                                logger.warning(
                                    "Waiting for local sandbox reconnection before saving history: %s",
                                    path,
                                )
                            await asyncio.sleep(2)
                            continue
                        logger.warning(
                            "Conversation history archive failed (%s, attempt %d/3): %s: %s",
                            path,
                            attempt + 1,
                            type(exc).__name__,
                            exc,
                        )
                        attempt += 1
                        if attempt == 3:
                            raise AppError(ErrorCode.CONVERSATION_HISTORY_SAVE_FAILED) from exc
                        await asyncio.sleep(0.25 * attempt)
        except TimeoutError:
            if reconnect_error is not None and recovery.expired():
                raise reconnect_error from None
            raise

    middleware._offload_to_backend = lambda backend, messages, session_id: run_coro_sync(
        archive(backend, messages, session_id)
    )

    original_summary = middleware._acreate_summary
    original_wrap = middleware.awrap_model_call
    original_build = middleware._build_new_messages_with_path

    def build(summary, file_path):
        if file_path is None:
            return original_build(summary, None)
        stem = file_path.rsplit(".", 2)[0]
        messages = original_build(summary, None)
        messages[0].content = (
            f"The latest archived conversation segment is at {file_path}. "
            f"Find earlier segments matching {stem}.*.md and the legacy {stem}.md, "
            f"if present.\n\n{messages[0].content}"
        )
        return messages

    middleware._build_new_messages_with_path = build
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

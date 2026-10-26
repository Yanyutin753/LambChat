"""Durable recommendation requests on their owning trace, recoverable across workers."""

from __future__ import annotations

import asyncio
import uuid
from contextvars import Context
from datetime import timedelta
from typing import Any

from langchain_core.runnables.config import var_child_runnable_config
from langsmith import tracing_context
from pymongo import ReturnDocument

from src.agents.core.recommendations import (
    _CURRENT_OUTPUT_MAX_CHARS,
    _CURRENT_USER_MAX_CHARS,
    _HISTORY_MAX_CHARS,
    _clip_text,
    _get_recommend_background_task_limit,
    _normalize_text,
    generate_recommend_questions,
)
from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.session.trace_storage_writes import (
    _ATTACHMENT_CHUNK_WRITE_FIELD,
    _TRACE_EVENT_REVISION_FIELD,
)
from src.infra.utils.datetime import utc_now
from src.infra.websocket import get_connection_manager

logger = get_logger(__name__)
_scan_lock = asyncio.Lock()
_IDENTITY_KEYS = ("user_id", "session_id", "run_id", "trace_id")


async def enqueue_recommendation(
    presenter: Any,
    user_input: str,
    output_text: str,
    history_context: str,
    response_language: str | None,
) -> None:
    identity = {
        key: getattr(presenter, key, None) or getattr(presenter.config, key, None)
        for key in _IDENTITY_KEYS
    }
    if not all(isinstance(value, str) and value for value in identity.values()):
        raise ValueError("Recommendation requires an owned trace")
    storage = get_trace_storage()
    await storage.ensure_indexes_if_needed()
    await storage.collection.update_one(
        {
            **identity,
            "recommendation_request": {"$exists": False},
            "recommend_questions.0": {"$exists": False},
        },
        {
            "$set": {
                "recommendation_request": {
                    "user_input": _clip_text(_normalize_text(user_input), _CURRENT_USER_MAX_CHARS),
                    "output_text": _clip_text(
                        _normalize_text(output_text), _CURRENT_OUTPUT_MAX_CHARS
                    ),
                    "history_context": _clip_text(
                        _normalize_text(history_context), _HISTORY_MAX_CHARS
                    ),
                    "response_language": response_language,
                },
                "recommendation_due_at": utc_now(),
            }
        },
    )


async def _run_claim(record: dict[str, Any]) -> None:
    collection = get_trace_storage().collection
    claim = {key: record[key] for key in _IDENTITY_KEYS}
    claim["recommendation_lease"] = record["recommendation_lease"]
    succeeded = False
    retry_at = utc_now()
    try:
        # Bound execution below the lease so a live old worker cannot overlap its successor.
        async with asyncio.timeout(90):
            owned = {**claim, "recommendation_due_at": {"$gt": utc_now()}}
            current = await collection.find_one(
                owned, {"recommend_questions": 1, "recommendation_request": 1}
            )
            if current is None:
                return
            request = current["recommendation_request"]
            questions = current.get("recommend_questions") or request.get("questions")
            with tracing_context(parent=False):
                if not questions:
                    questions = await generate_recommend_questions(**request)
                    # Cache the paid result before a chunk-write lock or notification can fail.
                    cached = await collection.update_one(
                        {**claim, "recommendation_due_at": {"$gt": utc_now()}},
                        {"$set": {"recommendation_request.questions": questions}},
                    )
                    if not cached.modified_count:
                        return
            now = utc_now()
            saved = await collection.update_one(
                {
                    **claim,
                    "recommendation_due_at": {"$gt": now},
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                {
                    "$set": {
                        "recommend_questions": questions,
                        "recommend_questions_updated_at": now,
                        "updated_at": now,
                    },
                    "$inc": {_TRACE_EVENT_REVISION_FIELD: 1},
                },
            )
            if saved.modified_count:
                await get_connection_manager().send_to_user_with_broadcast(
                    record["user_id"],
                    {
                        "type": "recommend:questions",
                        "data": {
                            "session_id": record["session_id"],
                            "run_id": record["run_id"],
                            "questions": questions,
                        },
                    },
                )
                succeeded = True
    except asyncio.CancelledError:
        raise
    except Exception:
        retry_at = utc_now() + timedelta(seconds=5)
        logger.warning(
            "Recommendation will resume on another pass: %s", record["run_id"], exc_info=True
        )
    finally:
        await collection.update_one(
            claim,
            {
                "$unset": {
                    "recommendation_request": "",
                    "recommendation_due_at": "",
                    "recommendation_lease": "",
                }
            }
            if succeeded
            else {
                "$set": {"recommendation_due_at": retry_at},
                "$unset": {"recommendation_lease": ""},
            },
        )


async def scan_recommendations(ctx: dict[str, Any]) -> None:
    """Claim persisted requests atomically; expired claims survive even SIGKILL."""
    if _scan_lock.locked():
        return
    async with _scan_lock:
        collection = get_trace_storage().collection
        tasks: list[asyncio.Task[None]] = []
        try:
            for _ in range(_get_recommend_background_task_limit()):
                now = utc_now()
                record = await collection.find_one_and_update(
                    {
                        "recommendation_request": {"$exists": True},
                        "recommendation_due_at": {"$lte": now},
                    },
                    {
                        "$set": {
                            "recommendation_due_at": now + timedelta(seconds=120),
                            "recommendation_lease": uuid.uuid4().hex,
                        }
                    },
                    projection={
                        **dict.fromkeys(_IDENTITY_KEYS, 1),
                        "recommendation_request": 1,
                        "recommend_questions": 1,
                        "recommendation_lease": 1,
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if record is None:
                    break
                context = Context()
                context.run(
                    var_child_runnable_config.set,
                    {
                        "configurable": {key: record[key] for key in _IDENTITY_KEYS},
                        "metadata": {"lc_source": "recommendation"},
                        "callbacks": [],
                    },
                )
                task = asyncio.create_task(_run_claim(record), context=context)
                tasks.append(task)
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

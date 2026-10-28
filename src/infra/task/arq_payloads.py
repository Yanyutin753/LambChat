from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Sequence
from typing import Any

from arq.constants import job_key_prefix, result_key_prefix
from arq.jobs import Job, JobStatus, serialize_job
from arq.utils import timestamp_ms

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

from .state_machine import TaskStateMachine
from .status import TaskStatus

logger = get_logger(__name__)

DEFAULT_TASK_ARQ_PAYLOAD_TTL_SECONDS = 60 * 60 * 24
TASK_ARQ_PAYLOAD_PREFIX = "task:arq:payload:"
TASK_ARQ_PAYLOAD_MAX_BYTES = 2 * 1024 * 1024
USER_MESSAGE_SEARCH_INDEX_PAYLOAD_PREFIX = "task:arq:user-message-search-index:"

# ARQ's public enqueue always adds an expiry; scheduled jobs need atomic durable enqueue.
_ENQUEUE_SCHEDULED_LUA = """
if redis.call('EXISTS', KEYS[1], KEYS[2]) > 0 then return 0 end
redis.call('SET', KEYS[1], ARGV[1])
redis.call('ZADD', KEYS[3], ARGV[2], ARGV[3])
return 1
"""


async def enqueue_scheduled_job(pool: Any, dispatch_id: str) -> bool:
    now = timestamp_ms()
    data = serialize_job(
        "run_scheduled_agent_task", (dispatch_id,), {}, None, now, serializer=pool.job_serializer
    )
    return bool(
        await pool.eval(
            _ENQUEUE_SCHEDULED_LUA,
            3,
            job_key_prefix + dispatch_id,
            result_key_prefix + dispatch_id,
            pool.default_queue_name,
            data,
            now,
            dispatch_id,
        )
    )


async def dispatch_jobs(
    enqueue_operations: Sequence[Awaitable[Any]],
    *,
    pool: Any,
    dispatch_id: str,
    session_id: str,
    agent_id: str,
    run_id: str,
    trace_id: str,
    storage: Any,
    heartbeat: Any,
    is_resume: bool,
) -> None:
    enqueue_results = await asyncio.gather(*enqueue_operations, return_exceptions=True)
    main_enqueue_result = enqueue_results[0]
    if isinstance(main_enqueue_result, Exception) or not main_enqueue_result:
        # A lost enqueue reply can still mean an accepted job; probe before failing its run.
        try:
            job_status = await Job(dispatch_id, pool, _queue_name=settings.ARQ_QUEUE_NAME).status()
        except Exception:
            if isinstance(main_enqueue_result, Exception):
                raise main_enqueue_result
            raise
        if job_status == JobStatus.not_found:
            if await heartbeat.is_stale(run_id):
                error = AppError(ErrorCode.INTERNAL_ERROR, message="Task dispatch failed")
                # Resume callers own their claim/approval rollback; do not terminate them here.
                if not is_resume:
                    await _fail_unstarted_dispatch(storage, session_id, run_id, trace_id, error)
                raise error
    elif isinstance(main_enqueue_result, BaseException):
        raise main_enqueue_result
    if len(enqueue_results) > 1 and isinstance(enqueue_results[1], BaseException):
        logger.warning(
            "Failed to enqueue distributed user-message search-index job: run_id=%s",
            run_id,
        )
    logger.info(
        "Task submitted to arq: session=%s, run_id=%s, agent=%s", session_id, run_id, agent_id
    )


async def _fail_unstarted_dispatch(
    storage: Any, session_id: str, run_id: str, trace_id: str, error: AppError
) -> None:
    from src.infra.session.dual_writer import get_dual_writer
    from src.infra.session.trace_storage import get_trace_storage

    try:
        changed = await storage.update_metadata_for_run(
            session_id,
            run_id,
            TaskStateMachine().build_metadata(
                TaskStatus.FAILED,
                error=error.message,
                error_code=error.error_code.code,
                recoverable=False,
            ),
            expected_statuses=["pending", "queued"],
        )
        if not changed:
            return
        writer = get_dual_writer()
        try:
            await writer.write_event(
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id or None,
                event_type="error",
                data={"error": error.message, "code": error.error_code.code, "run_id": run_id},
            )
            await writer.flush_mongo_buffer()
        finally:
            if trace_id:
                await get_trace_storage().complete_trace(
                    trace_id,
                    status="error",
                    metadata={"error": error.message, "error_code": "dispatch_failed"},
                    expected_run_id=run_id,
                )
    except Exception:
        logger.exception("Failed to persist rejected dispatch: run_id=%s", run_id)


class TaskArqPayloadStore:
    """Persist serializable task context for arq workers."""

    def __init__(self, redis: Any | None = None, ttl_seconds: int | None = None) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds or DEFAULT_TASK_ARQ_PAYLOAD_TTL_SECONDS

    @property
    def redis(self) -> Any:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    async def save(self, run_id: str, payload: dict[str, Any]) -> None:
        encoded = await run_blocking_io(json.dumps, payload, ensure_ascii=False)
        size = len(encoded.encode("utf-8"))
        if size > TASK_ARQ_PAYLOAD_MAX_BYTES:
            raise ValueError(
                f"task payload too large: {size} bytes (max {TASK_ARQ_PAYLOAD_MAX_BYTES})"
            )
        await self.redis.set(
            self._key(run_id),
            encoded,
            ex=None
            if payload.get("executor_key") in {"conversation_schedule", "scheduled_agent_stream"}
            else self._ttl_seconds,
        )

    async def load(self, run_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._key(run_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return await run_blocking_io(json.loads, raw)

    async def delete(self, run_id: str) -> bool:
        return bool(await self.redis.delete(self._key(run_id)))

    @staticmethod
    def _key(run_id: str) -> str:
        return f"{TASK_ARQ_PAYLOAD_PREFIX}{run_id}"


class UserMessageSearchIndexPayloadStore(TaskArqPayloadStore):
    """Persist user-message index input for a distributed ARQ worker."""

    @staticmethod
    def _key(run_id: str) -> str:
        return f"{USER_MESSAGE_SEARCH_INDEX_PAYLOAD_PREFIX}{run_id}"

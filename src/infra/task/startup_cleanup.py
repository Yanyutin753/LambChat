from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar, cast

from src.infra.async_utils.blocking import run_blocking_io
from src.infra.logging import get_logger
from src.kernel.extensions import PluginUnavailableError
from src.kernel.config import settings

from .status import TaskStatus

logger = get_logger(__name__)

T = TypeVar("T")
QUEUE_SCAN_PAGE_SIZE = 100
QUEUE_REWRITE_CHUNK_SIZE = 100
STALE_SESSION_SCAN_PAGE_SIZE = 100
STARTUP_CLEANUP_LEASE_KEY = "chat:startup-cleanup:lease"
STARTUP_CLEANUP_LEASE_TTL_SECONDS = 600

_RELEASE_LEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""

_RENEW_LEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
end
return 0
"""


@dataclass(slots=True)
class _StartupCleanupLease:
    redis: Any
    token: str | None


async def _gather_limited(
    factories: list[Callable[[], Awaitable[T]]],
    *,
    limit: int | None = None,
) -> list[T]:
    if not factories:
        return []

    results: list[T | None] = [None] * len(factories)
    next_index = 0
    lock = asyncio.Lock()
    worker_count = min(
        max(1, int(limit or getattr(settings, "TASK_STARTUP_CLEANUP_CONCURRENCY", 16) or 1)),
        len(factories),
    )

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(factories):
                    return
                index = next_index
                next_index += 1
            results[index] = await factories[index]()

    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return cast(list[T], results)


async def _iter_redis_list(redis: Any, key: str, page_size: int = QUEUE_SCAN_PAGE_SIZE):
    start = 0
    while True:
        end = start + page_size - 1
        entries = await redis.lrange(key, start, end)
        if not entries:
            return
        for entry in entries:
            yield entry
        if len(entries) < page_size:
            return
        start += page_size


async def _rpush_in_chunks(
    redis: Any,
    key: str,
    values: list[Any],
    *,
    chunk_size: int | None = None,
) -> None:
    if not values:
        return

    chunk_size = max(1, chunk_size or QUEUE_REWRITE_CHUNK_SIZE)
    for start in range(0, len(values), chunk_size):
        await redis.rpush(key, *values[start : start + chunk_size])


async def _queue_entry_json_loads(entry: Any) -> Any:
    return await run_blocking_io(json.loads, entry)


async def _rewrite_queue_without_expired(
    redis: Any,
    key: str,
    *,
    queue_timeout: float,
) -> int:
    expired = 0
    async for entry in _iter_redis_list(redis, key):
        data = await _queue_entry_json_loads(entry)
        if time.time() - data.get("queued_at", 0) > queue_timeout:
            expired += 1

    if not expired:
        return 0

    tmp_key = f"chat:queue-cleanup:{{{key}}}:{uuid.uuid4().hex}"
    valid_buffer: list[Any] = []
    wrote_valid = False

    async for entry in _iter_redis_list(redis, key):
        data = await _queue_entry_json_loads(entry)
        if time.time() - data.get("queued_at", 0) > queue_timeout:
            continue

        valid_buffer.append(entry)
        if len(valid_buffer) >= QUEUE_REWRITE_CHUNK_SIZE:
            await _rpush_in_chunks(redis, tmp_key, valid_buffer)
            valid_buffer.clear()
            wrote_valid = True

    if valid_buffer:
        await _rpush_in_chunks(redis, tmp_key, valid_buffer)
        valid_buffer.clear()
        wrote_valid = True

    if wrote_valid:
        await redis.rename(tmp_key, key)
    else:
        await redis.delete(key)
    return expired


async def _find_queued_run_ids(
    redis: Any,
    key: str,
    wanted_run_ids: set[str],
    page_size: int = QUEUE_SCAN_PAGE_SIZE,
) -> set[str]:
    if not wanted_run_ids:
        return set()

    found: set[str] = set()
    async for entry in _iter_redis_list(redis, key, page_size=page_size):
        try:
            data = await _queue_entry_json_loads(entry)
        except Exception:
            continue
        queued_run_id = data.get("run_id")
        if queued_run_id is None:
            continue
        queued_run_id = str(queued_run_id)
        if queued_run_id in wanted_run_ids:
            found.add(queued_run_id)
            if len(found) >= len(wanted_run_ids):
                break
    return found


async def _iter_cursor_batches(cursor: Any, page_size: int | None = None):
    page_size = page_size or STALE_SESSION_SCAN_PAGE_SIZE
    while True:
        docs = await cursor.to_list(length=page_size)
        if not docs:
            return
        yield docs
        if len(docs) < page_size:
            return


def _startup_cleanup_lease_ttl_seconds() -> int:
    value = getattr(
        settings,
        "TASK_STARTUP_CLEANUP_LEASE_TTL_SECONDS",
        STARTUP_CLEANUP_LEASE_TTL_SECONDS,
    )
    return max(30, int(value or STARTUP_CLEANUP_LEASE_TTL_SECONDS))


async def _acquire_startup_cleanup_lease(redis: Any) -> _StartupCleanupLease | None:
    set_method = getattr(redis, "set", None)
    if not callable(set_method):
        return _StartupCleanupLease(redis=redis, token=None)

    token = uuid.uuid4().hex
    try:
        acquired = await set_method(
            STARTUP_CLEANUP_LEASE_KEY,
            token,
            ex=_startup_cleanup_lease_ttl_seconds(),
            nx=True,
        )
    except Exception as exc:
        logger.warning("Failed to acquire startup cleanup lease: %s", exc)
        return None

    if not acquired:
        logger.info("Skipping startup cleanup; another instance holds the lease")
        return None
    return _StartupCleanupLease(redis=redis, token=token)


def _start_startup_cleanup_lease_renewal(lease: _StartupCleanupLease) -> asyncio.Task | None:
    if not lease.token or not callable(getattr(lease.redis, "eval", None)):
        return None
    return asyncio.create_task(_renew_startup_cleanup_lease(lease))


async def _renew_startup_cleanup_lease(lease: _StartupCleanupLease) -> None:
    ttl_seconds = _startup_cleanup_lease_ttl_seconds()
    interval = max(10, ttl_seconds // 3)
    try:
        while True:
            await asyncio.sleep(interval)
            renewed = await lease.redis.eval(
                _RENEW_LEASE_LUA,
                1,
                STARTUP_CLEANUP_LEASE_KEY,
                lease.token,
                ttl_seconds,
            )
            if not renewed:
                logger.warning("Startup cleanup lease was lost before renewal")
                return
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Failed to renew startup cleanup lease: %s", exc)


async def _stop_startup_cleanup_lease_renewal(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _release_startup_cleanup_lease(lease: _StartupCleanupLease) -> None:
    if not lease.token:
        return
    eval_method = getattr(lease.redis, "eval", None)
    if not callable(eval_method):
        return
    try:
        await eval_method(_RELEASE_LEASE_LUA, 1, STARTUP_CLEANUP_LEASE_KEY, lease.token)
    except Exception as exc:
        logger.warning("Failed to release startup cleanup lease: %s", exc)


def _task_metadata(session: dict[str, Any], session_model: Any) -> dict[str, Any]:
    raw_metadata = session.get("metadata") if isinstance(session, dict) else {}
    model_metadata = getattr(session_model, "metadata", None) or {}
    return {
        **(raw_metadata if isinstance(raw_metadata, dict) else {}),
        **(model_metadata if isinstance(model_metadata, dict) else {}),
    }


def _is_user_cancelled_task(metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("task_error_code") == "cancelled"
        or metadata.get("task_status") == TaskStatus.CANCELLED.value
    )


async def _has_persisted_cancel_event(session_id: str, run_id: str) -> bool:
    try:
        from src.infra.session.dual_writer import get_dual_writer

        events = await get_dual_writer().read_session_events(
            session_id,
            event_types=["user:cancel"],
            run_id=run_id,
            completed_only=False,
            max_events=1,
        )
        return bool(events)
    except Exception as exc:
        logger.warning(
            "Failed to inspect persisted cancel event during startup recovery: "
            "session=%s, run_id=%s, error=%s",
            session_id,
            run_id,
            exc,
        )
        return False


def _is_latest_run(
    metadata: dict[str, Any],
    run_id: str,
) -> bool:
    """Only reconcile the run that is still recorded as current for the session."""
    current_run_id = metadata.get("current_run_id")
    return current_run_id is not None and str(current_run_id) == str(run_id)


def _is_superseded_by_newer_run(
    metadata: dict[str, Any],
    run_id: str,
) -> bool:
    """Return true when the session already points to a newer conversation run."""
    current_run_id = metadata.get("current_run_id")
    return current_run_id is not None and str(current_run_id) != str(run_id)


def _is_latest_explicit_system_restart_failure(
    metadata: dict[str, Any],
    run_id: str,
) -> bool:
    """Only auto-recover failed runs when shutdown was explicitly recorded."""
    return (
        _is_latest_run(metadata, run_id)
        and metadata.get("task_status") == TaskStatus.FAILED.value
        and metadata.get("task_recoverable") is True
        and metadata.get("task_error_code") == "server_restart"
    )


def _agent_id_from_metadata(metadata: dict[str, Any], session_model: Any) -> str:
    return str(metadata.get("agent_id") or getattr(session_model, "agent_id", "") or "").strip()


def _plugin_agent_is_executable(agent_id: str) -> tuple[bool, str | None]:
    if not agent_id:
        return True, None
    from src.agents import ensure_agent_executable

    try:
        ensure_agent_executable(agent_id)
    except PluginUnavailableError as exc:
        return False, str(exc) or "Plugin-owned agent is unavailable"
    return True, None


class TaskStartupCleanupService:
    """Handles startup reconciliation for stale and queued tasks."""

    def __init__(
        self,
        *,
        storage: Any,
        heartbeat: Any,
        ensure_executor: Callable[[], Any],
        load_session_record: Callable[[dict[str, Any]], Awaitable[Any | None]],
        resume_interrupted_run: Callable[[Any, str, str], Awaitable[dict[str, Any]]],
        replay_pending_queued_tasks: Callable[[], Awaitable[None]] | None = None,
        cleanup_stale_queues: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._storage = storage
        self._heartbeat = heartbeat
        self._ensure_executor = ensure_executor
        self._load_session_record = load_session_record
        self._resume_interrupted_run = resume_interrupted_run
        self._replay_pending_queued_tasks_cb = replay_pending_queued_tasks
        self._cleanup_stale_queues_cb = cleanup_stale_queues

    async def _is_user_cancelled_run(
        self,
        session_id: str,
        metadata: dict[str, Any],
        run_id: str,
    ) -> bool:
        return _is_user_cancelled_task(metadata) or await _has_persisted_cancel_event(
            session_id,
            run_id,
        )

    async def cleanup_stale_tasks(self) -> None:
        """
        Recover stale active tasks and explicitly recoverable failed tasks after restart.
        """
        from .concurrency import get_concurrency_limiter

        limiter = get_concurrency_limiter()
        redis = limiter.redis
        lease = await _acquire_startup_cleanup_lease(redis)
        if lease is None:
            return
        renewal_task = _start_startup_cleanup_lease_renewal(lease)

        try:
            # --- RUNNING tasks ---
            cursor = self._storage.collection.find(
                {"metadata.task_status": TaskStatus.RUNNING.value}
            )

            cleaned_count = 0

            async for running_sessions in _iter_cursor_batches(cursor):
                cleaned_count += await self._process_running_sessions(running_sessions)

            # --- PENDING / QUEUED tasks ---
            cursor = self._storage.collection.find(
                {
                    "metadata.task_status": {
                        "$in": [TaskStatus.PENDING.value, TaskStatus.QUEUED.value]
                    }
                }
            )
            async for pending_sessions in _iter_cursor_batches(cursor):
                cleaned_count += await self._process_pending_sessions(pending_sessions, redis)

            # --- FAILED recoverable tasks ---
            cursor = self._storage.collection.find(
                {
                    "metadata.task_status": TaskStatus.FAILED.value,
                    "metadata.task_recoverable": True,
                    "metadata.task_error_code": "server_restart",
                }
            )
            async for failed_recoverable_sessions in _iter_cursor_batches(cursor):
                cleaned_count += await self._process_failed_recoverable_sessions(
                    failed_recoverable_sessions
                )

            if cleaned_count > 0:
                logger.info("Cleaned up %s stale tasks without heartbeat", cleaned_count)

            await self.replay_pending_queued_tasks()
            await self.cleanup_stale_queues()
        except Exception as e:
            logger.error("Failed to cleanup stale tasks: %s", e)
        finally:
            await _stop_startup_cleanup_lease_renewal(renewal_task)
            await _release_startup_cleanup_lease(lease)

    async def _process_running_sessions(self, running_sessions: list[dict[str, Any]]) -> int:
        load_session_factories: list[Callable[[], Awaitable[Any]]] = []
        for session in running_sessions:

            async def _load_session(session: dict[str, Any] = session) -> Any:
                return await self._load_session_record(session)

            load_session_factories.append(_load_session)

        session_models = await _gather_limited(load_session_factories)

        candidates: list[tuple[Any, str, dict[str, Any], str]] = []
        for session, session_model in zip(running_sessions, session_models):
            if session_model is None:
                continue
            session_id = session_model.id
            metadata = _task_metadata(session, session_model)
            run_id = session.get("metadata", {}).get("current_run_id") or metadata.get(
                "current_run_id"
            )
            if not run_id:
                continue
            if await self._is_user_cancelled_run(session_id, metadata, str(run_id)):
                logger.info(
                    "Skipping user-cancelled RUNNING task during startup recovery: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue
            if _is_superseded_by_newer_run(metadata, run_id):
                logger.info(
                    "Skipping superseded RUNNING task during startup recovery: session=%s, old_run=%s, current_run=%s",
                    session_id,
                    run_id,
                    metadata.get("current_run_id"),
                )
                continue
            if not _is_latest_run(metadata, run_id):
                logger.debug(
                    "Skipping non-current RUNNING task during startup recovery: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue
            candidates.append((session_model, session_id, metadata, run_id))

        if not candidates:
            return 0

        cleaned_count = 0
        heartbeat_factories: list[Callable[[], Awaitable[bool]]] = []
        for _, _, _, run_id in candidates:

            async def _check_heartbeat(run_id: str = run_id) -> bool:
                return await self._heartbeat.check_exists(run_id)

            heartbeat_factories.append(_check_heartbeat)

        heartbeat_results = await _gather_limited(heartbeat_factories)
        for (
            session_model,
            session_id,
            metadata,
            run_id,
        ), heartbeat_exists in zip(candidates, heartbeat_results):
            if heartbeat_exists:
                logger.debug(
                    "Task still running on another instance: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue

            logger.warning(
                "Cleaning up stale RUNNING task (no heartbeat): session=%s, run_id=%s",
                session_id,
                run_id,
            )
            recovery_result = await self._resume_interrupted_run(
                session_model,
                run_id,
                "server_restart",
            )
            if recovery_result.get("success"):
                logger.info(
                    "Recovered stale RUNNING task: session=%s, old_run=%s, new_run=%s",
                    session_id,
                    run_id,
                    recovery_result.get("run_id"),
                )
            else:
                logger.warning(
                    "Failed to auto-recover stale RUNNING task %s: %s",
                    run_id,
                    recovery_result.get("message"),
                )
            cleaned_count += 1
        return cleaned_count

    async def _process_pending_sessions(
        self,
        pending_sessions: list[dict[str, Any]],
        redis: Any,
    ) -> int:
        pending_load_factories: list[Callable[[], Awaitable[Any]]] = []
        for session in pending_sessions:

            async def _load_pending_session(session: dict[str, Any] = session) -> Any:
                return await self._load_session_record(session)

            pending_load_factories.append(_load_pending_session)

        pending_models = await _gather_limited(pending_load_factories)

        pending_candidates: list[tuple[Any, str, dict[str, Any], str, str]] = []
        for session, session_model in zip(pending_sessions, pending_models):
            if session_model is None:
                continue
            session_id = session_model.id
            metadata = _task_metadata(session, session_model)
            run_id = session.get("metadata", {}).get("current_run_id") or metadata.get(
                "current_run_id"
            )
            user_id = session.get("user_id")
            if not run_id or not user_id:
                continue
            if await self._is_user_cancelled_run(session_id, metadata, str(run_id)):
                logger.info(
                    "Skipping user-cancelled PENDING task during startup recovery: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue
            if _is_superseded_by_newer_run(metadata, run_id):
                logger.info(
                    "Skipping superseded PENDING task during startup recovery: session=%s, old_run=%s, current_run=%s",
                    session_id,
                    run_id,
                    metadata.get("current_run_id"),
                )
                continue
            if not _is_latest_run(metadata, run_id):
                logger.debug(
                    "Skipping non-current PENDING task during startup recovery: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue
            pending_candidates.append((session_model, session_id, metadata, run_id, user_id))

        if not pending_candidates:
            return 0

        active_factories: list[Callable[[], Awaitable[Any]]] = []
        for _, _, _, run_id, user_id in pending_candidates:

            async def _active_score(run_id: str = run_id, user_id: str = user_id) -> Any:
                return await redis.zscore(f"chat:active:{user_id}", run_id)

            active_factories.append(_active_score)

        active_results = await _gather_limited(active_factories)
        active_candidates = [
            cand for cand, score in zip(pending_candidates, active_results) if score is not None
        ]
        if not active_candidates:
            return 0

        cleaned_count = 0
        pending_heartbeat_factories: list[Callable[[], Awaitable[bool]]] = []
        for _, _, _, run_id, _ in active_candidates:

            async def _check_pending_heartbeat(run_id: str = run_id) -> bool:
                return await self._heartbeat.check_exists(run_id)

            pending_heartbeat_factories.append(_check_pending_heartbeat)

        heartbeat_results = await _gather_limited(pending_heartbeat_factories)
        for (
            session_model,
            session_id,
            metadata,
            run_id,
            user_id,
        ), heartbeat_exists in zip(active_candidates, heartbeat_results):
            if heartbeat_exists:
                logger.debug(
                    "Pending task still in active set (running elsewhere): session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue

            logger.warning(
                "Cleaning up stale PENDING task (in active set, no heartbeat): session=%s, run_id=%s",
                session_id,
                run_id,
            )
            recovery_result = await self._resume_interrupted_run(
                session_model,
                run_id,
                "server_restart",
            )
            if recovery_result.get("success"):
                logger.info(
                    "Recovered stale PENDING task: session=%s, old_run=%s, new_run=%s",
                    session_id,
                    run_id,
                    recovery_result.get("run_id"),
                )
            else:
                logger.warning(
                    "Failed to auto-recover stale PENDING task %s: %s",
                    run_id,
                    recovery_result.get("message"),
                )
            cleaned_count += 1
        return cleaned_count

    async def _process_failed_recoverable_sessions(
        self,
        failed_recoverable_sessions: list[dict[str, Any]],
    ) -> int:
        failed_load_factories: list[Callable[[], Awaitable[Any]]] = []
        for session in failed_recoverable_sessions:

            async def _load_failed_session(session: dict[str, Any] = session) -> Any:
                return await self._load_session_record(session)

            failed_load_factories.append(_load_failed_session)

        failed_models = await _gather_limited(failed_load_factories)

        failed_candidates: list[tuple[Any, str, dict[str, Any], str]] = []
        for session, session_model in zip(failed_recoverable_sessions, failed_models):
            if session_model is None:
                continue
            session_id = session_model.id
            run_id = session.get("metadata", {}).get("current_run_id")
            if not run_id:
                continue
            metadata = _task_metadata(session, session_model)
            if not _is_latest_explicit_system_restart_failure(metadata, run_id):
                logger.debug(
                    "Skipping unmarked FAILED task during startup recovery: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue
            failed_candidates.append((session_model, session_id, metadata, run_id))

        if not failed_candidates:
            return 0

        cleaned_count = 0
        failed_heartbeat_factories: list[Callable[[], Awaitable[bool]]] = []
        for _, _, _, run_id in failed_candidates:

            async def _check_failed_heartbeat(run_id: str = run_id) -> bool:
                return await self._heartbeat.check_exists(run_id)

            failed_heartbeat_factories.append(_check_failed_heartbeat)

        failed_heartbeat_results = await _gather_limited(failed_heartbeat_factories)
        for (
            session_model,
            session_id,
            metadata,
            run_id,
        ), heartbeat_exists in zip(failed_candidates, failed_heartbeat_results):
            if heartbeat_exists:
                logger.debug(
                    "Recoverable failed task still has heartbeat: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                continue

            logger.warning(
                "Recovering failed-but-recoverable task: session=%s, run_id=%s",
                session_id,
                run_id,
            )
            recovery_result = await self._resume_interrupted_run(
                session_model,
                run_id,
                "server_restart",
            )
            if recovery_result.get("success"):
                logger.info(
                    "Recovered failed task: session=%s, old_run=%s, new_run=%s",
                    session_id,
                    run_id,
                    recovery_result.get("run_id"),
                )
            else:
                logger.warning(
                    "Failed to auto-recover failed task %s: %s",
                    run_id,
                    recovery_result.get("message"),
                )
            cleaned_count += 1
        return cleaned_count

    async def cleanup_stale_queues(self) -> None:
        """Drop queue entries that have exceeded the concurrency queue timeout."""
        if self._cleanup_stale_queues_cb is not None:
            await self._cleanup_stale_queues_cb()
            return

        try:
            from .concurrency import QUEUE_TIMEOUT, get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="chat:queue:*", count=100)
                for key in keys:
                    expired = await _rewrite_queue_without_expired(
                        redis,
                        key,
                        queue_timeout=QUEUE_TIMEOUT,
                    )
                    if expired:
                        logger.info("Cleaned %s expired queue entries from %s", expired, key)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Failed to cleanup stale queues: %s", e)

    async def replay_pending_queued_tasks(self) -> None:
        """Replay latest queued tasks that still have Redis queue entries."""
        if self._replay_pending_queued_tasks_cb is not None:
            await self._replay_pending_queued_tasks_cb()
            return

        try:
            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            cursor = self._storage.collection.find(
                {
                    "metadata.task_status": {
                        "$in": [TaskStatus.PENDING.value, TaskStatus.QUEUED.value]
                    }
                }
            )

            replayed = 0
            abandoned = 0

            async for pending_sessions in _iter_cursor_batches(cursor):
                replay_candidates: list[
                    tuple[dict[str, Any], Any, str, dict[str, Any], str, str]
                ] = []
                wanted_run_ids_by_user: dict[str, set[str]] = {}
                replay_load_factories: list[Callable[[], Awaitable[Any]]] = []
                for session in pending_sessions:

                    async def _load_replay_session(session: dict[str, Any] = session) -> Any:
                        return await self._load_session_record(session)

                    replay_load_factories.append(_load_replay_session)

                pending_models = await _gather_limited(replay_load_factories)

                for session, session_model in zip(pending_sessions, pending_models):
                    if session_model is None:
                        continue
                    session_id = session_model.id
                    metadata = _task_metadata(session, session_model)
                    run_id = session.get("metadata", {}).get("current_run_id") or metadata.get(
                        "current_run_id"
                    )
                    user_id = session.get("user_id")
                    if not run_id or not user_id:
                        continue
                    if await self._is_user_cancelled_run(session_id, metadata, str(run_id)):
                        logger.info(
                            "Skipping user-cancelled queued task replay during startup recovery: session=%s, run_id=%s",
                            session_id,
                            run_id,
                        )
                        continue

                    if _is_superseded_by_newer_run(metadata, run_id):
                        logger.info(
                            "Skipping superseded queued task replay during startup recovery: session=%s, old_run=%s, current_run=%s",
                            session_id,
                            run_id,
                            metadata.get("current_run_id"),
                        )
                        continue

                    if not _is_latest_run(metadata, run_id):
                        logger.debug(
                            "Skipping non-current queued task replay during startup recovery: session=%s, run_id=%s",
                            session_id,
                            run_id,
                        )
                        continue

                    run_id = str(run_id)
                    replay_candidates.append(
                        (session, session_model, session_id, metadata, run_id, user_id)
                    )
                    wanted_run_ids_by_user.setdefault(user_id, set()).add(run_id)

                queued_run_ids_by_user: dict[str, set[str]] = {}
                for user_id, wanted_run_ids in wanted_run_ids_by_user.items():
                    queue_key = f"chat:queue:{user_id}"
                    queued_run_ids_by_user[user_id] = await _find_queued_run_ids(
                        redis,
                        queue_key,
                        wanted_run_ids,
                    )

                for (
                    session,
                    session_model,
                    session_id,
                    metadata,
                    run_id,
                    user_id,
                ) in replay_candidates:
                    agent_id = _agent_id_from_metadata(metadata, session_model)
                    agent_executable, agent_error = _plugin_agent_is_executable(agent_id)
                    if not agent_executable:
                        logger.warning(
                            "Skipping queued task replay for unavailable plugin-owned agent: session=%s, run_id=%s, agent_id=%s",
                            session_id,
                            run_id,
                            agent_id,
                        )
                        executor = self._ensure_executor()
                        await executor._update_session_status(
                            session_id,
                            TaskStatus.FAILED,
                            agent_error,
                            run_id=run_id,
                        )
                        continue

                    if run_id in queued_run_ids_by_user.get(user_id, set()):
                        logger.info(
                            "Replaying queued task on startup: session=%s, run_id=%s",
                            session_id,
                            run_id,
                        )
                        try:
                            await limiter.release(user_id, run_id)
                            replayed += 1
                        except Exception as e:
                            logger.warning("Failed to replay queued task %s: %s", run_id, e)
                    else:
                        active_key = f"chat:active:{user_id}"
                        in_active = await redis.zscore(active_key, run_id) is not None
                        heartbeat_exists = await self._heartbeat.check_exists(run_id)

                        if in_active or heartbeat_exists:
                            logger.debug(
                                "Pending task still active or running elsewhere: session=%s, run_id=%s",
                                session_id,
                                run_id,
                            )
                        else:
                            logger.warning(
                                "Abandoned queued task (no queue entry, no active, no heartbeat): session=%s, run_id=%s",
                                session_id,
                                run_id,
                            )
                            recovery_result = await self._resume_interrupted_run(
                                session_model,
                                run_id,
                                "server_restart",
                            )
                            if recovery_result.get("success"):
                                logger.info(
                                    "Recovered abandoned queued task: session=%s, old_run=%s, new_run=%s",
                                    session_id,
                                    run_id,
                                    recovery_result.get("run_id"),
                                )
                            else:
                                executor = self._ensure_executor()
                                await executor._update_session_status(
                                    session_id,
                                    TaskStatus.EXPIRED,
                                    "Task abandoned (server restarted while queued)",
                                    run_id=run_id,
                                )
                                abandoned += 1

            if replayed > 0:
                logger.info("Replayed %s queued tasks on startup", replayed)
            if abandoned > 0:
                logger.warning("Marked %s abandoned queued tasks as EXPIRED", abandoned)
        except Exception as e:
            logger.error("Failed to replay pending queued tasks: %s", e)

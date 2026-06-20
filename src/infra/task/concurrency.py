"""
Per-user chat concurrency limiter (Redis-based, distributed-safe)

Uses Redis Sorted Set for active task tracking (score=heartbeat timestamp).
Entries auto-expire when heartbeats stop (worker crash / restart safe).
Redis List for queuing waiting tasks — full task context stored in the entry
so any worker can dispatch without shared memory.

Redis key design:
  chat:active:{user_id}   -> Sorted Set (score=timestamp, member=run_id)
  chat:queue:{user_id}    -> List of queued run entries (JSON with full context)
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from src.infra.async_utils import run_blocking_io
from src.infra.session.storage import SessionUpdate
from src.infra.storage.redis import get_redis_client
from src.infra.task.constants import HEARTBEAT_TIMEOUT
from src.kernel.config import settings
from src.kernel.extensions import PluginUnavailableError

from .status import TaskStatus

logger = logging.getLogger(__name__)

QUEUE_TIMEOUT = 300  # 5 minutes max wait in queue
USER_LOCK_TTL = 5
USER_LOCK_WAIT_SECONDS = 5.0
USER_LOCK_POLL_INTERVAL = 0.05
QUEUE_SCAN_PAGE_SIZE = 100
QUEUE_ENTRY_MAX_BYTES = 2 * 1024 * 1024
QUEUE_REWRITE_CHUNK_SIZE = 100


async def _queue_json_dumps(value: Any) -> str:
    return await run_blocking_io(json.dumps, value, ensure_ascii=False)


async def _queue_json_loads(value: Any) -> Any:
    return await run_blocking_io(json.loads, value)


# ---------------------------------------------------------------------------
# Executor registry — maps string keys to callables so queued tasks can be
# dispatched by any worker without serialising function references.
# ---------------------------------------------------------------------------
_EXECUTOR_REGISTRY: Dict[str, Callable] = {}


def register_executor(key: str, executor: Callable) -> None:
    """Register an executor callable under a stable string key."""
    _EXECUTOR_REGISTRY[key] = executor


def unregister_executor(key: str) -> None:
    """Unregister an executor callable. Removes the key from the registry."""
    _EXECUTOR_REGISTRY.pop(key, None)


def get_registered_executor(key: str) -> Optional[Callable]:
    """Look up a registered executor by key.  Returns None if not found."""
    return _EXECUTOR_REGISTRY.get(key)


class ConcurrencyResult(str, Enum):
    """Result of concurrency check."""

    STARTED = "started"
    QUEUED = "queued"
    REJECTED_QUEUE = "rejected_queue"


@dataclass
class ConcurrencyResponse:
    """Response from concurrency check."""

    result: ConcurrencyResult
    queue_position: int = 0
    max_concurrent: int = 0
    active_count: int = 0
    queue_length: int = 0


@dataclass
class _DequeuedTask:
    user_id: str
    run_id: str
    session_id: str
    queue_data: dict[str, Any]


class UserConcurrencyLimiter:
    """Redis-based per-user chat concurrency limiter.

    Active tasks are tracked in a Sorted Set with heartbeat timestamps as scores.
    This makes the system self-healing:
    - Worker crash -> heartbeat stops -> entry expires -> count auto-corrects
    - No manual cleanup needed on restart
    - Distributed-safe: each worker refreshes its own entries via heartbeat
    """

    def __init__(self):
        self._redis = None

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    @staticmethod
    def _active_key(user_id: str) -> str:
        return f"chat:active:{user_id}"

    @staticmethod
    def _queue_key(user_id: str) -> str:
        return f"chat:queue:{user_id}"

    @staticmethod
    def _lock_key(user_id: str) -> str:
        return f"chat:lock:{user_id}"

    async def _iter_queue_entries(self, queue_key: str, page_size: int = QUEUE_SCAN_PAGE_SIZE):
        start = 0
        while True:
            end = start + page_size - 1
            entries = await self.redis.lrange(queue_key, start, end)
            if not entries:
                return
            for entry in entries:
                yield entry
            if len(entries) < page_size:
                return
            start += page_size

    async def get_user_limits(self, roles: list[str]) -> Tuple[Optional[int], Optional[int]]:
        """Get effective concurrency limits from user's roles (most permissive wins).

        Returns:
            (max_concurrent, max_queued) — None means unlimited
        """
        from src.infra.role.storage import RoleStorage

        max_concurrent = None
        max_queued = None

        try:
            role_storage = RoleStorage()
            # Single batch query instead of N individual lookups
            user_roles = await role_storage.get_by_names(roles)
            for role in user_roles:
                if role.limits:
                    rc = role.limits.max_concurrent_chats
                    rq = role.limits.max_queued_chats
                    if rc is not None:
                        max_concurrent = rc if max_concurrent is None else max(max_concurrent, rc)
                    if rq is not None:
                        max_queued = rq if max_queued is None else max(max_queued, rq)
        except Exception as e:
            logger.warning(f"Failed to get role limits, using defaults: {e}")
            max_concurrent = 5
            max_queued = 10

        return max_concurrent, max_queued

    async def _get_active_count(self, user_id: str) -> int:
        """Count tasks with recent heartbeats (excludes crashed workers)."""
        try:
            cutoff = time.time() - HEARTBEAT_TIMEOUT
            return await self.redis.zcount(self._active_key(user_id), cutoff, "+inf")
        except Exception as e:
            logger.warning(f"Failed to get active count: {e}")
            return 0

    async def _cleanup_stale_active(self, user_id: str) -> None:
        """Remove entries with expired heartbeats from the sorted set."""
        try:
            cutoff = time.time() - HEARTBEAT_TIMEOUT
            removed = await self.redis.zremrangebyscore(self._active_key(user_id), "-inf", cutoff)
            if removed:
                logger.info(f"Cleaned {removed} stale active entries for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup stale active entries: {e}")

    async def _acquire_user_lock(self, user_id: str) -> tuple[str, str]:
        """Acquire a short-lived per-user Redis mutex for distributed-safe slot updates."""
        lock_key = self._lock_key(user_id)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + USER_LOCK_WAIT_SECONDS

        while time.monotonic() < deadline:
            acquired = await self.redis.set(lock_key, token, ex=USER_LOCK_TTL, nx=True)
            if acquired:
                return lock_key, token
            await asyncio.sleep(USER_LOCK_POLL_INTERVAL)

        raise TimeoutError(f"Timed out acquiring concurrency lock for user {user_id}")

    async def _release_user_lock(self, lock_key: str, token: str) -> None:
        """Release a per-user Redis mutex if we still own it."""
        try:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self.redis.eval(lua_script, 1, lock_key, token)
        except Exception as e:
            logger.warning(f"Failed to release concurrency lock {lock_key}: {e}")

    async def _queue_task_locked(
        self,
        user_id: str,
        run_id: str,
        session_id: str,
        task_context: Optional[Dict[str, Any]],
        max_concurrent: Optional[int],
        active_count: int,
        max_queued: Optional[int],
    ) -> ConcurrencyResponse:
        """Queue a task while holding the per-user lock."""
        if max_queued is not None:
            queue_length = await self.redis.llen(self._queue_key(user_id))
            if queue_length >= max_queued:
                return ConcurrencyResponse(
                    result=ConcurrencyResult.REJECTED_QUEUE,
                    max_concurrent=max_concurrent or 0,
                    active_count=active_count,
                    queue_length=queue_length,
                )

        entry = await _queue_json_dumps(
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "queued_at": time.time(),
                "task_context": task_context or {},
            }
        )
        entry_size = len(entry.encode("utf-8"))
        if entry_size > QUEUE_ENTRY_MAX_BYTES:
            logger.warning(
                "Rejecting oversized queued task context: user=%s run=%s size=%s max=%s",
                user_id,
                run_id,
                entry_size,
                QUEUE_ENTRY_MAX_BYTES,
            )
            return ConcurrencyResponse(
                result=ConcurrencyResult.REJECTED_QUEUE,
                max_concurrent=max_concurrent or 0,
                active_count=active_count,
                queue_length=await self.redis.llen(self._queue_key(user_id)),
            )
        await self.redis.rpush(self._queue_key(user_id), entry)
        queue_length = await self.redis.llen(self._queue_key(user_id))
        logger.info(
            f"Task queued: user={user_id}, run={run_id}, position={queue_length}, "
            f"active={active_count}/{max_concurrent}"
        )
        return ConcurrencyResponse(
            result=ConcurrencyResult.QUEUED,
            queue_position=queue_length,
            max_concurrent=max_concurrent or 0,
            active_count=active_count,
            queue_length=queue_length,
        )

    async def _acquire_locked(
        self,
        user_id: str,
        roles: list[str],
        run_id: str,
        session_id: str,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> ConcurrencyResponse:
        """Try to acquire a slot while holding the per-user lock."""
        max_concurrent, max_queued = await self.get_user_limits(roles)

        if max_concurrent is None:
            return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

        await self._cleanup_stale_active(user_id)
        active_count = await self._get_active_count(user_id)

        if active_count < max_concurrent:
            await self.redis.zadd(
                self._active_key(user_id),
                {run_id: time.time()},
            )
            return ConcurrencyResponse(
                result=ConcurrencyResult.STARTED,
                max_concurrent=max_concurrent,
                active_count=active_count + 1,
            )

        return await self._queue_task_locked(
            user_id=user_id,
            run_id=run_id,
            session_id=session_id,
            task_context=task_context,
            max_concurrent=max_concurrent,
            active_count=active_count,
            max_queued=max_queued,
        )

    async def acquire(
        self,
        user_id: str,
        roles: list[str],
        run_id: str,
        session_id: str,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> ConcurrencyResponse:
        """Try to acquire a concurrency slot for a task."""
        try:
            lock_key, token = await self._acquire_user_lock(user_id)
            try:
                return await self._acquire_locked(
                    user_id=user_id,
                    roles=roles,
                    run_id=run_id,
                    session_id=session_id,
                    task_context=task_context,
                )
            finally:
                await self._release_user_lock(lock_key, token)
        except Exception as e:
            logger.error(f"Concurrency limiter error (fail-open): {e}")
            return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

    async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
        """Release a concurrency slot and trigger next queued task."""
        dequeued_task: _DequeuedTask | None = None
        try:
            lock_key, token = await self._acquire_user_lock(user_id)
            try:
                await self._release_active_slot_locked(user_id, run_id)
                if dequeue:
                    dequeued_task = await self._try_dequeue_next_locked(
                        user_id,
                        dispatch=False,
                    )
            finally:
                await self._release_user_lock(lock_key, token)

            if dequeued_task is not None:
                await self._dispatch_queued_task(
                    dequeued_task.user_id,
                    dequeued_task.run_id,
                    dequeued_task.session_id,
                    dequeued_task.queue_data,
                )
        except Exception as e:
            logger.error(f"Concurrency release error: {e}")

    async def _release_active_slot_locked(self, user_id: str, run_id: str) -> None:
        """Release an active slot while the caller already holds the per-user lock."""
        await self.redis.zrem(self._active_key(user_id), run_id)

    async def refresh(self, user_id: str, run_id: str) -> None:
        """Refresh heartbeat timestamp for an active task.

        Called periodically by the task heartbeat mechanism to keep
        the entry alive in the sorted set.
        """
        try:
            await self.redis.zadd(
                self._active_key(user_id),
                {run_id: time.time()},
            )
        except Exception as e:
            logger.warning(f"Failed to refresh concurrency entry: {e}")

    async def _try_dequeue_next(self, user_id: str) -> None:
        """Try to dequeue next valid (non-expired) task from queue."""
        dequeued_task: _DequeuedTask | None = None
        try:
            lock_key, token = await self._acquire_user_lock(user_id)
            try:
                dequeued_task = await self._try_dequeue_next_locked(user_id, dispatch=False)
            finally:
                await self._release_user_lock(lock_key, token)

            if dequeued_task is not None:
                await self._dispatch_queued_task(
                    dequeued_task.user_id,
                    dequeued_task.run_id,
                    dequeued_task.session_id,
                    dequeued_task.queue_data,
                )
        except Exception as e:
            logger.error(f"Dequeue error: {e}")

    async def _try_dequeue_next_locked(
        self,
        user_id: str,
        *,
        dispatch: bool = True,
    ) -> _DequeuedTask | None:
        """Try to dequeue the next queued task while holding the per-user lock."""
        queue_key = self._queue_key(user_id)
        attempts = 0
        while attempts < 20:
            attempts += 1
            entry = await self.redis.lpop(queue_key)
            if entry is None:
                return None

            try:
                data = await _queue_json_loads(entry)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Discarding corrupt queued task entry: %s", exc)
                continue
            if not isinstance(data, dict):
                logger.warning("Discarding non-object queued task entry: %r", data)
                continue
            if time.time() - data.get("queued_at", 0) > QUEUE_TIMEOUT:
                logger.info(f"Discarding expired queued task: run={data.get('run_id')}")
                continue

            run_id = data.get("run_id")
            session_id = data.get("session_id")
            if not run_id or not session_id:
                logger.warning("Discarding queued task entry missing run_id or session_id")
                continue

            max_concurrent, _ = await self.get_user_limits_from_cache(user_id)
            if max_concurrent is not None:
                await self._cleanup_stale_active(user_id)
                active_count = await self._get_active_count(user_id)
                if active_count >= max_concurrent:
                    await self.redis.lpush(queue_key, entry)
                    return None

            await self.redis.zadd(self._active_key(user_id), {run_id: time.time()})
            logger.info(f"Task dequeued: user={user_id}, run={run_id}")
            if dispatch:
                await self._dispatch_queued_task(user_id, run_id, session_id, data)
                return None
            return _DequeuedTask(
                user_id=user_id,
                run_id=run_id,
                session_id=session_id,
                queue_data=data,
            )

        return None

    async def get_user_limits_from_cache(self, user_id: str) -> Tuple[Optional[int], Optional[int]]:
        """Get limits (cache not implemented, delegates to get_user_limits with empty roles).

        Used internally when we don't have role info — falls back to defaults.
        """
        from src.infra.user.storage import UserStorage

        try:
            user = await UserStorage().get_by_id(user_id)
            roles = getattr(user, "roles", None) or []
            return await self.get_user_limits(roles)
        except Exception as e:
            logger.warning(f"Failed to load user limits for {user_id}, using defaults: {e}")
            return 5, 10

    async def claim_recovery_slot(
        self,
        user_id: str,
        roles: list[str],
        old_run_id: str,
        new_run_id: str,
        session_id: str,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> ConcurrencyResponse:
        """Claim a slot for recovery by swapping the old run or queueing safely."""
        try:
            lock_key, token = await self._acquire_user_lock(user_id)
            try:
                max_concurrent, max_queued = await self.get_user_limits(roles)
                active_key = self._active_key(user_id)

                if max_concurrent is None:
                    if old_run_id:
                        await self.redis.zrem(active_key, old_run_id)
                    await self.redis.zadd(active_key, {new_run_id: time.time()})
                    return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

                await self._cleanup_stale_active(user_id)
                if await self.redis.zscore(active_key, old_run_id) is not None:
                    await self.redis.zrem(active_key, old_run_id)
                    await self.redis.zadd(active_key, {new_run_id: time.time()})
                    return ConcurrencyResponse(
                        result=ConcurrencyResult.STARTED,
                        max_concurrent=max_concurrent,
                        active_count=await self._get_active_count(user_id),
                    )

                active_count = await self._get_active_count(user_id)
                if active_count < max_concurrent:
                    await self.redis.zadd(active_key, {new_run_id: time.time()})
                    return ConcurrencyResponse(
                        result=ConcurrencyResult.STARTED,
                        max_concurrent=max_concurrent,
                        active_count=active_count + 1,
                    )

                return await self._queue_task_locked(
                    user_id=user_id,
                    run_id=new_run_id,
                    session_id=session_id,
                    task_context=task_context,
                    max_concurrent=max_concurrent,
                    active_count=active_count,
                    max_queued=max_queued,
                )
            finally:
                await self._release_user_lock(lock_key, token)
        except Exception as e:
            logger.error(f"Recovery slot claim error (fail-open): {e}")
            return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

    async def _dispatch_queued_task(
        self,
        user_id: str,
        run_id: str,
        session_id: str,
        queue_data: dict,
    ) -> None:
        """Dispatch a queued task by creating a background task.

        Reads task context from Redis queue entry (multi-worker safe).
        Falls back to in-memory _pending_tasks for entries written before migration.
        """
        try:
            from src.infra.task.manager import get_task_manager

            task_manager = get_task_manager()

            # --- Resolve task context (Redis-first, memory fallback) ---
            task_ctx = queue_data.get("task_context")
            executor_key = None
            if task_ctx and task_ctx.get("executor_key"):
                # New format: context stored in Redis, executor resolved from registry
                executor_key = str(task_ctx["executor_key"])
                executor_fn = get_registered_executor(executor_key)
                if executor_fn is None and settings.TASK_BACKEND != "arq":
                    logger.error(f"No executor registered for key '{executor_key}' (run={run_id})")
                    await self._release_active_slot_locked(user_id, run_id)
                    return
                dispatch_user_id = queue_data.get("user_id", user_id)
                agent_id = task_ctx["agent_id"]
                message = task_ctx["message"]
                disabled_tools = task_ctx.get("disabled_tools")
                agent_options = task_ctx.get("agent_options")
                attachments = task_ctx.get("attachments")
                disabled_skills = task_ctx.get("disabled_skills")
                enabled_skills = task_ctx.get("enabled_skills")
                persona_system_prompt = task_ctx.get("persona_system_prompt")
                disabled_mcp_tools = task_ctx.get("disabled_mcp_tools")
                team_id = task_ctx.get("team_id")
                active_goal = task_ctx.get("active_goal")
            else:
                # Legacy fallback: context in process memory (single-worker)
                pending = task_manager.pop_pending_task(run_id)
                if pending is None:
                    logger.warning(f"No pending task found for queued run: {run_id}")
                    await self._release_active_slot_locked(user_id, run_id)
                    return
                executor_fn = pending["executor"]
                dispatch_user_id = user_id
                agent_id = pending["agent_id"]
                message = pending["message"]
                disabled_tools = pending.get("disabled_tools")
                agent_options = pending.get("agent_options")
                attachments = pending.get("attachments")
                disabled_skills = pending.get("disabled_skills")
                enabled_skills = pending.get("enabled_skills")
                persona_system_prompt = pending.get("persona_system_prompt")
                disabled_mcp_tools = pending.get("disabled_mcp_tools")
                team_id = pending.get("team_id")
                active_goal = pending.get("active_goal")

            try:
                from src.agents import ensure_agent_executable

                ensure_agent_executable(str(agent_id))
            except PluginUnavailableError as exc:
                logger.warning(
                    "Rejecting queued task for unavailable plugin-owned agent: run=%s, session=%s, agent=%s, plugin_id=%s",
                    run_id,
                    session_id,
                    agent_id,
                    exc.plugin_id,
                )
                executor = task_manager._ensure_executor()
                await executor._update_session_status(
                    session_id,
                    TaskStatus.FAILED,
                    str(exc) or "Plugin-owned agent is unavailable",
                    run_id=run_id,
                )
                await self._release_active_slot_locked(user_id, run_id)
                return

            if task_ctx and settings.TASK_BACKEND == "arq":
                await task_manager.submit_arq(
                    session_id=session_id,
                    agent_id=agent_id,
                    message=message,
                    user_id=dispatch_user_id,
                    executor_key=executor_key or "agent_stream",
                    disabled_tools=disabled_tools,
                    agent_options=agent_options,
                    attachments=attachments,
                    run_id=run_id,
                    disabled_skills=disabled_skills,
                    enabled_skills=enabled_skills,
                    persona_system_prompt=persona_system_prompt,
                    disabled_mcp_tools=disabled_mcp_tools,
                    display_message=task_ctx.get("display_message"),
                    recommendation_input=task_ctx.get("recommendation_input"),
                    trace_id=task_ctx.get("trace_id"),
                    user_message_written=task_ctx.get("user_message_written", False),
                    team_id=team_id,
                    active_goal=active_goal,
                )
                await self._send_queue_processing_event(session_id, run_id)
                return

            # --- Create and run the background task locally ---
            async with task_manager._lock:
                queued_executor = task_manager._executor
                if queued_executor is None:
                    logger.error("No executor available for queued task %s", run_id)
                    await self._release_active_slot_locked(user_id, run_id)
                    return

                # Ensure session record exists in MongoDB before executing
                await queued_executor.ensure_session(session_id, agent_id, dispatch_user_id)

                task = asyncio.create_task(
                    queued_executor.run_task(
                        session_id=session_id,
                        run_id=run_id,
                        agent_id=agent_id,
                        message=message,
                        user_id=dispatch_user_id,
                        executor=executor_fn,  # type: ignore[arg-type]
                        disabled_tools=disabled_tools,
                        agent_options=agent_options,
                        attachments=attachments,
                        existing_trace_id=task_ctx.get("trace_id") if task_ctx else None,
                        user_message_written=task_ctx.get("user_message_written", False)
                        if task_ctx
                        else False,
                        disabled_skills=disabled_skills,
                        enabled_skills=enabled_skills,
                        persona_system_prompt=persona_system_prompt,
                        disabled_mcp_tools=disabled_mcp_tools,
                        display_message=task_ctx.get("display_message") if task_ctx else None,
                        recommendation_input=task_ctx.get("recommendation_input")
                        if task_ctx
                        else None,
                        team_id=team_id,
                        active_goal=active_goal,
                    )
                )
                task_manager._tasks[run_id] = task
                task.add_done_callback(lambda t: task_manager._on_task_done(run_id, t))

            await self._send_queue_processing_event(session_id, run_id)

        except Exception as e:
            logger.error(f"Failed to dispatch queued task: {e}")
            await self._release_active_slot_locked(user_id, run_id)

    async def _send_queue_processing_event(self, session_id: str, run_id: str) -> None:
        """Send queue_update SSE event so frontend knows processing started."""
        try:
            from src.infra.session.dual_writer import get_dual_writer

            dual_writer = get_dual_writer()
            await dual_writer.write_event(
                session_id=session_id,
                event_type="queue_update",
                data={"status": "processing", "queue_position": 0},
                run_id=run_id,
            )
        except Exception as e:
            logger.warning(f"Failed to send queue_update event: {e}")

    async def get_queue_position(self, user_id: str, run_id: str) -> int:
        """Get current queue position for a run_id. Returns 0 if not in queue."""
        try:
            queue_key = self._queue_key(user_id)
            position = 0
            async for entry in self._iter_queue_entries(queue_key):
                position += 1
                data = await _queue_json_loads(entry)
                if data.get("run_id") == run_id:
                    return position
            return 0
        except Exception:
            return 0

    async def remove_from_queue(self, user_id: str, session_id: str) -> int:
        """Remove queued tasks matching session_id. Returns count removed."""
        try:
            lock_key, token = await self._acquire_user_lock(user_id)
            try:
                removed, removed_run_ids = await self._remove_from_queue_locked(
                    user_id,
                    session_id,
                )
            finally:
                await self._release_user_lock(lock_key, token)

            if removed:
                logger.info(f"Removed {removed} queued tasks for session {session_id}")
                # 更新 MongoDB session 状态
                try:
                    from src.infra.session.storage import SessionStorage
                    from src.infra.task.status import TaskStatus

                    storage = SessionStorage()
                    for run_id in removed_run_ids:
                        if run_id:
                            await storage.update(
                                session_id,
                                SessionUpdate(
                                    metadata={
                                        "task_status": TaskStatus.CANCELLED.value,
                                        "task_error": "Task cancelled by user",
                                        "task_error_code": "cancelled",
                                        "task_recoverable": False,
                                        "current_run_id": run_id,
                                    }
                                ),
                            )
                except Exception as e:
                    logger.warning(
                        f"Failed to update session status after removing from queue: {e}"
                    )
            return removed
        except Exception as e:
            logger.warning(f"Failed to remove from queue: {e}")
            return 0

    async def _remove_from_queue_locked(
        self, user_id: str, session_id: str
    ) -> tuple[int, list[Any]]:
        """Remove queued tasks while the caller holds the per-user lock."""
        tmp_key: str | None = None
        try:
            queue_key = self._queue_key(user_id)
            removed = 0
            removed_run_ids = []
            tmp_key = f"{queue_key}:rewrite:{uuid.uuid4().hex}"
            keep_buffer: list[str] = []
            wrote_keep_entries = False

            async def _flush_keep_buffer() -> None:
                nonlocal wrote_keep_entries
                if not keep_buffer:
                    return
                await self.redis.rpush(tmp_key, *keep_buffer)
                keep_buffer.clear()
                wrote_keep_entries = True

            async for entry in self._iter_queue_entries(queue_key):
                data = await _queue_json_loads(entry)
                if data.get("session_id") == session_id:
                    removed += 1
                    removed_run_ids.append(data.get("run_id"))
                else:
                    keep_buffer.append(entry)
                    if len(keep_buffer) >= QUEUE_REWRITE_CHUNK_SIZE:
                        await _flush_keep_buffer()
            if removed:
                await _flush_keep_buffer()
                if wrote_keep_entries:
                    await self.redis.rename(tmp_key, queue_key)
                    tmp_key = None
                else:
                    await self.redis.delete(queue_key)
                    tmp_key = None
            return removed, removed_run_ids
        except Exception:
            if tmp_key:
                try:
                    await self.redis.delete(tmp_key)
                except Exception:
                    pass
            raise


# Singleton
_limiter: Optional[UserConcurrencyLimiter] = None


def get_concurrency_limiter() -> UserConcurrencyLimiter:
    """Get singleton concurrency limiter."""
    global _limiter
    if _limiter is None:
        _limiter = UserConcurrencyLimiter()
    return _limiter

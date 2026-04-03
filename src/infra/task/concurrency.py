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
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from src.infra.session.storage import SessionUpdate
from src.infra.storage.redis import get_redis_client
from src.infra.task.constants import HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)

QUEUE_TIMEOUT = 300  # 5 minutes max wait in queue

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
            for role_name in roles:
                role = await role_storage.get_by_name(role_name)
                if role and role.limits:
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
            max_concurrent, max_queued = await self.get_user_limits(roles)

            # No limit configured — allow immediately
            if max_concurrent is None:
                return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

            # Cleanup stale entries first (crashed workers)
            await self._cleanup_stale_active(user_id)

            # Check current active count (only entries with recent heartbeats)
            active_count = await self._get_active_count(user_id)

            if active_count < max_concurrent:
                # Slot available — add to sorted set with current timestamp
                await self.redis.zadd(
                    self._active_key(user_id),
                    {run_id: time.time()},
                )
                return ConcurrencyResponse(
                    result=ConcurrencyResult.STARTED,
                    max_concurrent=max_concurrent,
                    active_count=active_count + 1,
                )

            # Active limit reached — try to queue
            if max_queued is not None:
                queue_length = await self.redis.llen(self._queue_key(user_id))
                if queue_length >= max_queued:
                    return ConcurrencyResponse(
                        result=ConcurrencyResult.REJECTED_QUEUE,
                        max_concurrent=max_concurrent,
                        active_count=active_count,
                        queue_length=queue_length,
                    )

            # Add to queue with full context and timestamp for timeout cleanup
            entry = json.dumps(
                {
                    "run_id": run_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "queued_at": time.time(),
                    "task_context": task_context or {},
                }
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
                max_concurrent=max_concurrent,
                active_count=active_count,
                queue_length=queue_length,
            )

        except Exception as e:
            logger.error(f"Concurrency limiter error (fail-open): {e}")
            return ConcurrencyResponse(result=ConcurrencyResult.STARTED)

    async def release(self, user_id: str, run_id: str) -> None:
        """Release a concurrency slot and trigger next queued task."""
        try:
            # Remove from active sorted set
            await self.redis.zrem(self._active_key(user_id), run_id)

            # Try to pop next task from queue
            await self._try_dequeue_next(user_id)

        except Exception as e:
            logger.error(f"Concurrency release error: {e}")

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

    async def _try_dequeue_next(self, user_id: str, depth: int = 0) -> None:
        """Try to dequeue next valid (non-expired) task from queue."""
        if depth >= 20:
            return
        try:
            queue_key = self._queue_key(user_id)
            entry = await self.redis.lpop(queue_key)
            if entry is None:
                return

            data = json.loads(entry)
            if time.time() - data.get("queued_at", 0) > QUEUE_TIMEOUT:
                logger.info(f"Discarding expired queued task: run={data.get('run_id')}")
                await self._try_dequeue_next(user_id, depth + 1)
                return

            run_id = data["run_id"]
            session_id = data["session_id"]

            # Check if we still have capacity (another release might have started one)
            max_concurrent, _ = await self.get_user_limits_from_cache(user_id)
            if max_concurrent is not None:
                await self._cleanup_stale_active(user_id)
                active_count = await self._get_active_count(user_id)
                if active_count >= max_concurrent:
                    # No slot available, put it back at the front
                    await self.redis.lpush(queue_key, entry)
                    return

            # Add to active set and dispatch
            await self.redis.zadd(self._active_key(user_id), {run_id: time.time()})
            logger.info(f"Task dequeued: user={user_id}, run={run_id}")
            await self._dispatch_queued_task(user_id, run_id, session_id, data)

        except Exception as e:
            logger.error(f"Dequeue error: {e}")

    async def get_user_limits_from_cache(self, user_id: str) -> Tuple[Optional[int], Optional[int]]:
        """Get limits (cache not implemented, delegates to get_user_limits with empty roles).

        Used internally when we don't have role info — falls back to defaults.
        """
        return 5, 10

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
            if task_ctx and task_ctx.get("executor_key"):
                # New format: context stored in Redis, executor resolved from registry
                executor_fn = get_registered_executor(task_ctx["executor_key"])
                if executor_fn is None:
                    logger.error(
                        f"No executor registered for key '{task_ctx['executor_key']}' "
                        f"(run={run_id})"
                    )
                    await self.release(user_id, run_id)
                    return
                dispatch_user_id = queue_data.get("user_id", user_id)
                agent_id = task_ctx["agent_id"]
                message = task_ctx["message"]
                disabled_tools = task_ctx.get("disabled_tools")
                agent_options = task_ctx.get("agent_options")
                attachments = task_ctx.get("attachments")
                disabled_skills = task_ctx.get("disabled_skills")
                disabled_mcp_tools = task_ctx.get("disabled_mcp_tools")
            else:
                # Legacy fallback: context in process memory (single-worker)
                pending = task_manager.pop_pending_task(run_id)
                if pending is None:
                    logger.warning(f"No pending task found for queued run: {run_id}")
                    await self.release(user_id, run_id)
                    return
                executor_fn = pending["executor"]
                dispatch_user_id = user_id
                agent_id = pending["agent_id"]
                message = pending["message"]
                disabled_tools = pending.get("disabled_tools")
                agent_options = pending.get("agent_options")
                attachments = pending.get("attachments")
                disabled_skills = pending.get("disabled_skills")
                disabled_mcp_tools = pending.get("disabled_mcp_tools")

            # --- Create and run the background task ---
            async with task_manager._lock:
                executor = task_manager._executor
                if executor is None:
                    logger.error("No executor available for queued task %s", run_id)
                    await self.release(user_id, run_id)
                    return

                # Ensure session record exists in MongoDB before executing
                await executor.ensure_session(session_id, agent_id, dispatch_user_id)

                task = asyncio.create_task(
                    executor.run_task(
                        session_id=session_id,
                        run_id=run_id,
                        agent_id=agent_id,
                        message=message,
                        user_id=dispatch_user_id,
                        executor=executor_fn,
                        disabled_tools=disabled_tools,
                        agent_options=agent_options,
                        attachments=attachments,
                        existing_trace_id=task_ctx.get("trace_id") if task_ctx else None,
                        user_message_written=task_ctx.get("user_message_written", False)
                        if task_ctx
                        else False,
                        disabled_skills=disabled_skills,
                        disabled_mcp_tools=disabled_mcp_tools,
                    )
                )
                task_manager._tasks[run_id] = task
                task.add_done_callback(lambda t: task_manager._on_task_done(run_id, t))

            # Send queue_update SSE event so frontend knows processing started
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

        except Exception as e:
            logger.error(f"Failed to dispatch queued task: {e}")
            await self.release(user_id, run_id)

    async def get_queue_position(self, user_id: str, run_id: str) -> int:
        """Get current queue position for a run_id. Returns 0 if not in queue."""
        try:
            entries = await self.redis.lrange(self._queue_key(user_id), 0, -1)
            for i, entry in enumerate(entries):
                data = json.loads(entry)
                if data.get("run_id") == run_id:
                    return i + 1
            return 0
        except Exception:
            return 0

    async def remove_from_queue(self, user_id: str, session_id: str) -> int:
        """Remove queued tasks matching session_id. Returns count removed."""
        try:
            queue_key = self._queue_key(user_id)
            entries = await self.redis.lrange(queue_key, 0, -1)
            to_keep = []
            removed = 0
            removed_run_ids = []
            for entry in entries:
                data = json.loads(entry)
                if data.get("session_id") == session_id:
                    removed += 1
                    removed_run_ids.append(data.get("run_id"))
                else:
                    to_keep.append(entry)
            if removed:
                await redis_delete_and_repush(self.redis, queue_key, to_keep)
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
                                        "task_status": TaskStatus.FAILED.value,
                                        "task_error": "Task cancelled by user",
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


async def redis_delete_and_repush(redis, key: str, entries: list[str]) -> None:
    """Delete a Redis list key and repopulate with filtered entries."""
    await redis.delete(key)
    if entries:
        await redis.rpush(key, *entries)


# Singleton
_limiter: Optional[UserConcurrencyLimiter] = None


def get_concurrency_limiter() -> UserConcurrencyLimiter:
    """Get singleton concurrency limiter."""
    global _limiter
    if _limiter is None:
        _limiter = UserConcurrencyLimiter()
    return _limiter

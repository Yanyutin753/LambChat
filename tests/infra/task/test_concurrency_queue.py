from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.task import concurrency
from src.infra.task.concurrency import ConcurrencyResult, UserConcurrencyLimiter
from src.infra.task.status import TaskStatus
from src.kernel.extensions import PluginRuntime, build_agent_team_plugin_manifest


class _PagedRedis:
    def __init__(self, entries: list[str]) -> None:
        self.entries = entries
        self.token: str | None = None
        self.events: list[str] = []
        self.lrange_calls: list[tuple[str, int, int]] = []
        self.deleted: list[str] = []
        self.pushed: list[tuple[str, tuple[str, ...]]] = []
        self.eval_calls: list[tuple[str, int, str, tuple[str, ...]]] = []
        self.renamed: list[tuple[str, str]] = []

    async def set(self, key: str, token: str, **kwargs):
        del key, kwargs
        self.token = token
        self.events.append("lock_acquired")
        return True

    async def get(self, key: str):
        del key
        return self.token

    async def lrange(self, key: str, start: int, end: int):
        self.lrange_calls.append((key, start, end))
        if end == -1:
            raise AssertionError("queue scan must not read the full list")
        return self.entries[start : end + 1]

    async def delete(self, key: str):
        self.deleted.append(key)
        if key.startswith("chat:lock:"):
            self.events.append("lock_released")

    async def rpush(self, key: str, *entries: str):
        self.pushed.append((key, entries))
        self.events.append("rpush")

    async def eval(self, script: str, numkeys: int, key: str, *entries: str):
        self.eval_calls.append((script, numkeys, key, entries))
        if key.startswith("chat:lock:"):
            self.events.append("lock_released")

    async def rename(self, source: str, target: str):
        self.renamed.append((source, target))
        self.events.append("rename")


class _DispatchRedis:
    def __init__(self, entry: str) -> None:
        self.entry = entry
        self.active: dict[str, float] = {}
        self.lock_attempted = False

    async def lpop(self, key: str):
        del key
        if self.entry is None:
            return None
        entry = self.entry
        self.entry = None
        return entry

    async def zadd(self, key: str, values: dict[str, float]):
        del key
        self.active.update(values)

    async def zrem(self, key: str, run_id: str):
        del key
        self.active.pop(run_id, None)

    async def set(self, *args, **kwargs):
        del args, kwargs
        self.lock_attempted = True
        raise AssertionError("dispatch failure while locked should not reacquire user lock")


class _LockOrderRedis:
    def __init__(self, entry: str) -> None:
        self.entry = entry
        self.token: str | None = None
        self.events: list[str] = []

    async def set(self, key: str, token: str, **kwargs):
        del key, kwargs
        self.token = token
        self.events.append("lock_acquired")
        return True

    async def get(self, key: str):
        del key
        return self.token

    async def delete(self, key: str):
        del key
        self.events.append("lock_released")

    async def eval(self, script: str, numkeys: int, key: str, token: str):
        del script, numkeys, key, token
        self.events.append("lock_released")

    async def zrem(self, key: str, run_id: str):
        del key, run_id

    async def lpop(self, key: str):
        del key
        if self.entry is None:
            return None
        entry = self.entry
        self.entry = None
        return entry

    async def zadd(self, key: str, values: dict[str, float]):
        del key, values


class _RaceLockRedis:
    def __init__(self) -> None:
        self.delete_calls: list[str] = []
        self.eval_calls: list[tuple[str, int, str, str]] = []

    async def get(self, key: str):
        del key
        return "old-token"

    async def delete(self, key: str):
        self.delete_calls.append(key)

    async def eval(self, script: str, numkeys: int, key: str, token: str):
        self.eval_calls.append((script, numkeys, key, token))
        return 0


class _QueueRedis:
    def __init__(self) -> None:
        self.pushed: list[tuple[str, tuple[str, ...]]] = []
        self.llen_calls: list[str] = []

    async def llen(self, key: str) -> int:
        self.llen_calls.append(key)
        return 0

    async def rpush(self, key: str, *entries: str) -> None:
        self.pushed.append((key, entries))


class _CorruptQueueRedis:
    def __init__(self, entries: list[str]) -> None:
        self.entries = list(entries)
        self.active: dict[str, float] = {}

    async def lpop(self, key: str):
        del key
        if not self.entries:
            return None
        return self.entries.pop(0)

    async def zadd(self, key: str, values: dict[str, float]):
        del key
        self.active.update(values)


@pytest.mark.asyncio
async def test_get_queue_position_scans_queue_in_pages() -> None:
    entries = [
        json.dumps({"run_id": f"run-{index}", "session_id": f"session-{index}"})
        for index in range(5)
    ]
    redis = _PagedRedis(entries)
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    position = await limiter.get_queue_position("user-1", "run-3")

    assert position == 4
    assert redis.lrange_calls == [
        ("chat:queue:user-1", 0, 99),
    ]


@pytest.mark.asyncio
async def test_remove_from_queue_scans_queue_in_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        json.dumps({"run_id": "run-1", "session_id": "keep"}),
        json.dumps({"run_id": "run-2", "session_id": "remove"}),
        json.dumps({"run_id": "run-3", "session_id": "keep"}),
    ]
    redis = _PagedRedis(entries)
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    class _FakeSessionStorage:
        def __init__(self) -> None:
            self.updates = []

        async def update(self, session_id, update):
            self.updates.append((session_id, update))

    fake_storage = _FakeSessionStorage()
    monkeypatch.setattr(
        "src.infra.session.storage.SessionStorage",
        lambda: fake_storage,
    )

    removed = await limiter.remove_from_queue("user-1", "remove")

    assert removed == 1
    assert redis.lrange_calls == [("chat:queue:user-1", 0, 99)]
    assert "chat:queue:user-1" not in redis.deleted
    assert len(redis.eval_calls) == 1
    assert redis.eval_calls[0][2] == "chat:lock:user-1"
    assert len(redis.pushed) == 1
    tmp_key, kept_entries = redis.pushed[0]
    assert kept_entries == (entries[0], entries[2])
    assert redis.renamed == [(tmp_key, "chat:queue:user-1")]
    assert redis.events == ["lock_acquired", "rpush", "rename", "lock_released"]
    assert fake_storage.updates[0][0] == "remove"


@pytest.mark.asyncio
async def test_remove_from_queue_rewrites_kept_entries_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(concurrency, "QUEUE_REWRITE_CHUNK_SIZE", 2, raising=False)
    entries = [json.dumps({"run_id": f"run-{index}", "session_id": "keep"}) for index in range(5)]
    entries.insert(2, json.dumps({"run_id": "run-remove", "session_id": "remove"}))
    redis = _PagedRedis(entries)
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    class _FakeSessionStorage:
        async def update(self, session_id, update):
            del session_id, update

    monkeypatch.setattr(
        "src.infra.session.storage.SessionStorage",
        lambda: _FakeSessionStorage(),
    )

    removed = await limiter.remove_from_queue("user-1", "remove")

    assert removed == 1
    assert len(redis.eval_calls) == 1
    assert redis.eval_calls[0][2] == "chat:lock:user-1"
    assert [len(batch) for _, batch in redis.pushed] == [2, 2, 1]
    tmp_keys = {key for key, _ in redis.pushed}
    assert len(tmp_keys) == 1
    tmp_key = next(iter(tmp_keys))
    assert redis.renamed == [(tmp_key, "chat:queue:user-1")]
    assert redis.events == [
        "lock_acquired",
        "rpush",
        "rpush",
        "rpush",
        "rename",
        "lock_released",
    ]


@pytest.mark.asyncio
async def test_locked_dequeue_dispatch_failure_releases_slot_without_reacquiring_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    entry = json.dumps(
        {
            "run_id": "run-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "queued_at": 9_999_999_999,
            "task_context": {
                "executor_key": "missing",
                "agent_id": "default",
                "message": "hello",
            },
        }
    )
    redis = _DispatchRedis(entry)
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    await limiter._try_dequeue_next_locked("user-1")

    assert redis.lock_attempted is False
    assert redis.active == {}


@pytest.mark.asyncio
async def test_release_dispatches_queued_task_after_releasing_user_lock() -> None:
    entry = json.dumps(
        {
            "run_id": "queued-run",
            "session_id": "session-1",
            "user_id": "user-1",
            "queued_at": 9_999_999_999,
            "task_context": {
                "executor_key": "registered",
                "agent_id": "default",
                "message": "hello",
            },
        }
    )
    redis = _LockOrderRedis(entry)

    class _Limiter(UserConcurrencyLimiter):
        async def get_user_limits_from_cache(self, user_id: str):
            del user_id
            return None, None

        async def _dispatch_queued_task(
            self,
            user_id: str,
            run_id: str,
            session_id: str,
            queue_data: dict,
        ) -> None:
            del user_id, run_id, session_id, queue_data
            redis.events.append("dispatch")

    limiter = _Limiter()
    limiter._redis = redis

    await limiter.release("user-1", "finished-run")

    assert redis.events == ["lock_acquired", "lock_released", "dispatch"]


@pytest.mark.asyncio
async def test_release_user_lock_uses_atomic_compare_delete() -> None:
    redis = _RaceLockRedis()
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    await limiter._release_user_lock("chat:lock:user-1", "old-token")

    assert redis.delete_calls == []
    assert redis.eval_calls
    assert redis.eval_calls[0][1:] == (1, "chat:lock:user-1", "old-token")


@pytest.mark.asyncio
async def test_dequeue_skips_corrupt_queue_entries_and_continues() -> None:
    valid_entry = json.dumps(
        {
            "run_id": "valid-run",
            "session_id": "session-1",
            "user_id": "user-1",
            "queued_at": 9_999_999_999,
            "task_context": {
                "executor_key": "registered",
                "agent_id": "default",
                "message": "hello",
            },
        }
    )
    redis = _CorruptQueueRedis(["{not-json", valid_entry])

    class _Limiter(UserConcurrencyLimiter):
        def __init__(self) -> None:
            super().__init__()
            self.dispatched: list[str] = []

        async def get_user_limits_from_cache(self, user_id: str):
            del user_id
            return None, None

        async def _dispatch_queued_task(
            self,
            user_id: str,
            run_id: str,
            session_id: str,
            queue_data: dict,
        ) -> None:
            del user_id, session_id, queue_data
            self.dispatched.append(run_id)

    limiter = _Limiter()
    limiter._redis = redis

    await limiter._try_dequeue_next_locked("user-1")

    assert limiter.dispatched == ["valid-run"]
    assert redis.active == {"valid-run": pytest.approx(redis.active["valid-run"])}


@pytest.mark.asyncio
async def test_queue_task_rejects_oversized_context_before_redis_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(concurrency, "QUEUE_ENTRY_MAX_BYTES", 64, raising=False)
    redis = _QueueRedis()
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    response = await limiter._queue_task_locked(
        user_id="user-1",
        run_id="run-1",
        session_id="session-1",
        task_context={"executor_key": "agent_stream", "message": "x" * 128},
        max_concurrent=1,
        active_count=1,
        max_queued=None,
    )

    assert response.result == ConcurrencyResult.REJECTED_QUEUE
    assert redis.pushed == []


@pytest.mark.asyncio
async def test_queue_task_offloads_queue_entry_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _QueueRedis()
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(concurrency, "run_blocking_io", _fake_run_blocking_io, raising=False)

    response = await limiter._queue_task_locked(
        user_id="user-1",
        run_id="run-1",
        session_id="session-1",
        task_context={"executor_key": "agent_stream", "message": "x" * 20_000},
        max_concurrent=1,
        active_count=1,
        max_queued=None,
    )

    assert response.result == ConcurrencyResult.QUEUED
    assert calls == [json.dumps]
    assert redis.pushed


@pytest.mark.asyncio
async def test_dequeue_offloads_queue_entry_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    entry = json.dumps(
        {
            "run_id": "queued-run",
            "session_id": "session-1",
            "user_id": "user-1",
            "queued_at": 9_999_999_999,
            "task_context": {"executor_key": "registered", "message": "x" * 20_000},
        }
    )
    redis = _DispatchRedis(entry)

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    class _Limiter(UserConcurrencyLimiter):
        def __init__(self) -> None:
            super().__init__()
            self.dispatched: list[str] = []

        async def get_user_limits_from_cache(self, user_id: str):
            del user_id
            return None, None

        async def _dispatch_queued_task(
            self,
            user_id: str,
            run_id: str,
            session_id: str,
            queue_data: dict,
        ) -> None:
            del user_id, session_id, queue_data
            self.dispatched.append(run_id)

    monkeypatch.setattr(concurrency, "run_blocking_io", _fake_run_blocking_io, raising=False)
    limiter = _Limiter()
    limiter._redis = redis

    await limiter._try_dequeue_next_locked("user-1")

    assert calls == [json.loads]
    assert limiter.dispatched == ["queued-run"]


@pytest.mark.asyncio
async def test_dispatch_queued_task_uses_arq_backend_without_local_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arq_calls: list[dict[str, Any]] = []
    local_submit_calls: list[dict[str, Any]] = []

    class _FakeTaskManager:
        _executor = object()
        _lock = None

        async def submit_arq(self, **kwargs):
            arq_calls.append(kwargs)
            return kwargs["run_id"], kwargs.get("trace_id") or ""

        async def submit(self, **kwargs):
            local_submit_calls.append(kwargs)
            return kwargs["run_id"], kwargs.get("trace_id") or ""

    async def _fake_executor(*args, **kwargs):
        del args, kwargs
        if False:
            yield None

    created_tasks: list[Any] = []

    def _fail_create_task(coro):
        created_tasks.append(coro)
        raise AssertionError("arq queued dispatch must not create a local asyncio task")

    limiter = UserConcurrencyLimiter()
    limiter._redis = _DispatchRedis("{}")
    queue_data = {
        "run_id": "queued-run",
        "session_id": "session-1",
        "user_id": "user-1",
        "task_context": {
            "executor_key": "agent_stream",
            "agent_id": "default",
            "message": "hello",
            "display_message": "hello visible",
            "disabled_tools": ["shell"],
            "agent_options": {"model": "test-model"},
            "attachments": [{"name": "a.txt"}],
            "trace_id": "trace-1",
            "user_message_written": True,
            "disabled_skills": ["skill-a"],
            "enabled_skills": ["skill-b"],
            "persona_system_prompt": "persona",
            "disabled_mcp_tools": ["mcp.tool"],
            "team_id": "team-1",
            "active_goal": {"objective": "ship it"},
            "recommendation_input": "hello",
        },
    }

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "arq")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(concurrency, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(concurrency.asyncio, "create_task", _fail_create_task)

    await limiter._dispatch_queued_task("user-1", "queued-run", "session-1", queue_data)

    assert local_submit_calls == []
    assert created_tasks == []
    assert len(arq_calls) == 1
    call = arq_calls[0]
    assert call["session_id"] == "session-1"
    assert call["run_id"] == "queued-run"
    assert call["executor_key"] == "agent_stream"
    assert call["trace_id"] == "trace-1"
    assert call["user_message_written"] is True
    assert call["display_message"] == "hello visible"
    assert call["recommendation_input"] == "hello"
    assert call["active_goal"] == {"objective": "ship it"}


@pytest.mark.asyncio
async def test_dispatch_queued_task_rejects_disabled_plugin_owned_agent_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    class _FakeExecutor:
        def __init__(self) -> None:
            self.ensure_calls: list[tuple] = []
            self.status_calls: list[tuple] = []

        async def ensure_session(self, *args, **kwargs) -> None:
            self.ensure_calls.append((args, kwargs))

        async def _update_session_status(self, *args, **kwargs) -> None:
            self.status_calls.append((args, kwargs))

        async def run_task(self, *args, **kwargs) -> None:
            raise AssertionError("disabled plugin-owned queued task should not run")

    class _FakeTaskManager:
        def __init__(self) -> None:
            self._executor = _FakeExecutor()
            self._lock = None
            self._tasks = {}

        def _ensure_executor(self):
            return self._executor

        async def submit_arq(self, **kwargs):
            raise AssertionError("disabled plugin-owned queued task should not submit to arq")

        def pop_pending_task(self, run_id: str):
            raise AssertionError("redis-backed queued task should not use memory fallback")

    async def _fake_executor_fn(*args, **kwargs):
        raise AssertionError("disabled plugin-owned queued task should not call executor fn")
        if False:
            yield None

    redis = _DispatchRedis("{}")
    redis.active = {"queued-run": 9_999_999_999}
    limiter = UserConcurrencyLimiter()
    limiter._redis = redis
    task_manager = _FakeTaskManager()
    queue_data = {
        "run_id": "queued-run",
        "session_id": "session-1",
        "user_id": "user-1",
        "task_context": {
            "executor_key": "agent_stream",
            "agent_id": "team",
            "message": "hello",
        },
    }
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: task_manager)
    monkeypatch.setattr(concurrency, "get_registered_executor", lambda key: _fake_executor_fn)
    set_plugin_runtime(runtime)

    try:
        await limiter._dispatch_queued_task("user-1", "queued-run", "session-1", queue_data)
    finally:
        set_plugin_runtime(None)

    assert task_manager._executor.ensure_calls == []
    assert task_manager._tasks == {}
    assert task_manager._executor.status_calls
    args, kwargs = task_manager._executor.status_calls[0]
    assert args[0] == "session-1"
    assert args[1] is TaskStatus.FAILED
    assert "agent_team" in args[2]
    assert kwargs == {"run_id": "queued-run"}
    assert redis.active == {}

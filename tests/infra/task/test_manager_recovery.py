from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.manager import BackgroundTaskManager


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, object]] = []
        self.collection = None

    async def get_by_session_id(self, session_id: str):
        if self.session and self.session.id == session_id:
            return self.session
        return None

    async def get_by_id(self, session_id: str):
        if self.session and self.session.id == session_id:
            return self.session
        return None

    async def update(self, session_id: str, session_update) -> None:
        self.updates.append((session_id, session_update))


class _FakeCancellation:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def cancel_run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FakeHeartbeat:
    def __init__(self, exists: bool = False) -> None:
        self.exists = exists

    async def check_exists(self, run_id: str) -> bool:
        return self.exists

    async def is_stale(self, run_id: str) -> bool:
        return not self.exists


@pytest.mark.asyncio
async def test_cancel_session_persists_cancelled_status_without_local_run_info() -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={
            "current_run_id": "run-old",
            "task_status": "running",
            "agent_id": "search",
            "trace_id": "trace-1",
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._cancellation = _FakeCancellation(
        {
            "success": True,
            "cancelled_locally": False,
            "run_id": "run-old",
            "message": "取消信号已发送，任务将在下次检查点中断",
        }
    )

    result = await manager.cancel("session-1", user_id="user-1")

    assert result["success"] is True
    assert manager._cancellation.calls == [
        {
            "run_id": "run-old",
            "publish": True,
            "user_id": "user-1",
            "run_info": {
                "session_id": "session-1",
                "trace_id": "trace-1",
                "agent_id": "search",
                "user_id": "user-1",
            },
        }
    ]
    assert storage.updates
    metadata = storage.updates[-1][1].metadata
    assert metadata["task_status"] == "cancelled"
    assert metadata["task_error_code"] == "cancelled"
    assert metadata["task_recoverable"] is False
    assert metadata["current_run_id"] == "run-old"


class _FakeRedis:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.set_calls: list[tuple[str, str, int, bool]] = []
        self.deleted_keys: list[str] = []
        self.eval_calls: list[tuple[str, int, str, str]] = []

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.set_calls.append((key, value, ex or 0, nx))
        return self.acquired

    async def delete(self, key: str):
        self.deleted_keys.append(key)
        return 1

    async def eval(self, script: str, numkeys: int, key: str, token: str):
        self.eval_calls.append((script, numkeys, key, token))
        return 1


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs
        self.sort_args = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    async def to_list(self, length: int):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs_per_call):
        self._docs_per_call = list(docs_per_call)
        self.calls = 0
        self.find_calls: list[tuple[tuple, dict]] = []

    def find(self, *args, **kwargs):
        self.find_calls.append((args, kwargs))
        docs = self._docs_per_call[self.calls]
        self.calls += 1
        return _FakeCursor(docs)


@pytest.mark.asyncio
async def test_cancel_session_looks_up_trace_id_when_session_metadata_lacks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={
            "current_run_id": "run-old",
            "task_status": "running",
            "agent_id": "search",
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._cancellation = _FakeCancellation(
        {
            "success": True,
            "cancelled_locally": False,
            "run_id": "run-old",
            "message": "取消信号已发送，任务将在下次检查点中断",
        }
    )
    trace_collection = _FakeCollection([[{"trace_id": "trace-from-store"}]])

    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: SimpleNamespace(collection=trace_collection),
    )

    result = await manager.cancel("session-1", user_id="user-1")

    assert result["success"] is True
    assert manager._cancellation.calls[0]["run_info"]["trace_id"] == "trace-from-store"
    assert trace_collection.find_calls == [(({"run_id": "run-old"}, {"trace_id": 1, "_id": 0}), {})]


@pytest.mark.asyncio
async def test_resume_session_submits_localized_recovery_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Recovery Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "agent_id": "search",
            "executor_key": "agent_stream",
            "agent_options": {"model": "gpt-test"},
            "disabled_tools": ["bash"],
            "disabled_skills": ["demo-skill"],
            "disabled_mcp_tools": ["mcp.tool"],
            "project_id": "project-1",
            "team_id": "team-1",
            "auto_mode": True,
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    redis = _FakeRedis(acquired=True)
    submit_calls = []

    async def _fake_submit(*args, **kwargs):
        submit_calls.append({"args": args, **kwargs})
        return kwargs["run_id"], ""

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        raise AssertionError("seamless resume must not mark the run failed")

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return SimpleNamespace(metadata={"language": "zh-CN"})

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _FakeLimiter:
        async def try_acquire_run_slot(self, user_id: str, run_id: str) -> bool:
            return True

        async def release(self, *args, **kwargs):
            return None

    class _EmptyTraceCursor:
        def sort(self, key, direction=None):
            return self

        def limit(self, limit):
            return self

        async def to_list(self, length=None):
            return []

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(
        recovery_module,
        "get_trace_storage",
        lambda: SimpleNamespace(collection=SimpleNamespace(find=lambda q, p=None: _EmptyTraceCursor())),
    )
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr(manager, "submit", _fake_submit)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager.resume_session("session-1")

    assert result["success"] is True
    assert result["run_id"] == "run-old"
    assert result["resumed_from_run_id"] == "run-old"
    assert len(submit_calls) == 1
    call = submit_calls[0]
    assert call["args"][0] == "session-1"
    assert call["args"][2] == "请继续处理当前会话中未完成的内容。"
    assert call["project_id"] == "project-1"
    assert call["disabled_tools"] == ["bash"]
    assert call["auto_mode"] is True
    # 无缝续跑契约：复用原 run_id、不写新用户消息事件、带 resume 标记
    assert call["run_id"] == "run-old"
    assert call["user_message_written"] is True
    assert call["interrupted_resume"] is True
    assert redis.set_calls
    assert storage.updates[-1][0] == "session-1"
    assert storage.updates[-1][1].metadata["resume_attempts"] == 1


@pytest.mark.asyncio
async def test_resume_session_uses_arq_submission_when_task_backend_is_arq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Arq Recovery Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "agent_id": "search",
            "executor_key": "agent_stream",
            "agent_options": {"model": "gpt-test"},
            "disabled_tools": ["bash"],
            "project_id": "project-1",
            "auto_mode": True,
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    redis = _FakeRedis(acquired=True)
    local_submit_calls = []
    arq_submit_calls = []

    async def _fake_submit_arq(**kwargs):
        arq_submit_calls.append(kwargs)
        return kwargs["run_id"], kwargs.get("trace_id") or ""

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        raise AssertionError("seamless resume must not mark the run failed")

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=["admin"])

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _TraceCursor:
        def sort(self, key, direction=None):
            return self

        def limit(self, limit):
            return self

        async def to_list(self, length=None):
            return [{"trace_id": "trace-old"}]

    class _FakeTraceStorage:
        reopened: list[str] = []

        collection = SimpleNamespace(find=lambda q, p=None: _TraceCursor())

        async def reopen_interrupted_trace(self, trace_id: str) -> bool:
            self.reopened.append(trace_id)
            return True

    trace_storage = _FakeTraceStorage()

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_trace_storage", lambda: trace_storage)
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "arq")
    monkeypatch.setattr(manager, "submit_arq", _fake_submit_arq)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager.resume_session("session-1")

    assert result["success"] is True
    assert result["run_id"] == "run-old"
    assert local_submit_calls == []
    assert len(arq_submit_calls) == 1
    call = arq_submit_calls[0]
    assert call["executor_key"] == "agent_stream"
    assert call["run_id"] == "run-old"
    assert call["trace_id"] == "trace-old"
    assert call["auto_mode"] is True
    assert call["user_message_written"] is True
    assert call["interrupted_resume"] is True
    assert call["initial_status"].value == "pending"
    assert call["dispatch_id"].startswith("resume:run-old:")
    assert call["message"] == "请继续处理当前会话中未完成的内容。"
    assert trace_storage.reopened == ["trace-old"]


@pytest.mark.asyncio
async def test_seamless_resume_falls_back_from_legacy_default_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    class _SearchAgentClass:
        _agent_name = "Search"

    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="default",
        name="Legacy Default Agent Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "agent_id": "default",
            "executor_key": "agent_stream",
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage

    submit_calls = []

    async def _fake_submit(*args, **kwargs):
        submit_calls.append({"args": args, **kwargs})
        return kwargs["run_id"], kwargs.get("trace_id") or ""

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _FakeLimiter:
        async def try_acquire_run_slot(self, user_id: str, run_id: str) -> bool:
            return True

        async def release(self, *args, **kwargs):
            return None

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=[])

    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"search": _SearchAgentClass})
    monkeypatch.setattr("src.kernel.config.settings.DEFAULT_AGENT", "fast")  # fast not in registry
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(
        recovery_module,
        "get_trace_storage",
        lambda: SimpleNamespace(
            collection=SimpleNamespace(find=lambda q, p=None: _EmptyTraceCursorStub())
        ),
    )
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")

    service = recovery_module.TaskRecoveryService(
        storage=storage,
        run_info=manager._run_info,
        heartbeat=SimpleNamespace(check_exists=lambda run_id: False, is_stale=_always_stale),
        ensure_executor=lambda: SimpleNamespace(),
        submit_task=_fake_submit,
        mark_run_failed=_stub_noop,
    )
    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: _FakeRedis(acquired=True))

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is True
    assert submit_calls[0]["args"][1] == "search"


class _EmptyTraceCursorStub:
    def sort(self, key, direction=None):
        return self

    def limit(self, limit):
        return self

    async def to_list(self, length=None):
        return []


async def _stub_noop(*_args, **_kwargs):
    return None


async def _always_stale(_run_id: str) -> bool:
    return True


@pytest.mark.asyncio
async def test_resume_session_rejects_user_cancelled_tasks() -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Cancelled Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "task_error_code": "cancelled",
            "task_recoverable": False,
        },
    )
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage(session)
    manager._heartbeat = _FakeHeartbeat(exists=False)

    result = await manager.resume_session("session-1")

    assert result["success"] is False
    assert result["message"] == "该任务已被用户取消，不能恢复"


@pytest.mark.asyncio
async def test_cleanup_stale_tasks_recovers_latest_running_session_without_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Auto Recovery Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "running",
        },
    )
    manager = BackgroundTaskManager()
    storage = _FakeStorage(session)
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {"current_run_id": "run-old"},
                }
            ],
            [],
            [],
        ]
    )
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    recovery_calls = []

    async def _fake_resume_interrupted_run(session, source_run_id: str, reason: str):
        recovery_calls.append((session.id, source_run_id, reason))
        return {"success": True, "run_id": "run-new", "message": "ok"}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str) -> None:
            self.release_calls.append((user_id, run_id))

    fake_limiter = _FakeLimiter()

    monkeypatch.setattr(manager, "_resume_interrupted_run", _fake_resume_interrupted_run)
    monkeypatch.setattr(manager, "_replay_pending_queued_tasks", _no_op)
    monkeypatch.setattr(manager, "_cleanup_stale_queues", _no_op)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    await manager.cleanup_stale_tasks()

    assert recovery_calls == [("session-1", "run-old", "server_restart")]
    assert fake_limiter.release_calls == []


@pytest.mark.asyncio
async def test_cleanup_stale_tasks_attempts_auto_recovery_for_failed_recoverable_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Recoverable Failed Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
        },
    )
    manager = BackgroundTaskManager()
    storage = _FakeStorage(session)
    storage.collection = _FakeCollection(
        [
            [],
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {
                        "current_run_id": "run-old",
                        "task_recoverable": True,
                        "task_error_code": "server_restart",
                    },
                }
            ],
            [],
        ]
    )
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    recovery_calls = []

    async def _fake_resume_interrupted_run(session, source_run_id: str, reason: str):
        recovery_calls.append((session.id, source_run_id, reason))
        return {"success": True, "run_id": "run-new", "message": "ok"}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str) -> None:
            self.release_calls.append((user_id, run_id))

    fake_limiter = _FakeLimiter()

    monkeypatch.setattr(manager, "_resume_interrupted_run", _fake_resume_interrupted_run)
    monkeypatch.setattr(manager, "_replay_pending_queued_tasks", _no_op)
    monkeypatch.setattr(manager, "_cleanup_stale_queues", _no_op)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    await manager.cleanup_stale_tasks()

    assert recovery_calls == [("session-1", "run-old", "server_restart")]
    assert fake_limiter.release_calls == []


@pytest.mark.asyncio
async def test_resume_interrupted_run_releases_lock_after_failed_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={"current_run_id": "run-old"},
    )
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage(session)

    redis = _FakeRedis(acquired=True)

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        return None

    async def _fake_submit_seamless_resume(self, *args, **kwargs):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(
        recovery_module.TaskRecoveryService,
        "submit_seamless_resume",
        _fake_submit_seamless_resume,
    )

    result = await manager._resume_interrupted_run(session, "run-old", "manual_resume")

    assert result["success"] is False
    assert redis.deleted_keys == []
    assert redis.eval_calls
    assert redis.eval_calls[0][1:] == (
        1,
        "task:recovery:session-1:run-old",
        redis.set_calls[0][1],
    )


@pytest.mark.asyncio
async def test_resume_interrupted_run_releases_lock_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={"current_run_id": "run-old"},
    )
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage(session)

    manager._heartbeat = _FakeHeartbeat(exists=False)
    redis = _FakeRedis(acquired=True)
    lookup_started = asyncio.Event()

    async def _blocking_lookup(run_id: str):
        lookup_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "_lookup_trace_id_for_run", _blocking_lookup)

    task = asyncio.create_task(manager._resume_interrupted_run(session, "run-old", "manual_resume"))
    await asyncio.wait_for(lookup_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert redis.eval_calls
    assert redis.eval_calls[0][1:] == (
        1,
        "task:recovery:session-1:run-old",
        redis.set_calls[0][1],
    )


@pytest.mark.asyncio
async def test_resume_interrupted_run_skips_when_recovery_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={"current_run_id": "run-old"},
    )
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage(session)

    redis = _FakeRedis(acquired=False)
    mark_failed_calls = []
    submit_calls = []

    async def _fake_mark_failed(*args, **kwargs):
        mark_failed_calls.append((args, kwargs))

    async def _fake_submit_seamless_resume(*args, **kwargs):
        submit_calls.append((args, kwargs))
        return {"success": True}

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(
        recovery_module.TaskRecoveryService,
        "submit_seamless_resume",
        _fake_submit_seamless_resume,
    )

    result = await manager._resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert "已在其他实例中启动" in result["message"]
    assert mark_failed_calls == []
    assert submit_calls == []
    assert len(redis.set_calls) == 1
    assert redis.set_calls[0][0] == "task:recovery:session-1:run-old"
    assert redis.set_calls[0][2:] == (300, True)


@pytest.mark.asyncio
async def test_resume_interrupted_run_restores_recoverable_failure_when_submission_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={"current_run_id": "run-old"},
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    redis = _FakeRedis(acquired=True)
    recoverable_failures = []

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        recoverable_failures.append((run_id, reason, loaded_session.id))

    async def _fake_submit_seamless_resume(*args, **kwargs):
        return {"success": False, "message": "当前并发任务已满，稍后将自动重试恢复"}

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(
        recovery_module.TaskRecoveryService,
        "submit_seamless_resume",
        _fake_submit_seamless_resume,
    )

    result = await manager._resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    # 无缝恢复失败不 mark_run_failed（trace 保持可续跑），只恢复 recoverable 元数据
    assert recoverable_failures == []
    assert storage.updates[-1][0] == "session-1"
    assert storage.updates[-1][1].metadata["task_status"] == "failed"
    assert storage.updates[-1][1].metadata["task_recoverable"] is True
    assert storage.updates[-1][1].metadata["task_error_code"] == "server_restart"
    assert redis.eval_calls
    assert redis.eval_calls[0][1:] == (
        1,
        "task:recovery:session-1:run-old",
        redis.set_calls[0][1],
    )


@pytest.mark.asyncio
async def test_resume_interrupted_run_skips_when_session_already_points_to_new_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={"current_run_id": "run-new"},
    )
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage(session)

    redis = _FakeRedis(acquired=True)
    mark_failed_calls = []

    async def _fake_mark_failed(*args, **kwargs):
        mark_failed_calls.append((args, kwargs))

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager._resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert "已由其他恢复流程接管" in result["message"]
    assert mark_failed_calls == []
    assert redis.deleted_keys == []
    assert redis.eval_calls
    assert redis.eval_calls[0][1:] == (
        1,
        "task:recovery:session-1:run-old",
        redis.set_calls[0][1],
    )


@pytest.mark.asyncio
async def test_manager_release_recovery_lock_forwards_lock_token() -> None:
    manager = BackgroundTaskManager()
    calls: list[tuple[str, str]] = []

    class _FakeRecoveryService:
        async def release_recovery_lock(self, lock_key: str, token: str) -> None:
            calls.append((lock_key, token))

    manager._recovery_service = lambda: _FakeRecoveryService()  # type: ignore[method-assign]

    await manager._release_recovery_lock("task:recovery:session-1:run-old", "token-1")

    assert calls == [("task:recovery:session-1:run-old", "token-1")]


@pytest.mark.asyncio
async def test_shutdown_releases_active_slot_without_dequeuing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    manager._tasks = {"run-old": SimpleNamespace(done=lambda: False, cancel=lambda: None)}
    manager._run_info = {
        "run-old": {
            "session_id": "session-1",
            "user_id": "user-1",
        }
    }

    async def _fake_stop_all() -> None:
        return None

    mark_calls = []

    async def _fake_mark_run_recoverable_failure(session_id: str, run_id: str, error_message: str):
        mark_calls.append((session_id, run_id, error_message))

    class _FakeLimiter:
        def __init__(self) -> None:
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()

    monkeypatch.setattr(manager._heartbeat, "stop_all", _fake_stop_all)
    monkeypatch.setattr(
        manager, "_mark_run_recoverable_failure", _fake_mark_run_recoverable_failure
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    await manager.shutdown()

    assert mark_calls == [("session-1", "run-old", "Server shutdown")]
    assert fake_limiter.release_calls == [("user-1", "run-old", False)]


@pytest.mark.asyncio
async def test_shutdown_limits_parallel_task_recovery_and_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    manager._tasks = {
        f"run-{index}": SimpleNamespace(done=lambda: False, cancel=lambda: None)
        for index in range(5)
    }
    manager._run_info = {
        f"run-{index}": {
            "session_id": f"session-{index}",
            "user_id": "user-1",
        }
        for index in range(5)
    }
    active = 0
    max_active = 0
    release_calls: list[tuple[str, str, bool]] = []
    mark_calls: list[tuple[str, str, str]] = []

    async def _track_work() -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1

    async def _fake_stop_all() -> None:
        return None

    async def _fake_mark_run_recoverable_failure(
        session_id: str,
        run_id: str,
        error_message: str,
    ) -> None:
        await _track_work()
        mark_calls.append((session_id, run_id, error_message))

    class _FakeLimiter:
        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            await _track_work()
            release_calls.append((user_id, run_id, dequeue))

    monkeypatch.setattr(manager._heartbeat, "stop_all", _fake_stop_all)
    monkeypatch.setattr(
        manager, "_mark_run_recoverable_failure", _fake_mark_run_recoverable_failure
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )
    monkeypatch.setattr(
        "src.infra.task.startup_cleanup.settings.TASK_STARTUP_CLEANUP_CONCURRENCY", 2
    )

    await manager.shutdown()

    assert max_active == 2
    assert len(mark_calls) == 5
    assert len(release_calls) == 5
    assert manager._tasks == {}
    assert manager._run_info == {}


@pytest.mark.asyncio
async def test_shutdown_awaits_cancelled_tasks_to_finish_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    cleanup_finished = False
    started = asyncio.Event()

    async def _long_running_task() -> None:
        nonlocal cleanup_finished
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await allow_cleanup.wait()
            cleanup_finished = True

    task = asyncio.create_task(_long_running_task())
    await started.wait()
    manager._tasks = {"run-old": task}
    manager._run_info = {
        "run-old": {
            "session_id": "session-1",
            "user_id": "user-1",
        }
    }

    async def _fake_stop_all() -> None:
        return None

    async def _fake_mark_run_recoverable_failure(
        session_id: str,
        run_id: str,
        error_message: str,
    ) -> None:
        del session_id, run_id, error_message

    class _FakeLimiter:
        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            del user_id, run_id, dequeue

    monkeypatch.setattr(manager._heartbeat, "stop_all", _fake_stop_all)
    monkeypatch.setattr(
        manager, "_mark_run_recoverable_failure", _fake_mark_run_recoverable_failure
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )

    shutdown_task = asyncio.create_task(manager.shutdown())
    await cleanup_started.wait()
    await asyncio.sleep(0)

    assert shutdown_task.done() is False
    assert cleanup_finished is False

    allow_cleanup.set()
    await shutdown_task
    assert task.done()
    assert cleanup_finished is True



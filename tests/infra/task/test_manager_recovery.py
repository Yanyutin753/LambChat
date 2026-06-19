from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.manager import BackgroundTaskManager
from src.kernel.extensions import PluginRuntime, build_agent_team_plugin_manifest


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
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    redis = _FakeRedis(acquired=True)
    submit_calls = []

    async def _fake_submit(**kwargs):
        submit_calls.append(kwargs)
        return kwargs["run_id"], ""

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        assert run_id == "run-old"
        assert loaded_session.id == "session-1"

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return SimpleNamespace(metadata={"language": "zh-CN"})

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr(manager, "submit", _fake_submit)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager.resume_session("session-1")

    assert result["success"] is True
    assert result["resumed_from_run_id"] == "run-old"
    assert len(submit_calls) == 1
    assert submit_calls[0]["session_id"] == "session-1"
    assert submit_calls[0]["project_id"] == "project-1"
    assert submit_calls[0]["disabled_tools"] == ["bash"]
    assert submit_calls[0]["message"] == "请继续处理当前会话中未完成的内容。"
    assert redis.set_calls
    assert storage.updates[-1][0] == "session-1"


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
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._heartbeat = _FakeHeartbeat(exists=False)

    redis = _FakeRedis(acquired=True)
    local_submit_calls = []
    arq_submit_calls = []

    async def _fake_submit(**kwargs):
        local_submit_calls.append(kwargs)
        return kwargs["run_id"], ""

    async def _fake_submit_arq(**kwargs):
        arq_submit_calls.append(kwargs)
        return kwargs["run_id"], kwargs.get("trace_id") or ""

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        assert run_id == "run-old"
        assert loaded_session.id == "session-1"

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=["admin"])

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _FakeLimiter:
        async def claim_recovery_slot(self, **kwargs):
            return SimpleNamespace(result=recovery_module.ConcurrencyResult.STARTED)

        async def release(self, *args, **kwargs):
            return None

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "arq")
    monkeypatch.setattr(manager, "submit", _fake_submit)
    monkeypatch.setattr(manager, "submit_arq", _fake_submit_arq)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager.resume_session("session-1")

    assert result["success"] is True
    assert local_submit_calls == []
    assert len(arq_submit_calls) == 1
    assert arq_submit_calls[0]["executor_key"] == "agent_stream"
    assert arq_submit_calls[0]["trace_id"]
    assert arq_submit_calls[0].get("user_message_written") is not True
    assert arq_submit_calls[0]["message"] == "请继续处理当前会话中未完成的内容。"


@pytest.mark.asyncio
async def test_submit_recovery_run_falls_back_from_legacy_default_agent(
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

    async def _fake_submit(**kwargs):
        submit_calls.append(kwargs)
        return kwargs["run_id"], kwargs.get("trace_id") or ""

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _FakeLimiter:
        async def claim_recovery_slot(self, **kwargs):
            return SimpleNamespace(result=recovery_module.ConcurrencyResult.STARTED)

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
    monkeypatch.setattr(manager, "_submit_recovery_task", _fake_submit)

    result = await manager._submit_recovery_run(session, "run-old", "server_restart")

    assert result["success"] is True
    assert submit_calls[0]["agent_id"] == "search"
    assert storage.updates[-1][1].metadata["agent_id"] == "search"


@pytest.mark.asyncio
async def test_submit_recovery_run_rejects_disabled_plugin_owned_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    set_plugin_runtime(runtime)
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="team",
        name="Disabled Team Recovery Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "agent_id": "team",
            "executor_key": "agent_stream",
            "team_id": "team-1",
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    class _FakeLimiter:
        async def claim_recovery_slot(self, **kwargs):
            raise AssertionError("disabled plugin-owned agent should not claim recovery slot")

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=[])

    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())

    try:
        result = await manager._submit_recovery_run(session, "run-old", "server_restart")
    finally:
        set_plugin_runtime(None)

    assert result["success"] is False
    assert result["error"] == "plugin_unavailable"
    assert result["agent_id"] == "team"
    assert result["run_id"] is None
    assert storage.updates == []


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

    async def _fake_submit_recovery_run(self, *args, **kwargs):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(
        recovery_module.TaskRecoveryService,
        "submit_recovery_run",
        _fake_submit_recovery_run,
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

    redis = _FakeRedis(acquired=True)
    mark_failed_started = asyncio.Event()

    async def _blocking_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        mark_failed_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _blocking_mark_failed)

    task = asyncio.create_task(manager._resume_interrupted_run(session, "run-old", "manual_resume"))
    await asyncio.wait_for(mark_failed_started.wait(), timeout=1)

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

    async def _fake_submit_recovery_run(*args, **kwargs):
        submit_calls.append((args, kwargs))
        return {"success": True}

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(manager, "_submit_recovery_run", _fake_submit_recovery_run)

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

    redis = _FakeRedis(acquired=True)
    recoverable_failures = []

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        recoverable_failures.append((run_id, reason, loaded_session.id))

    async def _fake_submit_recovery_run(*args, **kwargs):
        return {"success": False, "message": "恢复任务失败：当前恢复队列已满"}

    class _FakeLimiter:
        async def claim_recovery_slot(self, **kwargs):
            return recovery_module.ConcurrencyResponse(
                result=recovery_module.ConcurrencyResult.REJECTED_QUEUE
            )

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda _key: object())
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(manager, "_submit_recovery_run", _fake_submit_recovery_run)

    result = await manager._resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert recoverable_failures == [
        ("run-old", "Task interrupted (instance unavailable)", "session-1")
    ]
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


@pytest.mark.asyncio
async def test_submit_recovery_run_reuses_trace_for_queued_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Queued Recovery Session",
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
        },
    )
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage

    captured_task_context = {}

    class _FakeLimiter:
        async def claim_recovery_slot(
            self,
            *,
            user_id: str,
            roles: list[str],
            old_run_id: str,
            new_run_id: str,
            session_id: str,
            task_context,
        ):
            captured_task_context.update(task_context)
            return SimpleNamespace(result=recovery_module.ConcurrencyResult.QUEUED)

    class _FakeExecutor:
        async def ensure_session(self, *args, **kwargs):
            return None

        async def _update_session_status(self, *args, **kwargs):
            return None

    presenter_calls = []

    class _FakePresenter:
        def __init__(self, config):
            self.trace_id = config.trace_id or "generated-trace"
            presenter_calls.append(config)

        async def _ensure_trace(self):
            return None

        async def emit_user_message(self, message: str):
            presenter_calls.append(message)

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=["admin"])

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(recovery_module, "Presenter", _FakePresenter)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    manager._executor = _FakeExecutor()

    result = await manager._submit_recovery_run(session, "run-old", "server_restart")

    assert result["success"] is True
    assert result["message"] == "任务恢复已加入队列"
    assert captured_task_context["team_id"] == "team-1"
    assert captured_task_context["user_message_written"] is True
    assert captured_task_context["trace_id"] == "generated-trace"
    assert "team_id" not in storage.updates[-1][1].metadata
    assert storage.updates[-1][1].metadata["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }
    assert manager._run_info[result["run_id"]]["trace_id"] == "generated-trace"
    assert (
        presenter_calls[-1] == "由于系统重启，上一轮任务已中断。请继续处理当前会话中未完成的内容。"
    )

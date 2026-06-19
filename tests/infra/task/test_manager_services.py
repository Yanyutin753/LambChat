from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.infra.task import concurrency as concurrency_module
from src.infra.task import manager as task_manager_module
from src.infra.task import recovery as recovery_module
from src.infra.task import startup_cleanup as startup_cleanup_module
from src.infra.task.status import TaskStatus
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


class _FakeHeartbeat:
    def __init__(self, exists: bool = False) -> None:
        self.exists = exists

    async def check_exists(self, run_id: str) -> bool:
        return self.exists


class _FakeRedis:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.set_calls: list[tuple[str, str, int, bool]] = []
        self.deleted_keys: list[str] = []

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.set_calls.append((key, value, ex or 0, nx))
        return self.acquired

    async def delete(self, key: str):
        self.deleted_keys.append(key)
        return 1


class _NoopHeartbeat:
    async def stop_all(self) -> None:
        return None


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length: int):
        return list(self._docs)


class _PagedFakeCursor:
    def __init__(self, docs, *, max_length: int) -> None:
        self._docs = list(docs)
        self._index = 0
        self.max_length = max_length
        self.to_list_lengths: list[int] = []

    async def to_list(self, length: int):
        self.to_list_lengths.append(length)
        if length > self.max_length:
            raise AssertionError("startup cleanup should read stale sessions in small pages")
        chunk = self._docs[self._index : self._index + length]
        self._index += len(chunk)
        return list(chunk)


class _FakeCollection:
    def __init__(self, docs_per_call):
        self._docs_per_call = list(docs_per_call)
        self.calls = 0

    def find(self, *args, **kwargs):
        docs = self._docs_per_call[self.calls]
        self.calls += 1
        return _FakeCursor(docs)


class _FailingCollection:
    def find(self, *args, **kwargs):
        raise AssertionError("startup cleanup should not scan sessions without the lease")


class _PagedFakeCollection:
    def __init__(self, docs_per_call, *, max_length: int) -> None:
        self._docs_per_call = list(docs_per_call)
        self.max_length = max_length
        self.calls = 0
        self.cursors: list[_PagedFakeCursor] = []

    def find(self, *args, **kwargs):
        docs = self._docs_per_call[self.calls]
        self.calls += 1
        cursor = _PagedFakeCursor(docs, max_length=self.max_length)
        self.cursors.append(cursor)
        return cursor


@pytest.mark.asyncio
async def test_task_manager_shutdown_releases_global_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = task_manager_module.BackgroundTaskManager()
    manager._heartbeat = _NoopHeartbeat()
    manager._executor = object()
    task_manager_module._task_manager = manager

    monkeypatch.setattr(
        concurrency_module,
        "get_concurrency_limiter",
        lambda: SimpleNamespace(release=lambda *args, **kwargs: None),
    )

    await manager.shutdown()

    assert task_manager_module._task_manager is None


@pytest.mark.asyncio
async def test_recovery_service_resume_session_submits_localized_recovery_message(
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
    heartbeat = _FakeHeartbeat(exists=False)
    run_info: dict[str, dict[str, object]] = {}
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

    service = recovery_module.TaskRecoveryService(
        storage=storage,
        run_info=run_info,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        submit_task=_fake_submit,
        mark_run_failed=_fake_mark_failed,
    )

    result = await service.resume_session("session-1")

    assert result["success"] is True
    assert result["resumed_from_run_id"] == "run-old"
    assert len(submit_calls) == 1
    assert submit_calls[0]["session_id"] == "session-1"
    assert submit_calls[0]["project_id"] == "project-1"
    assert submit_calls[0]["disabled_tools"] == ["bash"]
    assert submit_calls[0]["team_id"] == "team-1"
    assert "active_goal" not in submit_calls[0]
    assert submit_calls[0]["message"] == "请继续处理当前会话中未完成的内容。"
    assert submit_calls[0]["enabled_skills"] is None
    assert redis.set_calls
    assert storage.updates[-1][0] == "session-1"
    recovered_metadata = storage.updates[-1][1].metadata
    assert "team_id" not in recovered_metadata
    assert recovered_metadata["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }


@pytest.mark.asyncio
async def test_recovery_service_preserves_empty_enabled_skills_whitelist(
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
            "enabled_skills": [],
        },
    )
    storage = _FakeStorage(session)
    heartbeat = _FakeHeartbeat(exists=False)
    redis = _FakeRedis(acquired=True)
    submit_calls = []

    async def _fake_submit(**kwargs):
        submit_calls.append(kwargs)
        return kwargs["run_id"], ""

    async def _fake_mark_failed(run_id: str, reason: str, loaded_session) -> None:
        return None

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            return SimpleNamespace(metadata={"language": "zh-CN"})

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)

    service = recovery_module.TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        submit_task=_fake_submit,
        mark_run_failed=_fake_mark_failed,
    )

    result = await service.resume_session("session-1")

    assert result["success"] is True
    assert submit_calls[0]["enabled_skills"] == []
    metadata = storage.updates[-1][1].metadata
    assert metadata["enabled_skills"] == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_recovers_latest_running_session_without_heartbeat(
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
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
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
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == [("session-1", "run-old", "server_restart")]
    assert fake_limiter.release_calls == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_skips_running_session_superseded_by_new_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Newer Run Session",
        metadata={
            "current_run_id": "run-new",
            "task_status": "running",
        },
    )
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
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
        recovery_calls.append((session.id, source_run_id, reason))
        return {"success": True, "run_id": "run-recovered", "message": "ok"}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_skips_scan_when_lease_is_held_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.collection = _FailingCollection()
    heartbeat = _FakeHeartbeat(exists=False)
    redis = _FakeRedis(acquired=False)
    callback_calls: list[str] = []

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = redis

    async def _fake_load_session(raw_session):
        raise AssertionError("startup cleanup should not load sessions without the lease")

    async def _fake_resume(*_args, **_kwargs):
        raise AssertionError("startup cleanup should not recover runs without the lease")

    async def _fake_replay() -> None:
        callback_calls.append("replay")

    async def _fake_cleanup_queues() -> None:
        callback_calls.append("cleanup_queues")

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_fake_replay,
        cleanup_stale_queues=_fake_cleanup_queues,
    )

    await service.cleanup_stale_tasks()

    assert callback_calls == []
    assert redis.set_calls


@pytest.mark.asyncio
async def test_startup_cleanup_service_limits_parallel_session_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": f"mongo-{index}",
                    "session_id": f"session-{index}",
                    "user_id": "user-1",
                    "metadata": {"current_run_id": f"run-{index}"},
                }
                for index in range(5)
            ],
            [],
            [],
        ]
    )
    heartbeat = _FakeHeartbeat(exists=True)
    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def _fake_load_session(raw_session):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return SimpleNamespace(
            id=raw_session["session_id"],
            user_id=raw_session["user_id"],
            metadata={
                "current_run_id": raw_session["metadata"]["current_run_id"],
                "task_status": "running",
            },
        )

    async def _fake_resume(*_args, **_kwargs):
        return {"success": True}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )
    monkeypatch.setattr(
        startup_cleanup_module.settings,
        "TASK_STARTUP_CLEANUP_CONCURRENCY",
        2,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    task = asyncio.create_task(service.cleanup_stale_tasks())
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    await task


@pytest.mark.asyncio
async def test_startup_cleanup_service_reads_stale_sessions_in_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    collection = _PagedFakeCollection(
        [
            [
                {
                    "_id": f"mongo-{index}",
                    "session_id": f"session-{index}",
                    "user_id": "user-1",
                    "metadata": {"current_run_id": f"run-{index}"},
                }
                for index in range(5)
            ],
            [],
            [],
        ],
        max_length=2,
    )
    storage.collection = collection
    heartbeat = _FakeHeartbeat(exists=True)

    async def _fake_load_session(raw_session):
        return SimpleNamespace(
            id=raw_session["session_id"],
            user_id=raw_session["user_id"],
            metadata={
                "current_run_id": raw_session["metadata"]["current_run_id"],
                "task_status": "running",
            },
        )

    async def _fake_resume(*_args, **_kwargs):
        return {"success": True}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )
    monkeypatch.setattr(startup_cleanup_module, "STALE_SESSION_SCAN_PAGE_SIZE", 2)

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert collection.cursors[0].to_list_lengths == [2, 2, 2]


@pytest.mark.asyncio
async def test_startup_cleanup_service_recovers_latest_explicit_system_restart_failure(
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
                        "task_status": "failed",
                        "task_recoverable": True,
                        "task_error_code": "server_restart",
                    },
                }
            ],
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
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

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == [("session-1", "run-old", "server_restart")]
    assert fake_limiter.release_calls == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_skips_user_cancelled_running_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Cancelled Running Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "running",
            "task_error_code": "cancelled",
            "task_recoverable": False,
        },
    )
    storage = _FakeStorage(session)
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {
                        "current_run_id": "run-old",
                        "task_error_code": "cancelled",
                        "task_recoverable": False,
                    },
                }
            ],
            [],
            [],
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
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

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_skips_running_session_with_persisted_cancel_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Cancel Event Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "running",
        },
    )
    storage = _FakeStorage(session)
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {
                        "current_run_id": "run-old",
                        "task_status": "running",
                    },
                }
            ],
            [],
            [],
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
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

    class _FakeDualWriter:
        async def read_session_events(self, *args, **kwargs):
            assert kwargs["run_id"] == "run-old"
            assert kwargs["event_types"] == ["user:cancel"]
            assert kwargs["completed_only"] is False
            assert kwargs["max_events"] == 1
            return [
                {
                    "event_type": "user:cancel",
                    "data": {"run_id": "run-old"},
                }
            ]

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        replay_pending_queued_tasks=_no_op,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == []


@pytest.mark.asyncio
async def test_startup_cleanup_service_skips_user_cancelled_abandoned_queued_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Cancelled Queued Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "queued",
            "task_error_code": "cancelled",
            "task_recoverable": False,
        },
    )
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
                        "task_error_code": "cancelled",
                        "task_recoverable": False,
                    },
                }
            ],
            [],
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {
                        "current_run_id": "run-old",
                        "task_error_code": "cancelled",
                        "task_recoverable": False,
                    },
                }
            ],
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
        recovery_calls.append((session.id, source_run_id, reason))
        return {"success": True, "run_id": "run-new", "message": "ok"}

    async def _no_op() -> None:
        return None

    class _FakeLimiterRedis:
        async def zscore(self, key: str, member: str):
            return None

        async def lrange(self, key: str, start: int, end: int):
            return []

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
        cleanup_stale_queues=_no_op,
    )

    await service.cleanup_stale_tasks()

    assert recovery_calls == []


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_replays_latest_queued_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Queued Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "queued",
        },
    )
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
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)

    class _FakeLimiterRedis:
        async def lrange(self, key: str, start: int, end: int):
            return ['{"run_id":"run-old","queued_at":0}']

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()

    async def _fake_load_session(raw_session):
        return session

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert fake_limiter.release_calls == [("user-1", "run-old", True)]


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_skips_session_superseded_by_new_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Superseded Queued Session",
        metadata={
            "current_run_id": "run-new",
            "task_status": "queued",
        },
    )
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
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    recovery_calls = []

    class _FakeLimiterRedis:
        async def lrange(self, key: str, start: int, end: int):
            return ['{"run_id":"run-old","queued_at":0}']

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()

    async def _fake_load_session(raw_session):
        assert raw_session["session_id"] == "session-1"
        return session

    async def _fake_resume(session, source_run_id: str, reason: str):
        recovery_calls.append((session.id, source_run_id, reason))
        return {"success": True, "run_id": "run-recovered", "message": "ok"}

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=_fake_resume,
    )

    await service.replay_pending_queued_tasks()

    assert fake_limiter.release_calls == []
    assert recovery_calls == []


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_scans_queue_in_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Queued Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "queued",
        },
    )
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
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)

    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.lrange_calls = []

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if end == -1:
                raise AssertionError("queue replay must not read the full list")
            return ['{"run_id":"run-old","queued_at":0}']

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()

    async def _fake_load_session(raw_session):
        return session

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert fake_limiter.redis.lrange_calls == [("chat:queue:user-1", 0, 99)]
    assert fake_limiter.release_calls == [("user-1", "run-old", True)]


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_rejects_disabled_plugin_owned_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="team",
        name="Queued Team Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "queued",
            "agent_id": "team",
        },
    )
    storage = _FakeStorage(session)
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": "mongo-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "metadata": {
                        "current_run_id": "run-old",
                        "task_status": "queued",
                        "agent_id": "team",
                    },
                }
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)
    status_calls: list[tuple] = []

    class _FakeExecutor:
        async def _update_session_status(self, *args, **kwargs):
            status_calls.append((args, kwargs))

    class _FakeLimiterRedis:
        async def lrange(self, key: str, start: int, end: int):
            del key, start, end
            return ['{"run_id":"run-old","queued_at":0}']

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")

    async def _fake_load_session(raw_session):
        return session

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )
    set_plugin_runtime(runtime)

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: _FakeExecutor(),
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    try:
        await service.replay_pending_queued_tasks()
    finally:
        set_plugin_runtime(None)

    assert fake_limiter.release_calls == []
    assert status_calls
    args, kwargs = status_calls[0]
    assert args[0] == "session-1"
    assert args[1] is TaskStatus.FAILED
    assert "agent_team" in args[2]
    assert kwargs == {"run_id": "run-old"}


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_stops_queue_scan_after_needed_run_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Queued Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "queued",
        },
    )
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
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)

    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.lrange_calls = []

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if start > 0:
                raise AssertionError("queue replay should stop once wanted run_ids are found")
            return [
                '{"run_id":"run-old","queued_at":0}'
            ] * startup_cleanup_module.QUEUE_SCAN_PAGE_SIZE

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()

    async def _fake_load_session(raw_session):
        return session

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert fake_limiter.redis.lrange_calls == [("chat:queue:user-1", 0, 99)]
    assert fake_limiter.release_calls == [("user-1", "run-old", True)]


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_indexes_each_user_queue_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = [
        SimpleNamespace(
            id=f"session-{index}",
            user_id="user-1",
            agent_id="search",
            name="Queued Session",
            metadata={
                "current_run_id": f"run-{index}",
                "task_status": "queued",
            },
        )
        for index in range(3)
    ]
    storage = _FakeStorage()
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": f"mongo-{index}",
                    "session_id": f"session-{index}",
                    "user_id": "user-1",
                    "metadata": {"current_run_id": f"run-{index}"},
                }
                for index in range(3)
            ]
        ]
    )
    heartbeat = _FakeHeartbeat(exists=False)

    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.lrange_calls = []

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if len(self.lrange_calls) > 1:
                raise AssertionError("same user queue should be indexed once per replay pass")
            return [f'{{"run_id":"run-{index}","queued_at":0}}' for index in range(3)]

        async def zscore(self, key: str, member: str):
            return None

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()
    sessions_by_id = {session.id: session for session in sessions}

    async def _fake_load_session(raw_session):
        return sessions_by_id[raw_session["session_id"]]

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert fake_limiter.redis.lrange_calls == [("chat:queue:user-1", 0, 99)]
    assert fake_limiter.release_calls == [
        ("user-1", "run-0", True),
        ("user-1", "run-1", True),
        ("user-1", "run-2", True),
    ]


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_reads_pending_sessions_in_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = [
        SimpleNamespace(
            id=f"session-{index}",
            user_id="user-1",
            agent_id="search",
            name="Queued Session",
            metadata={
                "current_run_id": f"run-{index}",
                "task_status": "queued",
            },
        )
        for index in range(150)
    ]
    docs = [
        {
            "_id": f"mongo-{index}",
            "session_id": f"session-{index}",
            "user_id": "user-1",
            "metadata": {"current_run_id": f"run-{index}"},
        }
        for index in range(150)
    ]
    storage = _FakeStorage()
    storage.collection = _PagedFakeCollection([docs], max_length=100)
    heartbeat = _FakeHeartbeat(exists=False)

    class _FakeLimiterRedis:
        async def lrange(self, key: str, start: int, end: int):
            del start, end
            run_id = key.rsplit(":", 1)[-1]
            return []

        async def zscore(self, key: str, member: str):
            return 1

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    fake_limiter = _FakeLimiter()
    sessions_by_id = {session.id: session for session in sessions}

    async def _fake_load_session(raw_session):
        return sessions_by_id[raw_session["session_id"]]

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert storage.collection.cursors[0].to_list_lengths == [100, 100]


@pytest.mark.asyncio
async def test_replay_pending_queued_tasks_limits_parallel_session_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = [
        SimpleNamespace(
            id=f"session-{index}",
            user_id="user-1",
            agent_id="search",
            name="Queued Session",
            metadata={
                "current_run_id": f"run-{index}",
                "task_status": "queued",
            },
        )
        for index in range(5)
    ]
    storage = _FakeStorage()
    storage.collection = _FakeCollection(
        [
            [
                {
                    "_id": f"mongo-{index}",
                    "session_id": f"session-{index}",
                    "user_id": "user-1",
                    "metadata": {"current_run_id": f"run-{index}"},
                }
                for index in range(5)
            ]
        ]
    )
    active = 0
    max_active = 0
    sessions_by_id = {session.id: session for session in sessions}

    async def _fake_load_session(raw_session):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return sessions_by_id[raw_session["session_id"]]

    class _FakeLimiterRedis:
        async def lrange(self, key: str, start: int, end: int):
            del key, start, end
            return []

        async def zscore(self, key: str, member: str):
            del key, member
            return 1

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()
            self.release_calls = []

        async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
            self.release_calls.append((user_id, run_id, dequeue))

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
    )
    monkeypatch.setattr(
        startup_cleanup_module.settings,
        "TASK_STARTUP_CLEANUP_CONCURRENCY",
        2,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=storage,
        heartbeat=_FakeHeartbeat(exists=True),
        ensure_executor=lambda: None,
        load_session_record=_fake_load_session,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.replay_pending_queued_tasks()

    assert max_active == 2


@pytest.mark.asyncio
async def test_cleanup_stale_queues_scans_queue_entries_in_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.scan_calls = 0
            self.lrange_calls = []
            self.deleted = []
            self.pushed = []

        async def scan(self, cursor=0, match=None, count=100):
            self.scan_calls += 1
            return 0, ["chat:queue:user-1"]

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if end == -1:
                raise AssertionError("stale queue cleanup must not read the full list")
            return ['{"run_id":"run-old","queued_at":9999999999}']

        async def delete(self, key: str):
            self.deleted.append(key)

        async def rpush(self, key: str, *values):
            self.pushed.append((key, values))

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    fake_limiter = _FakeLimiter()
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=_FakeStorage(),
        heartbeat=_FakeHeartbeat(exists=False),
        ensure_executor=lambda: None,
        load_session_record=lambda *_args: None,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.cleanup_stale_queues()

    assert fake_limiter.redis.lrange_calls == [("chat:queue:user-1", 0, 99)]
    assert fake_limiter.redis.deleted == []


@pytest.mark.asyncio
async def test_rewrite_queue_without_expired_offloads_queue_entry_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _FakeRedis:
        async def lrange(self, key: str, start: int, end: int):
            del key, start, end
            return ['{"run_id":"run-fresh","queued_at":9999999999}']

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        startup_cleanup_module,
        "run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )

    expired = await startup_cleanup_module._rewrite_queue_without_expired(
        _FakeRedis(),
        "chat:queue:user-1",
        queue_timeout=60,
    )

    assert expired == 0
    assert calls == [json.loads]


@pytest.mark.asyncio
async def test_find_queued_run_ids_offloads_queue_entry_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _FakeRedis:
        async def lrange(self, key: str, start: int, end: int):
            del key, start, end
            return ['{"run_id":"run-wanted","queued_at":9999999999}']

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        startup_cleanup_module,
        "run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )

    found = await startup_cleanup_module._find_queued_run_ids(
        _FakeRedis(),
        "chat:queue:user-1",
        {"run-wanted"},
    )

    assert found == {"run-wanted"}
    assert calls == [json.loads]


@pytest.mark.asyncio
async def test_cleanup_stale_queues_rewrites_valid_entries_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(startup_cleanup_module, "QUEUE_REWRITE_CHUNK_SIZE", 2, raising=False)

    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.lrange_calls = []
            self.deleted = []
            self.pushed = []
            self.renamed = []

        async def scan(self, cursor=0, match=None, count=100):
            return 0, ["chat:queue:user-1"]

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if start > 0:
                return []
            return [
                '{"run_id":"expired","queued_at":0}',
                '{"run_id":"valid-1","queued_at":9999999999}',
                '{"run_id":"valid-2","queued_at":9999999999}',
                '{"run_id":"valid-3","queued_at":9999999999}',
                '{"run_id":"valid-4","queued_at":9999999999}',
                '{"run_id":"valid-5","queued_at":9999999999}',
            ]

        async def delete(self, key: str):
            self.deleted.append(key)

        async def rpush(self, key: str, *values):
            if len(values) > 2:
                raise AssertionError("stale queue cleanup should rewrite valid entries in chunks")
            self.pushed.append((key, values))

        async def rename(self, src: str, dst: str):
            self.renamed.append((src, dst))

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    fake_limiter = _FakeLimiter()
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=_FakeStorage(),
        heartbeat=_FakeHeartbeat(exists=False),
        ensure_executor=lambda: None,
        load_session_record=lambda *_args: None,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.cleanup_stale_queues()

    assert fake_limiter.redis.deleted == []
    assert len(fake_limiter.redis.renamed) == 1
    tmp_key, dst_key = fake_limiter.redis.renamed[0]
    assert tmp_key.startswith("chat:queue-cleanup:{chat:queue:user-1}:")
    assert dst_key == "chat:queue:user-1"
    assert fake_limiter.redis.pushed == [
        (
            tmp_key,
            (
                '{"run_id":"valid-1","queued_at":9999999999}',
                '{"run_id":"valid-2","queued_at":9999999999}',
            ),
        ),
        (
            tmp_key,
            (
                '{"run_id":"valid-3","queued_at":9999999999}',
                '{"run_id":"valid-4","queued_at":9999999999}',
            ),
        ),
        (
            tmp_key,
            ('{"run_id":"valid-5","queued_at":9999999999}',),
        ),
    ]


@pytest.mark.asyncio
async def test_cleanup_stale_queues_does_not_rewrite_when_nothing_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(startup_cleanup_module, "QUEUE_REWRITE_CHUNK_SIZE", 2, raising=False)

    class _FakeLimiterRedis:
        def __init__(self) -> None:
            self.lrange_calls = []
            self.deleted = []
            self.pushed = []
            self.renamed = []

        async def scan(self, cursor=0, match=None, count=100):
            return 0, ["chat:queue:user-1"]

        async def lrange(self, key: str, start: int, end: int):
            self.lrange_calls.append((key, start, end))
            if start > 0:
                return []
            return [
                '{"run_id":"valid-1","queued_at":9999999999}',
                '{"run_id":"valid-2","queued_at":9999999999}',
                '{"run_id":"valid-3","queued_at":9999999999}',
                '{"run_id":"valid-4","queued_at":9999999999}',
                '{"run_id":"valid-5","queued_at":9999999999}',
            ]

        async def delete(self, key: str):
            self.deleted.append(key)

        async def rpush(self, key: str, *values):
            self.pushed.append((key, values))

        async def rename(self, src: str, dst: str):
            self.renamed.append((src, dst))

    class _FakeLimiter:
        def __init__(self) -> None:
            self.redis = _FakeLimiterRedis()

    fake_limiter = _FakeLimiter()
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: fake_limiter,
    )

    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=_FakeStorage(),
        heartbeat=_FakeHeartbeat(exists=False),
        ensure_executor=lambda: None,
        load_session_record=lambda *_args: None,
        resume_interrupted_run=lambda *args, **kwargs: None,
    )

    await service.cleanup_stale_queues()

    assert fake_limiter.redis.deleted == []
    assert fake_limiter.redis.pushed == []
    assert fake_limiter.redis.renamed == []

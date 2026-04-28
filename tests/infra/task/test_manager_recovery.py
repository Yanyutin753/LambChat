from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.task import manager as task_manager_module
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


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length: int):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs_per_call):
        self._docs_per_call = list(docs_per_call)
        self.calls = 0

    def find(self, *args, **kwargs):
        docs = self._docs_per_call[self.calls]
        self.calls += 1
        return _FakeCursor(docs)


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

    monkeypatch.setattr(task_manager_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(task_manager_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(task_manager_module, "get_registered_executor", lambda key: _fake_executor)
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
async def test_cleanup_stale_tasks_attempts_auto_recovery_for_running_sessions(
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

    async def _fake_submit_recovery_run(*args, **kwargs):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(task_manager_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)
    monkeypatch.setattr(manager, "_submit_recovery_run", _fake_submit_recovery_run)

    result = await manager._resume_interrupted_run(session, "run-old", "manual_resume")

    assert result["success"] is False
    assert redis.deleted_keys == ["task:recovery:session-1:run-old"]


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

    monkeypatch.setattr(task_manager_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(manager, "_mark_run_failed", _fake_mark_failed)

    result = await manager._resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert "已由其他恢复流程接管" in result["message"]
    assert mark_failed_calls == []
    assert redis.deleted_keys == ["task:recovery:session-1:run-old"]


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
            return SimpleNamespace(result=task_manager_module.ConcurrencyResult.QUEUED)

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

    monkeypatch.setattr(task_manager_module, "Presenter", _FakePresenter)
    monkeypatch.setattr(task_manager_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(task_manager_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(task_manager_module, "get_registered_executor", lambda key: _fake_executor)
    manager._executor = _FakeExecutor()

    result = await manager._submit_recovery_run(session, "run-old", "server_restart")

    assert result["success"] is True
    assert result["message"] == "任务恢复已加入队列"
    assert captured_task_context["user_message_written"] is True
    assert captured_task_context["trace_id"] == "generated-trace"
    assert manager._run_info[result["run_id"]]["trace_id"] == "generated-trace"
    assert (
        presenter_calls[-1] == "由于系统重启，上一轮任务已中断。请继续处理当前会话中未完成的内容。"
    )

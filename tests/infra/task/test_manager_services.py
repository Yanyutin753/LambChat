from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task import startup_cleanup as startup_cleanup_module


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
    assert submit_calls[0]["message"] == "请继续处理当前会话中未完成的内容。"
    assert redis.set_calls
    assert storage.updates[-1][0] == "session-1"


@pytest.mark.asyncio
async def test_startup_cleanup_service_attempts_auto_recovery_for_running_sessions(
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

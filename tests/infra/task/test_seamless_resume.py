from __future__ import annotations

"""无缝续跑：resume_interrupted_run 必须复用原 run_id/trace、用隐藏恢复指令、限次。

旧行为：先 mark_run_failed（写 error 事件 + trace 终结 error），再开新 run 并把
恢复提示当 user:message 显示给用户。新行为：同 run/trace 续跑，恢复指令只给模型
（user_message_written=True，不落 UI 事件），超限后终态失败防止毒消息无限重跑。
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.recovery import TaskRecoveryService


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, Any]] = []

    async def update(self, session_id, session_update) -> None:
        self.updates.append((session_id, session_update))


class _FakeRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple] = []
        self.eval_calls: list[tuple] = []

    async def set(self, key, value, ex=None, nx=False):
        self.set_calls.append((key, value, ex, nx))
        return True

    async def eval(self, script, num_keys, *args):
        self.eval_calls.append((script, num_keys, *args))
        return 1


class _FakeTraceCursor:
    def sort(self, key, direction=None):
        return self

    def limit(self, limit):
        return self

    async def to_list(self, length=None):
        return [{"trace_id": "trace-1"}]


class _FakeTraceStorage:
    def __init__(self) -> None:
        self.reopened: list[str] = []
        self.collection = SimpleNamespace(
            find=lambda query, projection=None: _FakeTraceCursor()
        )

    async def reopen_interrupted_trace(self, trace_id: str) -> bool:
        self.reopened.append(trace_id)
        return True


class _FakeRedisStream:
    def __init__(self, entries: list[tuple[str, dict[str, Any]]]) -> None:
        self.entries = list(entries)
        self.deleted: list[str] = []

    async def xrange(self, stream_key, min="-", max="+"):
        return list(self.entries)

    async def xdel(self, stream_key, entry_id):
        self.deleted.append(entry_id)
        self.entries = [e for e in self.entries if e[0] != entry_id]


class _FakeDualWriter:
    def __init__(self, redis_stream: _FakeRedisStream) -> None:
        self.redis = redis_stream

    @staticmethod
    def _stream_key(session_id, run_id):
        return f"session:{session_id}:run:{run_id}:events"


class _FakeLimiter:
    def __init__(self, acquire: bool = True) -> None:
        self.acquire = acquire
        self.released: list[tuple] = []

    async def try_acquire_run_slot(self, user_id: str, run_id: str) -> bool:
        return self.acquire

    async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
        self.released.append((user_id, run_id, dequeue))


def _make_session(resume_attempts: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        name="Seamless Session",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
            "agent_id": "search",
            "executor_key": "agent_stream",
            "resume_attempts": resume_attempts,
        },
    )


def _fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resume_attempts: int = 0,
    limiter: _FakeLimiter | None = None,
    stale: bool = True,
) -> tuple[TaskRecoveryService, SimpleNamespace, dict[str, Any]]:
    session = _make_session(resume_attempts)
    storage = _FakeStorage(session)
    limiter = limiter or _FakeLimiter()
    trace_storage = _FakeTraceStorage()
    # is_stale 可被个别测试覆盖；默认 stale=True（执行者已死，允许恢复）
    stale_holder = {"stale": stale}

    async def _stale_flag(run_id: str) -> bool:
        return stale_holder["stale"]
    redis_stream = _FakeRedisStream(
        [
            ("1-1", {"event_type": "thinking", "data": "{}"}),
            ("1-2", {"event_type": "error", "data": "{}"}),
        ]
    )
    submit_task = AsyncMock(return_value=("run-old", "trace-1"))
    mark_run_failed = AsyncMock()
    service = TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=SimpleNamespace(
            check_exists=lambda run_id: False,
            is_stale=_stale_flag,
        ),
        ensure_executor=lambda: SimpleNamespace(),
        submit_task=submit_task,
        mark_run_failed=mark_run_failed,
    )

    class _FakeUserStorage:
        async def get_by_id(self, user_id: str):
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=[])

    async def _fake_executor(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_trace_storage", lambda: trace_storage)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(redis_stream),
    )
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _fake_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(recovery_module, "_resolve_recovery_agent_id", lambda m, s: "search")
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")

    artifacts = {
        "storage": storage,
        "limiter": limiter,
        "trace_storage": trace_storage,
        "redis_stream": redis_stream,
        "submit_task": submit_task,
        "mark_run_failed": mark_run_failed,
    }
    return service, session, artifacts


@pytest.mark.asyncio
async def test_resume_reuses_run_and_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    service, session, artifacts = _fixture(monkeypatch)

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is True
    assert result["run_id"] == "run-old"
    assert result["resumed_from_run_id"] == "run-old"
    assert result.get("seamless") is True

    submit_task = artifacts["submit_task"]
    assert submit_task.await_count == 1
    call = submit_task.await_args
    assert call.args[:4] == ("session-1", "search", call.args[2], "user-1")
    assert call.args[2] == "由于系统重启，上一轮任务已中断。请继续处理当前会话中未完成的内容。"
    kwargs = call.kwargs
    assert kwargs["run_id"] == "run-old"
    assert kwargs["trace_id"] == "trace-1"
    assert kwargs["user_message_written"] is True
    assert kwargs["interrupted_resume"] is True

    # 成功后：恢复次数 +1、清掉 recoverable 标记（扫描器不再重复接管）
    last_metadata = artifacts["storage"].updates[-1][1].metadata
    assert last_metadata["resume_attempts"] == 1
    assert last_metadata["task_recoverable"] is False
    assert last_metadata["task_error_code"] is None


@pytest.mark.asyncio
async def test_resume_reopens_error_trace_and_strips_terminal_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session, artifacts = _fixture(monkeypatch)

    await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert artifacts["trace_storage"].reopened == ["trace-1"]
    assert artifacts["redis_stream"].deleted == ["1-2"]  # 只删 error，保留 thinking
    remaining = [fields["event_type"] for _, fields in artifacts["redis_stream"].entries]
    assert remaining == ["thinking"]


@pytest.mark.asyncio
async def test_resume_caps_attempts_at_three(monkeypatch: pytest.MonkeyPatch) -> None:
    service, session, artifacts = _fixture(monkeypatch, resume_attempts=3)

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert "上限" in result["message"]
    assert artifacts["submit_task"].await_count == 0
    artifacts["mark_run_failed"].assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_skips_when_heartbeat_still_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """心跳未过期（实例可能仍活着）时不得恢复，防同 run 并发执行。"""
    service, session, artifacts = _fixture(monkeypatch)

    async def _fresh_heartbeat(run_id: str) -> bool:
        return False  # is_stale=False → 仍存活

    monkeypatch.setattr(service._heartbeat, "is_stale", _fresh_heartbeat)

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert "仍在其他实例" in result["message"]
    assert artifacts["submit_task"].await_count == 0


@pytest.mark.asyncio
async def test_resume_failure_restores_recoverable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session, artifacts = _fixture(
        monkeypatch, limiter=_FakeLimiter(acquire=False)
    )

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert artifacts["submit_task"].await_count == 0
    last_metadata = artifacts["storage"].updates[-1][1].metadata
    assert last_metadata["task_status"] == "failed"
    assert last_metadata["task_recoverable"] is True
    assert last_metadata["task_error_code"] == "server_restart"


@pytest.mark.asyncio
async def test_resume_submit_exception_releases_slot_and_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _FakeLimiter()
    service, session, artifacts = _fixture(monkeypatch, limiter=limiter)
    artifacts["submit_task"].side_effect = RuntimeError("boom")

    result = await service.resume_interrupted_run(session, "run-old", "server_restart")

    assert result["success"] is False
    assert limiter.released == [("user-1", "run-old", False)]
    last_metadata = artifacts["storage"].updates[-1][1].metadata
    assert last_metadata["task_status"] == "failed"
    assert last_metadata["task_recoverable"] is True

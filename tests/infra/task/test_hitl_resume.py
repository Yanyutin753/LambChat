"""HITL interrupt 模式恢复服务测试（issue #218）。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.infra.task.hitl as hitl_mod
from src.infra.task.hitl import (
    extract_ask_human_interrupts,
    hitl_interrupt_mode_enabled,
    is_interrupt_approval,
    submit_hitl_resume_run,
)


def _approval(**overrides):
    base = dict(
        id="approval-1",
        session_id="session-1",
        user_id="user-1",
        metadata={"mode": "interrupt", "run_id": "run-1", "thread_id": "session-1"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            result = None
        else:
            self.store[key] = value
            result = True
        return _maybe_await(result)

    def eval(self, script, numkeys, key, token):
        released = self.store.pop(key, None) == token
        return _maybe_await(int(released))


def _maybe_await(value):
    import asyncio

    fut = asyncio.get_event_loop().create_future()
    fut.set_result(value)
    return fut


class _RacyReleaseRedis:
    """让两个 GET 都读到 marker，暴露非原子 GET+DELETE 竞态。"""

    def __init__(self) -> None:
        self.value: str | None = "1"
        self.get_calls = 0
        self.both_getting = asyncio.Event()

    async def get(self, _key: str):
        captured = self.value
        self.get_calls += 1
        if self.get_calls >= 2:
            self.both_getting.set()
        await self.both_getting.wait()
        return captured

    async def getdel(self, _key: str):
        value = self.value
        self.value = None
        return value

    async def delete(self, _key: str):
        self.value = None


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(hitl_mod, "get_redis_client", lambda: redis)
    return redis


def test_is_interrupt_approval():
    assert is_interrupt_approval(_approval())
    assert not is_interrupt_approval(_approval(metadata=None))
    assert not is_interrupt_approval(_approval(metadata={"mode": "blocking"}))


def test_hitl_mode_disabled_by_default(monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "blocking", raising=False)
    assert not hitl_interrupt_mode_enabled()


def test_extract_ask_human_interrupts_keeps_interrupt_ids() -> None:
    snapshot = SimpleNamespace(
        tasks=(
            SimpleNamespace(
                interrupts=(
                    SimpleNamespace(
                        id="interrupt-a",
                        value={"kind": "ask_human", "message": "same", "fields": []},
                    ),
                )
            ),
            SimpleNamespace(
                interrupts=(
                    SimpleNamespace(
                        id="interrupt-b",
                        value={"kind": "ask_human", "message": "same", "fields": []},
                    ),
                )
            ),
        )
    )

    assert extract_ask_human_interrupts(snapshot) == [
        {
            "kind": "ask_human",
            "message": "same",
            "fields": [],
            "interrupt_id": "interrupt-a",
        },
        {
            "kind": "ask_human",
            "message": "same",
            "fields": [],
            "interrupt_id": "interrupt-b",
        },
    ]


@pytest.mark.asyncio
async def test_source_release_marker_has_only_one_concurrent_consumer(monkeypatch) -> None:
    """两个恢复 worker 抢同一 source marker 时只能有一个立即进入。"""
    redis = _RacyReleaseRedis()
    monkeypatch.setattr(hitl_mod, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.check_exists",
        AsyncMock(return_value=True),
    )

    results = await asyncio.gather(
        hitl_mod.wait_for_hitl_source_release("run-1", "user-1", timeout=0.01),
        hitl_mod.wait_for_hitl_source_release("run-1", "user-1", timeout=0.01),
    )

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("heartbeat_exists", "slot_active", "expected"),
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
async def test_source_release_crash_fallback_requires_no_heartbeat_and_no_slot(
    monkeypatch,
    heartbeat_exists: bool,
    slot_active: bool,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.check_exists",
        AsyncMock(return_value=heartbeat_exists),
    )
    limiter = SimpleNamespace(is_active_run=AsyncMock(return_value=slot_active))
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter", lambda: limiter
    )

    result = await hitl_mod.wait_for_hitl_source_release(
        "run-crashed", "user-1", timeout=0
    )

    assert result is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "stored_attempt", "expected"),
    [
        ("approved", "attempt-1", True),
        ("pending", "attempt-1", False),
        ("approved", "attempt-other", False),
    ],
)
async def test_resume_activation_mongo_fallback_requires_exact_terminal_attempt(
    monkeypatch,
    status: str,
    stored_attempt: str,
    expected: bool,
) -> None:
    approval = SimpleNamespace(
        status=status,
        metadata={"resume_attempt_id": stored_attempt},
    )
    storage = SimpleNamespace(get=AsyncMock(return_value=approval))
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_approval_storage", lambda: storage
    )

    result = await hitl_mod.wait_for_hitl_resume_activation(
        "approval-1", "attempt-1", timeout=0
    )

    assert result is expected


@pytest.mark.asyncio
async def test_submit_resume_skips_when_not_waiting_human(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "interrupt", raising=False)

    class _Storage:
        async def get_by_session_id(self, session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="s",
                metadata={"task_status": "completed"},
            )

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", lambda: _Storage())
    result = await submit_hitl_resume_run(_approval(), {"approved": True, "values": {}})
    assert result["submitted"] is False
    assert "等待" in result["message"]


@pytest.mark.asyncio
async def test_submit_resume_rejects_approval_from_stale_run(fake_redis, monkeypatch):
    class _Storage:
        async def get_by_session_id(self, _session_id):
            return SimpleNamespace(
                user_id="user-1",
                metadata={
                    "task_status": "waiting_human",
                    "current_run_id": "run-new",
                },
            )

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _Storage)

    result = await submit_hitl_resume_run(
        _approval(metadata={"mode": "interrupt", "run_id": "run-old"}),
        {"approved": True, "values": {}},
    )

    assert result["submitted"] is False
    assert "已不是当前运行" in result["message"]


@pytest.mark.asyncio
async def test_local_resume_stays_retryable_when_concurrency_is_full(
    fake_redis, monkeypatch
):
    monkeypatch.setattr(hitl_mod.settings, "TASK_BACKEND", "local", raising=False)

    class _Storage:
        async def get_by_session_id(self, _session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="session",
                metadata={
                    "task_status": "waiting_human",
                    "current_run_id": "run-1",
                    "executor_key": "agent_stream",
                    "agent_id": "search",
                },
            )

    async def fake_executor():
        yield

    manager = SimpleNamespace(
        wait_for_task_completion=AsyncMock(),
        submit=AsyncMock(side_effect=AssertionError("full capacity must not submit")),
    )
    limiter = SimpleNamespace(try_acquire_run_slot=AsyncMock(return_value=False))
    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _Storage)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor", lambda _key: fake_executor
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter", lambda: limiter
    )
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)

    result = await submit_hitl_resume_run(
        _approval(), {"approved": True, "values": {}}
    )

    assert result == {
        "submitted": False,
        "run_id": None,
        "message": "当前并发任务已满，请稍后重试恢复",
    }
    manager.wait_for_task_completion.assert_awaited_once_with("run-1")
    manager.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_resume_lock_prevents_duplicate(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "interrupt", raising=False)
    fake_redis.store[f"{hitl_mod.HITL_RESUME_LOCK_PREFIX}approval-1"] = "other-token"

    result = await submit_hitl_resume_run(_approval(), {"approved": False, "values": {}})
    assert result["submitted"] is False
    assert "其他实例" in result["message"]


@pytest.mark.asyncio
async def test_submit_resume_submits_run_with_hitl_payload(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "interrupt", raising=False)
    monkeypatch.setattr(hitl_mod.settings, "TASK_BACKEND", "local", raising=False)

    class _Storage:
        async def get_by_session_id(self, session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="s",
                metadata={
                    "task_status": "waiting_human",
                    "current_run_id": "run-1",
                    "executor_key": "agent_stream",
                    "agent_id": "search",
                    "agent_options": {"model": "m"},
                    "disabled_tools": [],
                },
            )

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", lambda: _Storage())

    async def fake_executor():
        yield

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor", lambda key: fake_executor
    )

    submitted = {}

    class _Limiter:
        async def try_acquire_run_slot(self, user_id, run_id):
            submitted["slot"] = (user_id, run_id)
            return True

        async def release(self, user_id, run_id):
            submitted["released_slot"] = (user_id, run_id)

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter", lambda: _Limiter()
    )

    class _FakeManager:
        async def wait_for_task_completion(self, run_id):
            submitted["waited_for"] = run_id

        async def submit(self, *args, **kwargs):
            submitted["args"] = args
            submitted["kwargs"] = kwargs
            return kwargs["run_id"], kwargs["trace_id"]

    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeManager())

    resume_value = {"approved": True, "values": {"choice": "a"}}
    result = await submit_hitl_resume_run(
        _approval(
            metadata={
                "mode": "interrupt",
                "run_id": "run-1",
                "trace_id": "trace-1",
                "thread_id": "session-1",
                "interrupt_id": "interrupt-a",
                "resume_context": {
                    "active_goal": {"id": "goal-1"},
                    "recommendation_input": "原始问题",
                    "goal_started_at": "2026-08-21T10:00:00+00:00",
                },
            }
        ),
        resume_value,
    )
    assert result == {
        "submitted": True,
        "run_id": "run-1",
        "message": "恢复运行已提交",
    }
    assert submitted["waited_for"] == "run-1"
    assert submitted["slot"] == ("user-1", "run-1")
    assert submitted["args"][0] == "session-1"  # session_id
    assert submitted["args"][1] == "search"  # preserve the session's agent
    assert submitted["args"][2] == ""  # 空消息，不注入新用户输入
    assert submitted["kwargs"]["user_message_written"] is True
    assert submitted["kwargs"]["agent_options"] == {"model": "m"}
    assert submitted["kwargs"]["run_id"] == "run-1"
    assert submitted["kwargs"]["trace_id"] == "trace-1"
    assert submitted["kwargs"]["active_goal"] == {"id": "goal-1"}
    assert submitted["kwargs"]["recommendation_input"] == "原始问题"
    assert submitted["kwargs"]["hitl_resume"]["approval_id"] == "approval-1"
    assert submitted["kwargs"]["hitl_resume"]["goal_started_at"] == (
        "2026-08-21T10:00:00+00:00"
    )
    assert submitted["kwargs"]["hitl_resume"]["resume_value"] == {
        "interrupt-a": resume_value
    }
    assert submitted["kwargs"]["hitl_resume"]["approval_resolved"] == {
        "id": "approval-1",
        "tool_call_id": None,
        "interrupt_id": "interrupt-a",
        "status": "approved",
        "success": True,
        "result": {
            "status": "success",
            "message": "用户已响应",
            "values": {"choice": "a"},
        },
        "timestamp": submitted["kwargs"]["hitl_resume"]["approval_resolved"]["timestamp"],
    }


@pytest.mark.asyncio
async def test_submit_resume_uses_arq_attempt_but_keeps_logical_run(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "TASK_BACKEND", "arq", raising=False)

    class _Storage:
        async def get_by_session_id(self, _session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="s",
                metadata={
                    "task_status": "waiting_human",
                    "current_run_id": "run-1",
                    "executor_key": "agent_stream",
                    "agent_id": "team",
                },
            )

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _Storage)
    submitted = {}

    class _FakeManager:
        async def submit_arq(self, *args, **kwargs):
            submitted["args"] = args
            submitted["kwargs"] = kwargs
            return "run-1", "trace-1"

    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeManager())

    result = await submit_hitl_resume_run(
        _approval(
            metadata={
                "mode": "interrupt",
                "run_id": "run-1",
                "trace_id": "trace-1",
                "thread_id": "session-1",
                "interrupt_id": "interrupt-a",
            }
        ),
        {"approved": True, "values": {"choice": "a"}},
    )

    assert result["submitted"] is True
    assert result["run_id"] == "run-1"
    assert submitted["kwargs"]["run_id"] == "run-1"
    assert submitted["kwargs"]["trace_id"] == "trace-1"
    assert submitted["kwargs"]["dispatch_id"].startswith("hitl-resume:approval-1:")
    assert submitted["kwargs"]["hitl_resume"]["approval_id"] == "approval-1"


@pytest.mark.asyncio
async def test_submit_resume_failure_restores_waiting_session_state(fake_redis, monkeypatch):
    restored: list[tuple[str, dict]] = []

    class _Storage:
        async def get_by_session_id(self, _session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="s",
                metadata={
                    "task_status": "waiting_human",
                    "executor_key": "agent_stream",
                    "agent_id": "team",
                },
            )

        async def update_metadata_only(self, session_id: str, metadata: dict):
            restored.append((session_id, metadata))
            return True

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", _Storage)

    async def fake_executor():
        yield

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor", lambda _key: fake_executor
    )

    class _FailingManager:
        async def submit(self, *_args, **_kwargs):
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FailingManager())

    result = await submit_hitl_resume_run(_approval(), {"approved": True, "values": {}})

    assert result["submitted"] is False
    assert restored == [
        (
            "session-1",
            {"task_status": "waiting_human", "current_run_id": "run-1"},
        )
    ]

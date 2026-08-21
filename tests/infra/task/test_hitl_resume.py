"""HITL interrupt 模式恢复服务测试（issue #218）。"""

from types import SimpleNamespace

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
async def test_submit_resume_lock_prevents_duplicate(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "interrupt", raising=False)
    fake_redis.store[f"{hitl_mod.HITL_RESUME_LOCK_PREFIX}approval-1"] = "other-token"

    result = await submit_hitl_resume_run(_approval(), {"approved": False, "values": {}})
    assert result["submitted"] is False
    assert "其他实例" in result["message"]


@pytest.mark.asyncio
async def test_submit_resume_submits_run_with_hitl_payload(fake_redis, monkeypatch):
    monkeypatch.setattr(hitl_mod.settings, "HITL_MODE", "interrupt", raising=False)

    class _Storage:
        async def get_by_session_id(self, session_id):
            return SimpleNamespace(
                user_id="user-1",
                name="s",
                metadata={
                    "task_status": "waiting_human",
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

    class _FakeManager:
        async def submit(self, *args, **kwargs):
            submitted["args"] = args
            submitted["kwargs"] = kwargs
            return "run-2", "trace-2"

    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeManager())

    resume_value = {"approved": True, "values": {"choice": "a"}}
    result = await submit_hitl_resume_run(
        _approval(
            metadata={
                "mode": "interrupt",
                "run_id": "run-1",
                "thread_id": "session-1",
                "interrupt_id": "interrupt-a",
            }
        ),
        resume_value,
    )
    assert result == {
        "submitted": True,
        "run_id": "run-2",
        "message": "恢复运行已提交",
    }
    assert submitted["args"][0] == "session-1"  # session_id
    assert submitted["args"][1] == "search"  # preserve the session's agent
    assert submitted["args"][2] == ""  # 空消息，不注入新用户输入
    assert submitted["kwargs"]["user_message_written"] is True
    assert submitted["kwargs"]["agent_options"] == {"model": "m"}
    assert submitted["kwargs"]["hitl_resume"] == {
        "approval_id": "approval-1",
        "resume_value": {"interrupt-a": resume_value},
    }


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

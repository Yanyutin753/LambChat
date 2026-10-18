"""Different ARQ dispatch IDs must not execute one detached logical run twice."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import arq_worker
from tests.infra.agent.test_goal_runtime import runtime_redis as runtime_redis
from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore


async def test_two_background_worker_dispatches_share_one_execution_owner(
    monkeypatch, runtime_redis
):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def execute(**kwargs):
        calls.append(kwargs)
        entered.set()
        await release.wait()

    executor = SimpleNamespace(run_task=execute, _update_session_status=AsyncMock())
    manager = SimpleNamespace(
        _tasks={},
        _run_info={},
        _ensure_executor=lambda: executor,
        _mark_run_recoverable_failure=AsyncMock(),
    )
    limiter = _FakeLimiter()
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(arq_worker, "_resolve_executor", lambda _: object())
    monkeypatch.setattr(arq_worker, "_run_watchdog_timeout", lambda: None)
    monkeypatch.setattr(
        "src.infra.task.background_admission.validate_background_run_admission", AsyncMock()
    )
    payload = {
        "session_id": "child",
        "run_id": "background-run",
        "user_id": "u",
        "agent_id": "fast",
        "message": "work",
        "executor_key": "background_agent_stream",
    }
    first_store = _FakePayloadStore(payload, key="dispatch-a")
    second_store = _FakePayloadStore(payload, key="dispatch-b")
    first = asyncio.create_task(
        arq_worker.run_agent_task({"payload_store": first_store}, "dispatch-a")
    )
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        owner_info = manager._run_info["background-run"]
        second = asyncio.create_task(
            arq_worker.run_agent_task({"payload_store": second_store}, "dispatch-b")
        )
        await asyncio.wait_for(asyncio.shield(second), 0.1)
        assert len(calls) == 1
        assert manager._run_info["background-run"] is owner_info
        assert not second_store.deleted
        assert not limiter.acquire_calls and not limiter.release_calls
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)


async def test_background_execution_owner_releases_after_original_worker_finishes(
    monkeypatch, runtime_redis
):
    calls = []
    executor = SimpleNamespace(
        run_task=AsyncMock(side_effect=lambda **kwargs: calls.append(kwargs)),
        _update_session_status=AsyncMock(),
    )
    manager = SimpleNamespace(_tasks={}, _run_info={}, _ensure_executor=lambda: executor)
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(arq_worker, "_resolve_executor", lambda _: object())
    monkeypatch.setattr(arq_worker, "_run_watchdog_timeout", lambda: None)
    monkeypatch.setattr(
        "src.infra.task.background_admission.validate_background_run_admission", AsyncMock()
    )
    payload = {
        "session_id": "child",
        "run_id": "background-run",
        "user_id": "u",
        "agent_id": "fast",
        "message": "work",
        "executor_key": "background_agent_stream",
    }
    for dispatch in ["a", "b"]:
        await arq_worker.run_agent_task(
            {"payload_store": _FakePayloadStore(payload, key=dispatch)}, dispatch
        )
    assert len(calls) == 2
    assert not runtime_redis.values


@pytest.mark.parametrize(
    "boundary", ["on_chat_model_start", "on_llm_start", "on_tool_start", "on_llm_end"]
)
async def test_expired_background_owner_cannot_begin_another_model_or_tool(boundary):
    from src.infra.goal_runtime import BackgroundLeaseCallback
    from src.infra.task.exceptions import TaskInterruptedError

    guard = BackgroundLeaseCallback(
        {"failure": "", "expires_at": asyncio.get_running_loop().time() - 1}
    )
    with pytest.raises(TaskInterruptedError, match="lease"):
        if boundary == "on_llm_end":
            await guard.on_llm_end({})
        else:
            await getattr(guard, boundary)({}, [])


@pytest.mark.parametrize("kind", ["background", "goal"])
@pytest.mark.parametrize("resume_flag", ["interrupted_resume", "hitl_resume"])
async def test_resume_defers_until_previous_execution_lease_expires(
    monkeypatch, runtime_redis, kind, resume_flag
):
    from arq import Retry

    from src.infra.goal_runtime import goal_run_lease

    limiter = _FakeLimiter()
    executor = SimpleNamespace(run_task=AsyncMock(), _update_session_status=AsyncMock())
    owner_info = {"owner": "first-worker"}
    manager = SimpleNamespace(
        _tasks={}, _run_info={"background-run": owner_info}, _ensure_executor=lambda: executor
    )
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    payload = {
        "session_id": "child",
        "run_id": "background-run",
        "user_id": "u",
        "agent_id": "fast",
        "message": "resume",
        "executor_key": "background_agent_stream" if kind == "background" else "agent_stream",
        resume_flag: True,
    }
    goal = {"_persistent_id": "g", "_persistent_version": 1} if kind == "goal" else None
    if goal:
        payload["active_goal"] = goal
    store = _FakePayloadStore(payload, key="recovery-dispatch")
    async with goal_run_lease(
        goal, "background-run", background_identity=("u", "child") if kind == "background" else None
    ):
        # A separate worker does not inherit the first process's ContextVar.
        from src.infra.goal_runtime import GOAL_RUN_LEASE

        token = GOAL_RUN_LEASE.set(None)
        try:
            with pytest.raises(Retry) as error:
                await arq_worker.run_agent_task({"payload_store": store}, "recovery-dispatch")
            assert 60 <= error.value.defer_score / 1000 <= 65
        finally:
            GOAL_RUN_LEASE.reset(token)
        assert not store.deleted
        assert manager._run_info["background-run"] is owner_info
        assert not limiter.acquire_calls and not limiter.release_calls
        executor.run_task.assert_not_awaited()

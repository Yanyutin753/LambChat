from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.goal_runtime import _run_goal, guarded_goal_stream
from src.infra.persistent_goal import GoalService
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_goal_runtime import runtime_redis  # noqa: F401
from tests.infra.agent.test_persistent_goal import Store


async def goal_rounds(monkeypatch):
    service = GoalService(Store())
    await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    monkeypatch.setattr("src.infra.goal_runtime.GoalService", lambda: service)
    monkeypatch.setattr("src.infra.goal_runtime.publish_goal", AsyncMock())
    monkeypatch.setattr("src.infra.goal_runtime.enqueue_goal", AsyncMock())
    sequence = 0

    async def run(result, *, success=True, copies=1):
        nonlocal sequence
        sequence += 1
        current = await service.get("s", "u")
        reserved = await service.reserve("s", "u", current.version)
        assert reserved is not None
        presenter = SimpleNamespace(run_id=reserved.current_run_id)

        async def source():
            for index in range(copies):
                identity = f"call-{sequence}-{index}"
                yield {
                    "event": "tool:start",
                    "data": {
                        "tool": "http_get",
                        "tool_call_id": identity,
                        "timestamp": str(sequence),
                        "args": {"url": "/status"},
                    },
                }
                yield {
                    "event": "tool:result",
                    "data": {
                        "tool": "http_get",
                        "tool_call_id": identity,
                        "timestamp": str(sequence),
                        "success": success,
                        "result": result,
                    },
                }

        async for _ in guarded_goal_stream(
            source(),
            active_goal=_run_goal(reserved),
            session_id="s",
            user_id="u",
            presenter=presenter,
        ):
            pass
        assert presenter.persistent_goal_metrics.tool_count == copies
        return await service.get("s", "u")

    return run


async def test_identical_poll_results_block_after_three_stagnant_rounds(monkeypatch):
    run = await goal_rounds(monkeypatch)
    first = await run({"status": "pending", "timestamp": "one"})
    second = await run({"timestamp": "two", "status": "pending"}, copies=3)
    third = await run('{"status":"pending","timestamp":"three"}')
    assert first.stagnant_turns == 0
    assert second.stagnant_turns == 1
    assert third.status == "active"
    fourth = await run({"status": "pending"})
    assert fourth.status == "blocked"
    assert (
        first.last_progress_signature
        == second.last_progress_signature
        == third.last_progress_signature
    )
    assert len(first.last_progress_signature) == 64


@pytest.mark.parametrize(
    "result,success",
    [
        ({"message": "failed"}, False),
        ({"status": "error", "message": "provider failed"}, True),
        ({"isError": True, "content": [{"type": "text", "text": "failed"}]}, True),
    ],
)
async def test_failed_tools_do_not_count_as_progress(monkeypatch, result, success):
    run = await goal_rounds(monkeypatch)
    first = await run(result, success=success)
    second = await run(result, success=success)
    assert first.stagnant_turns == 1
    assert second.status == "active"
    third = await run(result, success=success)
    assert third.status == "blocked"
    assert third.last_progress_signature == ""


async def test_changed_observation_resets_stagnation_without_self_reported_progress(monkeypatch):
    run = await goal_rounds(monkeypatch)
    first = await run({"status": "pending", "completed": 0})
    second = await run({"status": "pending", "completed": 0})
    changed = await run({"status": "pending", "completed": 1})
    assert second.stagnant_turns == 1
    assert changed.status == "active"
    assert changed.stagnant_turns == 0
    assert changed.last_progress_signature != first.last_progress_signature


async def test_failed_round_does_not_erase_previous_observation(monkeypatch):
    run = await goal_rounds(monkeypatch)
    first = await run({"status": "pending"})
    failed = await run({"status": "error"})
    repeated = await run({"status": "pending"})
    assert failed.last_progress_signature == first.last_progress_signature
    assert repeated.status == "active"
    assert (await run({"status": "pending"})).status == "blocked"

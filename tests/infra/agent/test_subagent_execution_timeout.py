"""Model-selected child deadlines survive recovery and conversation continuation."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.infra.agent import subagent_sessions as module
from src.infra.tool.subagent_tool import create_subagent_tools
from tests.infra.agent.test_subagent_controls import _sessions


def test_task_exposes_optional_bounded_execution_budget():
    sessions, _, _ = _sessions()
    task = next(tool for tool in create_subagent_tools(sessions) if tool.name == "task")
    schema = task.tool_call_schema.model_json_schema()
    budget = schema["properties"]["execution_timeout_seconds"]
    assert budget["default"] == 7200
    assert budget["minimum"] == 10
    assert budget["maximum"] == 7200
    assert "execution_timeout_seconds" not in schema["required"]


@pytest.mark.parametrize("budget", [True, 9, 7201, 30.0, "30", float("inf"), float("nan")])
def test_task_schema_rejects_invalid_execution_budget(budget):
    sessions, _, _ = _sessions()
    task = next(tool for tool in create_subagent_tools(sessions) if tool.name == "task")
    with pytest.raises(ValueError, match="execution_timeout_seconds"):
        task.tool_call_schema.model_validate(
            {
                "description": "Review",
                "subagent_type": "reviewer",
                "execution_timeout_seconds": budget,
            }
        )


async def test_task_forwards_and_reports_selected_execution_budget():
    sessions, _, release = _sessions()
    task = next(tool for tool in create_subagent_tools(sessions) if tool.name == "task")
    runtime = SimpleNamespace(state={}, config={}, tool_call_id="budget-tool")
    try:
        output = await task.coroutine(
            description="Review",
            subagent_type="reviewer",
            runtime=runtime,
            background=True,
            execution_timeout_seconds=90,
        )
        value = json.loads(output.update["messages"][0].content)
        assert value["execution_timeout_seconds"] == 90
        key = value["subagent_id"]
        assert output.update["subagent_sessions"][key]["execution_timeout_seconds"] == 90
    finally:
        release.set()
        await sessions.close()


@pytest.mark.parametrize(
    "budget", [True, False, 0, -1, 9, 7201, 10.5, "30", float("inf"), float("nan")]
)
async def test_start_rejects_invalid_execution_budget_without_creating_child(budget):
    sessions, _, _ = _sessions()
    with pytest.raises(ValueError, match="execution_timeout_seconds"):
        await sessions.start(
            "reviewer",
            "Review",
            call_id="invalid",
            config={},
            background=True,
            execution_timeout_seconds=budget,
        )
    assert sessions.records == {}
    assert sessions.jobs == {}


async def test_selected_execution_budget_is_enforced_and_persisted(monkeypatch):
    real_timeout = asyncio.timeout
    deadlines = []

    def scaled_timeout(seconds):
        deadlines.append(seconds)
        return real_timeout(seconds / 1000)

    monkeypatch.setattr(module.asyncio, "timeout", scaled_timeout)
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer",
            "Review",
            call_id="enforced",
            config={},
            background=True,
            execution_timeout_seconds=30,
        )
        key = started["subagent_id"]
        await asyncio.wait_for(sessions.jobs[key], 1)
        assert deadlines[0] == 30
        assert sessions.result(key)["status"] == "timed_out"
        assert graphs[key].values["subagent_outcome"]["execution_timeout_seconds"] == 30
        restored, _, _ = _sessions()
        restored.restore(sessions.snapshot())
        assert restored.result(key)["execution_timeout_seconds"] == 30
    finally:
        release.set()
        await sessions.close()


async def test_restored_execution_subtracts_already_consumed_budget(monkeypatch):
    real_timeout = asyncio.timeout
    deadlines = []

    def record_timeout(seconds):
        deadlines.append(seconds)
        return real_timeout(seconds)

    monkeypatch.setattr(module.asyncio, "timeout", record_timeout)
    sessions, _, release = _sessions()
    sessions.restore(
        {
            "child": {
                "subagent_type": "reviewer",
                "status": "running",
                "description": "Review",
                "execution_timeout_seconds": 30,
                "execution_seconds": 29.99,
            }
        }
    )
    try:
        await sessions._prepare("child", {})
        await asyncio.wait_for(sessions._run("child", {"messages": []}), 0.5)
        assert deadlines[0] == pytest.approx(0.01)
        assert sessions.result("child")["status"] == "timed_out"
        assert sessions.records["child"]["execution_seconds"] >= 30
    finally:
        release.set()
        await sessions.close()


def test_legacy_checkpoint_retains_default_execution_budget():
    sessions, _, _ = _sessions()
    sessions.restore({"old": {"subagent_type": "reviewer", "status": "running"}})
    assert sessions.result("old")["execution_timeout_seconds"] == 7200


@pytest.mark.parametrize("budget", [True, 0, -10, 7201, "30", float("inf"), float("nan")])
def test_invalid_restored_execution_budget_uses_server_default(budget):
    sessions, _, _ = _sessions()
    sessions.restore(
        {
            "child": {
                "subagent_type": "reviewer",
                "status": "running",
                "execution_timeout_seconds": budget,
            }
        }
    )
    assert sessions.result("child")["execution_timeout_seconds"] == 7200


async def test_messages_and_replayed_task_preserve_budget_and_continuation_resets_elapsed():
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer",
            "Review",
            call_id="continuation",
            config={},
            background=True,
            execution_timeout_seconds=60,
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()
        sessions.records[key]["execution_seconds"] = 5
        job = sessions.jobs[key]
        await sessions.send(key, "More context", config={}, background=True)
        repeated = await sessions.start(
            "reviewer",
            "Review",
            call_id="continuation",
            config={},
            background=True,
            execution_timeout_seconds=600,
        )
        assert repeated["execution_timeout_seconds"] == 60
        assert sessions.records[key]["execution_seconds"] == 5
        assert sessions.jobs[key] is job
        release.set()
        await job
        continued = await sessions.send(key, "Next question", config={}, background=True)
        assert continued["execution_timeout_seconds"] == 60
        assert sessions.records[key]["execution_seconds"] == 0
        assert sessions.jobs[key] is not job
        await sessions.jobs[key]
    finally:
        release.set()
        await sessions.close()

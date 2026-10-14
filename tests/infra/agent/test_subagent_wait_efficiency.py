"""Long, event-driven waits avoid polling and repeated final-report tokens."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.infra.agent import subagent_sessions as module
from src.infra.agent.subagent_sessions import SubagentSessions
from src.infra.tool.subagent_tool import create_subagent_tools
from tests.infra.agent.test_subagent_controls import _sessions


def test_wait_defaults_and_public_timeout_range():
    assert module.SUBAGENT_WAIT_TIMEOUT_SECONDS == 120
    assert module.SUBAGENT_WAIT_MIN_SECONDS == 10
    assert module.SUBAGENT_WAIT_MAX_SECONDS == 300
    sessions, _, _ = _sessions()
    wait = next(tool for tool in create_subagent_tools(sessions) if tool.name == "wait_subagent")
    schema = wait.tool_call_schema.model_json_schema()["properties"]
    assert schema["timeout_seconds"]["default"] == 120
    assert schema["timeout_seconds"]["minimum"] == 10
    assert schema["timeout_seconds"]["maximum"] == 300


async def test_wait_deadline_is_explicit_and_does_not_timeout_child(monkeypatch):
    monkeypatch.setattr(module, "SUBAGENT_WAIT_TIMEOUT_SECONDS", 0.01)
    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="bounded-new", config={}, background=True
        )
        key = started["subagent_id"]
        await graphs[key].entered.wait()
        value = await sessions.wait(key, config={})
        assert value["status"] == "running"
        assert value["wait_timed_out"] is True
        assert value["terminal"] is False
        assert "timed_out" != value["status"]
        assert "longer" in value["guidance"]
        assert not sessions.jobs[key].done()
    finally:
        release.set()
        await sessions.close()


async def test_timeout_argument_uses_requested_bounded_deadline(monkeypatch):
    sessions, graphs, release = _sessions()
    durations = []
    original = asyncio.timeout

    def shortened(seconds):
        durations.append(seconds)
        return original(0.01)

    monkeypatch.setattr(module.asyncio, "timeout", shortened)
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="timeout-argument", config={}, background=True
        )
        key = started["subagent_id"]
        # The wrapper's shortened execution deadline must not affect this test's mocked job.
        sessions.jobs[key].cancel()
        await asyncio.gather(sessions.jobs[key], return_exceptions=True)
        sessions.records[key]["status"] = "running"
        sessions.jobs[key] = asyncio.create_task(release.wait())
        value = await sessions.wait(key, config={}, timeout_seconds=240)
        assert durations[-1] == 240
        assert value["wait_timed_out"] is True
    finally:
        release.set()
        await sessions.close()


async def test_stale_mail_flag_cannot_cause_immediate_wait_loop(monkeypatch):
    monkeypatch.setattr(module, "SUBAGENT_WAIT_TIMEOUT_SECONDS", 0.01)
    sessions, graphs, release = _sessions()
    try:
        result = await sessions.start(
            "reviewer", "work", call_id="stale-mail", config={}, background=True
        )
        key = result["subagent_id"]
        await graphs[key].entered.wait()
        sessions.parent_mail.set()
        value = await sessions.wait(key, config={})
        assert value["wait_timed_out"] is True
        assert value.get("messages_pending") is not True
        assert not sessions.parent_mail.is_set()
    finally:
        release.set()
        await sessions.close()


async def test_collected_final_result_is_not_repeated_and_needs_no_graph_reload():
    async def forbidden(*args):
        raise AssertionError("Collected final state must not reload a graph")

    sessions = SubagentSessions(
        session_id="p", user_id="u", build_graph=forbidden, checkpointer=None
    )
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "completed",
        "result": "BIG_FINAL_REPORT" * 2000,
        "collected": True,
        "pending": [],
    }
    value = await sessions.wait("child", config={})
    assert value["status"] == "completed"
    assert value["terminal"] is True
    assert value["result_collected"] is True
    assert value["unchanged"] is True
    assert "result" not in value
    assert len(json.dumps(value)) < 500
    assert "already" in value["guidance"]


async def test_unknown_and_terminal_ids_return_stop_polling_guidance():
    async def forbidden(*args):
        raise AssertionError("Terminal or missing child must not open a graph")

    sessions = SubagentSessions(
        session_id="p", user_id="u", build_graph=forbidden, checkpointer=None
    )
    missing = await sessions.wait("missing", config={})
    assert missing["status"] == "error"
    assert missing["terminal"] is True
    assert missing["reason"] == "not_found"
    assert "list_subagents" in missing["guidance"]
    assert "again" in missing["guidance"]
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "timed_out",
        "error": "deadline",
        "collected": True,
    }
    terminal = await sessions.wait("child", config={})
    assert terminal["status"] == "timed_out"
    assert terminal["wait_timed_out"] is False
    assert terminal["terminal"] is True


async def test_wait_tool_forwards_timeout_and_suppresses_collected_report():
    captured = []

    class Sessions:
        records = {"child": {"status": "completed", "collected": True}}

        def restore(self, records):
            pass

        def snapshot(self):
            return self.records

        async def wait(self, key, **kwargs):
            captured.append(kwargs)
            return {
                "subagent_id": key,
                "status": "completed",
                "result_collected": True,
                "unchanged": True,
            }

    tool = next(tool for tool in create_subagent_tools(Sessions()) if tool.name == "wait_subagent")
    runtime = SimpleNamespace(state={}, config={}, tool_call_id="wait-1")
    output = await tool.coroutine(subagent_id="child", timeout_seconds=240, runtime=runtime)
    assert captured[0]["timeout_seconds"] == 240
    value = json.loads(output.update["messages"][0].content)
    assert "result" not in value
    assert value["result_collected"] is True


async def test_first_wait_delivers_report_once_repeated_wait_drops_report_and_evidence():
    from langchain_core.messages import AIMessage

    sessions, graphs, release = _sessions()
    try:
        started = await sessions.start(
            "reviewer", "work", call_id="deliver-once", config={}, background=True
        )
        key = started["subagent_id"]
        release.set()
        await sessions.jobs[key]
        report = "FINAL_REPORT_CONTENT" * 2000
        graphs[key].values = {
            "messages": [AIMessage(content=report)],
            "evidence": [{"scope_version": "current"}],
        }
        wait = next(
            tool for tool in create_subagent_tools(sessions) if tool.name == "wait_subagent"
        )
        first = await wait.coroutine(
            subagent_id=key, runtime=SimpleNamespace(state={}, config={}, tool_call_id="first-wait")
        )
        message = first.update["messages"][0]
        assert json.loads(message.content)["result"] == report
        assert message.additional_kwargs["lambchat_subagent_evidence"] == [
            {"scope_version": "current"}
        ]
        assert sessions.records[key]["collected"] is True
        sessions.graphs.clear()

        async def forbidden(*args):
            raise AssertionError("No checkpoint/model/authorization reload for a collected result")

        sessions.build_graph = forbidden
        repeated = await wait.coroutine(
            subagent_id=key,
            runtime=SimpleNamespace(state={}, config={}, tool_call_id="repeat-wait"),
        )
        compact = repeated.update["messages"][0]
        assert len(compact.content) < 500
        assert report not in compact.content
        assert compact.additional_kwargs["lambchat_subagent_unchanged"] is True
        assert compact.additional_kwargs["lambchat_subagent_evidence"] == []
    finally:
        release.set()
        await sessions.close()


@pytest.mark.parametrize("timeout", [-1, 0, 9, 301, True, 1.5])
async def test_direct_wait_rejects_polling_spam_and_unbounded_timeout(timeout):
    sessions, _, _ = _sessions()
    with pytest.raises(ValueError, match="10 to 300"):
        await sessions.wait("missing", config={}, timeout_seconds=timeout)


async def test_timeout_partial_handoff_preserves_source_evidence_for_parent():
    from src.infra.agent.middleware.evidence import EvidenceMiddleware
    from src.infra.agent.middleware.subagent_result_handoff import SubagentResultHandoffMiddleware

    async def writer(record, content):
        return f"/evidence/{record['evidence_id']}.json"

    parent = EvidenceMiddleware(
        session_id="controls", run_id="parent", scope_version="v", writer=writer
    )
    evidence = {
        "evidence_id": "child-proof",
        "session_id": "controls",
        "run_id": "child-run",
        "scope_version": "v",
        "status": "observed",
        "tool_call_id": "read",
        "source_ref": "/evidence/child-proof.json",
        "content_sha256": "a" * 64,
        "evidence_clock_token": parent.clock.token,
        "evidence_clock_generation": parent.clock.generation,
    }
    sessions, _, _ = _sessions()
    sessions.records["child"] = {
        "subagent_type": "reviewer",
        "status": "timed_out",
        "description": "review",
        "partial_result": True,
        "result": "Partial completed read",
        "error": "deadline",
        "evidence": [evidence],
    }
    wait = next(t for t in create_subagent_tools(sessions) if t.name == "wait_subagent")
    output = await wait.coroutine(
        subagent_id="child", runtime=SimpleNamespace(state={}, config={}, tool_call_id="wait")
    )
    writes = []

    class Backend:
        async def awrite(self, path, content):
            writes.append(content)
            return SimpleNamespace(path=path, error=None)

    handoff = SubagentResultHandoffMiddleware(backend=Backend())
    request = SimpleNamespace(
        tool_call={"name": "wait_subagent", "id": "wait", "args": {}},
        state={},
        runtime=SimpleNamespace(state={}),
    )

    async def handler(_request):
        return output

    async def with_handoff(req):
        return await handoff.awrap_tool_call(req, handler)

    imported = await parent.awrap_tool_call(request, with_handoff)
    assert evidence in imported.update["evidence"]
    assert "/evidence/child-proof.json" in writes[0]
    message = imported.update["messages"][0]
    assert json.loads(message.content)["status"] == "timed_out"
    assert message.status == "error"

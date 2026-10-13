import json
from datetime import datetime, timezone

from scripts.seed_subagent_preview import build_records


def test_role_preview_continues_one_subagent_across_two_chat_turns():
    records = build_records("owner", datetime(2026, 10, 13, tzinfo=timezone.utc))
    traces = records["traces"][:2]
    assert len(traces) == 2
    assert traces[0]["session_id"] == traces[1]["session_id"]
    assert traces[0]["run_id"] != traces[1]["run_id"]
    first, second = [trace["events"] for trace in traces]
    starts = [event["data"] for event in first if event["event_type"] == "tool:start"]
    assert [data["tool"] for data in starts] == [
        "search_persona_presets",
        "send_subagent_message",
        "wait_subagent",
    ]
    calls = [
        event["data"]
        for trace in traces
        for event in trace["events"]
        if event["event_type"] == "agent:call"
    ]
    assert len(calls) == 2
    assert calls[0]["agent_id"] == calls[1]["agent_id"]
    assert all(call["depth"] == 1 for call in calls)
    assert [event["data"]["tool"] for event in second if event["event_type"] == "tool:start"] == [
        "send_subagent_message"
    ]
    live = next(
        event["data"]
        for event in first
        if event["event_type"] == "tool:result" and event["data"]["tool"] == "send_subagent_message"
    )
    assert json.loads(live["result"])["status"] == "running"
    assert any("SOP" in event["data"].get("content", "") for event in first)
    assert any("QC-DEMO-42" in event["data"].get("content", "") for event in second)


def test_generic_preview_searches_before_fallback_and_shows_a_failed_continuation():
    trace = build_records("owner", datetime.now(timezone.utc))["traces"][2]
    tools = [event["data"] for event in trace["events"] if event["event_type"] == "tool:start"]
    assert [tool["tool"] for tool in tools] == [
        "search_persona_presets",
        "send_subagent_message",
    ]
    call = next(event for event in trace["events"] if event["event_type"] == "agent:call")
    assert call["data"]["agent_name"] == "通用代理"
    results = [event["data"] for event in trace["events"] if event["event_type"] == "tool:result"]
    assert json.loads(results[0]["result"])["presets"] == []
    assert json.loads(results[-1]["result"])["status"] == "error"
    assert results[-1]["success"] is False


def test_preview_is_repeatable_owner_scoped_and_only_adds_mock_chat_documents():
    now = datetime.now(timezone.utc)
    records = build_records("owner", now)
    assert set(records) == {"sessions", "traces", "shared_sessions"}
    assert len(records["sessions"]) == len(records["shared_sessions"]) == 3
    assert all(doc["preview_owner"] == "owner" for docs in records.values() for doc in docs)
    again, other = build_records("owner", now), build_records("other", now)
    for collection, docs in records.items():
        assert [doc["_id"] for doc in docs] == [doc["_id"] for doc in again[collection]]
        assert {str(doc["_id"]) for doc in docs}.isdisjoint(
            str(doc["_id"]) for doc in other[collection]
        )
    assert {trace["session_id"] for trace in records["traces"]} == {
        session["session_id"] for session in records["sessions"]
    }
    for trace in records["traces"]:
        assert trace["events"][-1]["event_type"] == "done"
        assert trace["event_count"] == len(trace["events"])
        starts = {
            event["data"]["tool_call_id"]
            for event in trace["events"]
            if event["event_type"] == "tool:start"
        }
        results = {
            event["data"]["tool_call_id"]
            for event in trace["events"]
            if event["event_type"] == "tool:result"
        }
        assert starts == results


def test_parent_message_preview_shows_the_original_child_question_and_reply():
    records = build_records("owner", datetime.now(timezone.utc))
    events = records["traces"][3]["events"]
    starts = [event["data"] for event in events if event["event_type"] == "tool:start"]
    messages = [data for data in starts if data["tool"] == "send_parent_message"]
    assert len(messages) == 2
    sent, received = messages
    assert sent["depth"] == 1
    assert received["depth"] == 0
    assert received["args"]["direction"] == "received"
    assert sent["args"]["message"] == received["args"]["message"]
    assert "是否只检查权限" in received["args"]["message"]
    reply = next(data for data in starts if data["tool"] == "send_subagent_message")
    assert reply["args"]["subagent_id"] == received["args"]["subagent_id"]
    assert events[-1]["event_type"] == "done"

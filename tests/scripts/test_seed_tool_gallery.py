import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.seed_tool_gallery import build_records, tool_cases


def test_gallery_covers_all_inline_tool_routes_and_special_events():
    source = Path("frontend/src/components/chat/ChatMessage/MessagePartRenderer.tsx").read_text()
    expected = set(re.findall(r'part.name === "([a-z_]+)"', source)) - {"todo_write", "write_todos"}
    assert expected <= {case[1] for case in tool_cases()}
    records = build_records("owner", datetime.now(timezone.utc), ["mock-one", "mock-two"])
    assert set(records) == {"sessions", "traces"}
    events = [e for trace in records["traces"] for e in trace["events"]]
    assert {"todo:updated", "agent:call", "agent:result"} <= {e["event_type"] for e in events}
    assert all(d["preview_owner"] == "owner" for docs in records.values() for d in docs)
    starts = [e["data"] for e in events if e["event_type"] == "tool:start"]
    results = [e["data"] for e in events if e["event_type"] == "tool:result"]
    assert {e["tool_call_id"] for e in starts} == {e["tool_call_id"] for e in results}
    assert {"mock-one:preview_search", "mock-two:preview_search"} <= {e["tool"] for e in starts}
    assert all(t["events"][-1]["event_type"] == "done" for t in records["traces"])
    assert all(t["event_count"] == len(t["events"]) for t in records["traces"])


def test_gallery_ids_are_repeatable_and_owner_scoped():
    now = datetime.now(timezone.utc)
    a = build_records("a", now, ["example"])
    again = build_records("a", now, ["example"])
    b = build_records("b", now, ["example"])
    for coll in a:
        assert [d["_id"] for d in a[coll]] == [d["_id"] for d in again[coll]]
        assert {d["_id"] for d in a[coll]}.isdisjoint(d["_id"] for d in b[coll])


def test_memory_and_mcp_samples_have_readable_metadata():
    memory = next(c[3] for c in tool_cases() if c[1] == "memory_recall")["memories"][0]
    assert memory["text"] and memory["type"] and memory["created_at"]
    records = build_records("owner", datetime.now(timezone.utc), ["demo"])
    results = [
        e["data"]
        for t in records["traces"]
        for e in t["events"]
        if e["event_type"] == "tool:result"
    ]
    result = next(r["result"] for r in results if r["tool"] == "demo:preview_search")
    assert result["content"][0]["text"].startswith("## ")


def test_search_and_history_fixtures_use_readable_tool_contracts():
    cases = {c[1]: c[3] for c in tool_cases()}
    assert cases["search_tools"].startswith("Found 2 tool(s).")
    assert "Name:" in cases["search_skills"]
    assert cases["search_conversation_history"]["items"][0]["session_name"]
    turn = cases["get_conversation_detail"]["turns"][0]
    assert turn["user_message"] and turn["assistant_final"]
    assert cases["create_persona_preset"]["preset"]["system_prompt"]

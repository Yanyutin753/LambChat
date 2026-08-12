from __future__ import annotations

from copy import deepcopy

from src.infra.session.history_compaction import compact_consecutive_message_chunks


def _chunk(
    content: str,
    *,
    seq: int,
    trace_id: str = "trace-1",
    run_id: str = "run-1",
    agent_id: str = "main",
    depth: int = 0,
    **extra_data,
) -> dict:
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "event_type": "message:chunk",
        "data": {
            "content": content,
            "agent_id": agent_id,
            "depth": depth,
            **extra_data,
        },
        "seq": seq,
        "timestamp": f"2026-08-12T00:00:{seq:02d}Z",
    }


def test_compacts_only_consecutive_compatible_message_chunks() -> None:
    tool_event = {
        "trace_id": "trace-1",
        "run_id": "run-1",
        "event_type": "tool:start",
        "data": {"name": "search"},
        "seq": 3,
    }
    events = [
        _chunk("a", seq=1),
        _chunk("b", seq=2),
        tool_event,
        _chunk("c", seq=4),
    ]

    compacted = compact_consecutive_message_chunks(events)

    assert [event["event_type"] for event in compacted] == [
        "message:chunk",
        "tool:start",
        "message:chunk",
    ]
    assert [
        event["data"]["content"] for event in compacted if event["event_type"] == "message:chunk"
    ] == ["ab", "c"]
    assert compacted[0]["seq"] == 2
    assert compacted[0]["timestamp"] == "2026-08-12T00:00:02Z"


def test_does_not_merge_across_identity_or_data_boundaries() -> None:
    events = [
        _chunk("a", seq=1),
        _chunk("b", seq=2, trace_id="trace-2"),
        _chunk("c", seq=3, trace_id="trace-2", run_id="run-2"),
        _chunk("d", seq=4, trace_id="trace-2", run_id="run-2", depth=1),
        _chunk("e", seq=5, trace_id="trace-2", run_id="run-2", depth=1, agent_id="sub"),
        _chunk(
            "f",
            seq=6,
            trace_id="trace-2",
            run_id="run-2",
            depth=1,
            agent_id="sub",
            channel="analysis",
        ),
    ]

    compacted = compact_consecutive_message_chunks(events)

    assert [event["data"]["content"] for event in compacted] == ["a", "b", "c", "d", "e", "f"]


def test_compaction_does_not_mutate_inputs() -> None:
    events = [_chunk("a", seq=1), _chunk("b", seq=2)]
    original = deepcopy(events)

    compacted = compact_consecutive_message_chunks(events)

    assert events == original
    assert compacted is not events
    assert compacted[0] is not events[0]

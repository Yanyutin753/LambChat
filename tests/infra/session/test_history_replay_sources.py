"""Stable stream provenance survives transport and persisted compaction."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from src.infra.session.dual_writer import DualEventWriter
from src.infra.session.history_compaction import compact_history_events


def _event(source, content, *, trace="trace-1", kind="message:chunk", **extra):
    return {
        "trace_id": trace,
        "run_id": "same-run",
        "event_type": kind,
        "timestamp": "2026-10-15T00:00:00Z",
        "seq": 1,
        "data": {"content": content, "_source_id": source, "_source_trace_id": trace, **extra},
    }


@pytest.mark.parametrize("mark_merges", [False, True])
def test_compaction_keeps_exact_source_coverage_without_changing_text(mark_merges):
    events = [_event(f"source-{index}", str(index)) for index in range(1000)]
    original = deepcopy(events)
    compacted = compact_history_events(events, mark_merges=mark_merges)
    assert len(compacted) == 1
    assert compacted[0]["data"]["content"] == "".join(str(index) for index in range(1000))
    assert compacted[0]["data"]["_source_ids"] == [f"source-{index}" for index in range(1000)]
    assert events == original
    # Background compaction followed by transport compaction retains every source once.
    again = compact_history_events([*compacted, _event("source-tail", "tail")])
    assert again[0]["data"]["_source_ids"] == [
        *[f"source-{index}" for index in range(1000)],
        "source-tail",
    ]


def test_interleaved_blocks_keep_distinct_coverage_and_trace_boundaries():
    events = [
        _event("think-1", "A", kind="thinking", thinking_id="thought"),
        _event("args-1", "{", kind="tool:args:chunk", tool_call_id="tool"),
        _event("think-2", "B", kind="thinking", thinking_id="thought"),
        _event("args-2", "}", kind="tool:args:chunk", tool_call_id="tool"),
        _event("retry", "C", trace="trace-2", kind="thinking", thinking_id="thought"),
    ]
    compacted = compact_history_events(events)
    assert len(compacted) == 3
    assert compacted[0]["data"]["_source_ids"] == ["think-1", "think-2"]
    assert compacted[1]["data"]["_source_ids"] == ["args-1", "args-2"]
    assert compacted[2]["trace_id"] == "trace-2"
    assert compacted[2]["data"]["content"] == "C"


async def test_writer_uses_one_fresh_source_for_redis_and_mongo_without_mutating_input():
    writer = DualEventWriter()
    writer._write_to_redis_direct = AsyncMock(return_value=True)
    writer._flush_event.clear()
    original = {"content": "same", "_source_id": "untrusted", "_source_ids": ["untrusted"]}
    for _ in range(2):
        await writer.write_event(
            "session", "message:chunk", original, trace_id="trace-1", run_id="run"
        )
    redis_data = [
        json.loads(call.args[1]["data"]) for call in writer._write_to_redis_direct.await_args_list
    ]
    mongo_data = [item[2] for item in writer._mongo_buffer]
    assert redis_data == mongo_data
    assert redis_data[0]["_source_id"] != redis_data[1]["_source_id"]
    assert all(data["_source_id"] != "untrusted" for data in redis_data)
    assert all(data["_source_trace_id"] == "trace-1" for data in redis_data)
    assert all("_source_ids" not in data for data in redis_data)
    assert original == {"content": "same", "_source_id": "untrusted", "_source_ids": ["untrusted"]}

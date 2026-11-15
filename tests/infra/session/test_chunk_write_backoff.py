"""A broken trace must neither flood MongoDB nor disappear from durability barriers."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.session import dual_writer


def item(trace="broken", attempts=0):
    return (
        trace,
        "message:chunk",
        {"content": "keep"},
        "session",
        "run",
        datetime.now(),
        1,
        False,
        False,
        attempts,
    )


async def test_repeated_failure_backs_off_without_blocking_other_traces_or_dropping_events(
    monkeypatch,
):
    monkeypatch.setattr(dual_writer.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", True)
    monkeypatch.setattr(dual_writer.settings, "SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY", False)
    now = [1000.0]
    monkeypatch.setattr(dual_writer.time, "monotonic", lambda: now[0])
    writer = dual_writer.DualEventWriter()
    calls = []

    async def append(trace, events, start):
        calls.append(trace["trace_id"])
        if trace["trace_id"] == "broken":
            raise RuntimeError("document too large")
        return True

    writer._trace = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        append_events_to_chunks=append,
    )
    for attempt in range(100):
        batch = writer._mongo_buffer or [item(attempts=50)]
        writer._mongo_buffer = []
        await writer._flush_mongo_batch(batch + ([item("healthy")] if attempt == 2 else []))
    assert calls.count("broken") <= 2
    assert calls.count("healthy") == 1
    assert len(writer._mongo_buffer) == 1
    assert writer._mongo_buffer[0][2] == {"content": "keep"}
    now[0] += 31
    batch, writer._mongo_buffer = writer._mongo_buffer, []
    await writer._flush_mongo_batch(batch)
    assert calls.count("broken") >= 2
    assert len(writer._mongo_buffer) == 1


async def test_full_buffer_does_not_grow_when_flush_cannot_make_progress(monkeypatch):
    from tests.infra.test_dual_writer_limits import _FakeRedis

    monkeypatch.setattr(dual_writer, "_get_mongo_buffer_max", lambda: 4)
    writer = dual_writer.DualEventWriter()
    writer._redis = _FakeRedis()
    writer._flush_event.clear()
    writer._mongo_buffer = [item() for _ in range(4)]
    writer.flush_mongo_buffer = AsyncMock()
    with pytest.raises(RuntimeError, match="MongoDB event buffer is full"):
        await writer.write_event(
            session_id="session",
            event_type="message:chunk",
            data={"content": "new"},
            trace_id="broken",
            run_id="run",
        )
    assert len(writer._mongo_buffer) == 4

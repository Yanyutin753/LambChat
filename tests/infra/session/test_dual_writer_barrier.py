from datetime import datetime

import pytest

from src.infra.session.dual_writer import DualEventWriter
from src.infra.session.dual_writer_helpers import _with_chunk_retry_metadata


async def test_chunk_retry_deadlines_are_bounded_without_discarding_failed_events(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.session import dual_writer

    monkeypatch.setattr(dual_writer.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", True)
    monkeypatch.setattr(dual_writer.settings, "SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY", False)
    writer = DualEventWriter()
    writer._trace = AsyncMock()
    writer._trace.collection.find_one.return_value = None
    writer._trace.append_events_to_chunks.side_effect = OSError("unavailable")
    batch = [
        _with_chunk_retry_metadata(
            (f"trace-{i}", "message:chunk", {"content": str(i)}, "s", "r", datetime.now()),
            reserved_start_seq=1,
            skip_legacy=False,
        )
        for i in range(300)
    ]
    await writer._flush_mongo_batch(batch)
    assert len(writer._mongo_retry_after) <= 256
    assert {item[0] for item in writer._mongo_buffer} == {item[0] for item in batch}
    assert "trace-299" in writer._mongo_retry_after


async def test_durability_barrier_does_not_require_events_arriving_during_flush(monkeypatch):
    writer = DualEventWriter()
    old = ("trace", "message:chunk", {"content": "old"}, "session", "run", datetime.now())
    new = ("trace", "message:chunk", {"content": "new"}, "session", "run", datetime.now())
    writer._mongo_buffer = [old]

    async def flush():
        writer._mongo_buffer = [new]

    monkeypatch.setattr(writer, "_do_flush_locked", flush)
    await writer.flush_mongo_buffer(require_trace_id="trace")
    assert writer._mongo_buffer == [new]


async def test_durability_barrier_still_rejects_failed_original_event_after_requeue(monkeypatch):
    writer = DualEventWriter()
    old = ("trace", "message:chunk", {"content": "old"}, "session", "run", datetime.now())
    writer._mongo_buffer = [old]

    async def flush():
        writer._mongo_buffer = [
            _with_chunk_retry_metadata(old, reserved_start_seq=1, skip_legacy=True)
        ]

    monkeypatch.setattr(writer, "_do_flush_locked", flush)
    with pytest.raises(RuntimeError, match="1 pending events"):
        await writer.flush_mongo_buffer(require_trace_id="trace")

from datetime import datetime

import pytest

from src.infra.session.dual_writer import DualEventWriter
from src.infra.session.dual_writer_helpers import _with_chunk_retry_metadata


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

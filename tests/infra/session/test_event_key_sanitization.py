from __future__ import annotations

"""Regression tests: unwritable event data keys must not poison the flush loop.

Production symptom (k3s, single-node dual pods): a scheduled search-agent task
emitted tool:result events whose ``data.result`` embedded external structured
content containing a field name with a '.'. The chunked write path builds a
pipeline ``$set`` update, and MongoDB rejects documents whose field paths
contain '.' ("Invalid $set :: caused by :: FieldPath ... may not contain
'.'", code 40353/16412). The buffered events could never be written and the
flush loop retried them forever (~730 ERROR logs in 13h, event_revision
churned to 950+, trace completion blocked with "Mongo event buffer still has
N pending events").
"""

import asyncio
from typing import Any

import pytest

from src.infra.session import dual_writer as dual_writer_module
from src.infra.session.dual_writer import DualEventWriter
from src.infra.session.dual_writer_helpers import (
    _buffer_item_attempts,
    _sanitize_event_data_for_mongo,
)

# ---------------------------------------------------------------------------
# Key sanitizer (pure function)
# ---------------------------------------------------------------------------


def test_sanitizer_rewrites_dotted_keys_recursively() -> None:
    data = {
        "content": "ok",
        "structured_content": {"author.name": "x", "nested": {"a.b": 1, "c": 2}},
    }
    sanitized = _sanitize_event_data_for_mongo(data)
    assert sanitized["structured_content"]["author_name"] == "x"
    assert sanitized["structured_content"]["nested"]["a_b"] == 1
    assert sanitized["structured_content"]["nested"]["c"] == 2


def test_sanitizer_rewrites_dollar_prefixed_and_empty_keys() -> None:
    data = {"$ref": 1, "": 2, "list": [{"$type": "a", ".t": "b"}]}
    sanitized = _sanitize_event_data_for_mongo(data)
    assert sanitized["_ref"] == 1
    assert sanitized["_"] == 2
    assert sanitized["list"][0] == {"_type": "a", "_t": "b"}


def test_sanitizer_returns_clean_data_object_unchanged() -> None:
    data = {"content": "hello", "result": {"text": "...", "blocks": [{"type": "text"}]}}
    assert _sanitize_event_data_for_mongo(data) is data


# ---------------------------------------------------------------------------
# write_event buffers sanitized data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_event_buffers_sanitized_data(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = object.__new__(DualEventWriter)
    writer._mongo_lock = asyncio.Lock()
    writer._mongo_buffer = []
    writer._flush_event = asyncio.Event()
    writer._ttl_set_keys = {}

    async def fake_serialize(data: Any) -> Any:
        return data

    redis_payloads: list[dict] = []

    async def fake_redis_write(stream_key: str, fields: dict) -> bool:
        redis_payloads.append(fields)
        return True

    monkeypatch.setattr(dual_writer_module, "_serialize_event_data_for_redis", fake_serialize)
    monkeypatch.setattr(writer, "_write_to_redis_direct", fake_redis_write)

    original = {"tool": "search", "result": {"structured": {"author.name": "x"}}}
    await writer.write_event(
        session_id="session-1",
        event_type="tool:result",
        data=original,
        trace_id="trace-1",
        run_id="run-1",
    )

    buffered = writer._mongo_buffer[0]
    assert buffered[2] == {"tool": "search", "result": {"structured": {"author_name": "x"}}}
    # 原始入参对象不被就地修改
    assert original["result"]["structured"] == {"author.name": "x"}


# ---------------------------------------------------------------------------
# Bounded retries for poisoned chunk groups
# ---------------------------------------------------------------------------


class _PoisonedTraceStorage:
    """Fake TraceStorage whose chunk append always fails like production."""

    def __init__(self) -> None:
        self.append_calls = 0

    async def acquire_session_trace_write(self, session_id: str) -> bool:
        return True

    async def release_session_trace_write(self, session_id: str) -> None:
        return None

    async def reserve_event_sequence_range(self, trace_id: str, count: int):
        return {"trace_id": trace_id, "event_count": count, "session_id": "session-1"}

    async def append_events_to_chunks(self, trace_doc, events, start_seq) -> bool:
        self.append_calls += 1
        raise RuntimeError("Invalid $set :: caused by :: FieldPath field names may not contain '.'")


@pytest.mark.asyncio
async def test_flush_drops_poisoned_group_after_attempt_cap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(dual_writer_module.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", True)
    monkeypatch.setattr(dual_writer_module.settings, "SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY", False)
    monkeypatch.setattr(dual_writer_module, "_CHUNK_WRITE_MAX_ATTEMPTS", 2)

    writer = object.__new__(DualEventWriter)
    writer._mongo_lock = asyncio.Lock()
    writer._flush_event = asyncio.Event()
    writer._mongo_buffer = []
    fake_trace = _PoisonedTraceStorage()
    monkeypatch.setattr(DualEventWriter, "trace", property(lambda self: fake_trace))

    batch = [
        ("trace-1", "tool:result", {"tool": "search"}, "session-1", "run-1", "t0"),
    ]

    # 第 1、2 次：重入缓冲区（带尝试计数）
    await writer._flush_mongo_batch(list(batch))
    first = writer._mongo_buffer
    assert len(first) == 1
    assert _buffer_item_attempts(first[0]) == 1

    writer._mongo_buffer = []
    await writer._flush_mongo_batch(list(first))
    second = writer._mongo_buffer
    assert len(second) == 1
    assert _buffer_item_attempts(second[0]) == 2

    # 第 3 次：达到上限，丢弃并打错误日志
    writer._mongo_buffer = []
    with caplog.at_level("ERROR", logger=dual_writer_module.logger.name):
        await writer._flush_mongo_batch(list(second))
    assert writer._mongo_buffer == []
    drop_logs = [r for r in caplog.records if "unwritable" in r.getMessage()]
    assert drop_logs, "expected a drop error log"
    assert fake_trace.append_calls == 3

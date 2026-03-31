import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ["DEBUG"] = "false"

from src.infra.session.trace_storage import TraceStorage
from src.infra.websocket import ConnectionManager


class DummyWebSocket:
    def __init__(self):
        self.messages: list[str] = []

    async def send_text(self, message: str) -> None:
        self.messages.append(message)


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._limit = None
        self._offset = 0

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length=None):
        effective = length
        if effective is None:
            effective = len(self._docs) - self._offset
        if self._limit is not None:
            effective = min(effective, self._limit)
        batch = self._docs[self._offset : self._offset + effective]
        self._offset += len(batch)
        return batch


@pytest.mark.asyncio
async def test_websocket_broadcast_ignores_same_instance_messages():
    manager = ConnectionManager()
    manager._instance_id = "instance-a"

    websocket = DummyWebSocket()
    await manager.connect(websocket, "user-1", accept=False)

    await manager._handle_broadcast_message(
        {
            "user_id": "user-1",
            "message": {"type": "task:complete", "data": {"run_id": "run-1"}},
            "source_instance_id": "instance-a",
        }
    )

    assert websocket.messages == []


@pytest.mark.asyncio
async def test_trace_storage_get_session_events_reads_beyond_500_traces():
    traces = [
        {
            "trace_id": f"trace-{i}",
            "run_id": f"run-{i}",
            "events": [
                {
                    "event_type": "message",
                    "data": {"index": i},
                    "timestamp": f"2026-03-26T00:00:{i % 60:02d}Z",
                }
            ],
        }
        for i in range(600)
    ]

    storage = TraceStorage()
    storage._collection = SimpleNamespace(find=lambda *_args, **_kwargs: FakeCursor(traces))
    storage.ensure_indexes_if_needed = AsyncMock()  # type: ignore[method-assign]

    events = await storage.get_session_events("session-1")

    assert len(events) == 600
    assert events[0]["trace_id"] == "trace-0"
    assert events[-1]["trace_id"] == "trace-599"

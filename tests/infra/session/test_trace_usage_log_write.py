import pytest

from src.infra.session import trace_storage as trace_storage_module


class _FakeTraceCollection:
    async def find_one(self, query, projection=None):
        assert query == {"trace_id": "trace-1"}
        assert projection == {"_id": 0, "events": 0}
        return {"trace_id": "trace-1", "session_id": "session-1"}


class _FakeDatabase(dict):
    def __getitem__(self, name):
        assert name == trace_storage_module.settings.MONGODB_TRACES_COLLECTION
        return _FakeTraceCollection()


class _FakeUsageCollection:
    database = _FakeDatabase()


class _FakeUsageStorage:
    def __init__(self):
        self.collection = _FakeUsageCollection()
        self.upsert_calls = []

    async def upsert_usage_log_from_trace_metadata(self, trace_doc, usage_data):
        self.upsert_calls.append((trace_doc, usage_data))
        return True


@pytest.mark.asyncio
async def test_write_usage_log_reads_trace_metadata_and_last_usage_event(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(
        "src.infra.usage.storage.get_usage_storage",
        lambda: storage,
    )
    usage_event_calls = []

    class _FakeTraceStorage:
        async def get_last_trace_event(self, trace_id, event_types):
            usage_event_calls.append((trace_id, event_types))
            return {
                "event_type": "token:usage",
                "data": {"input_tokens": 1, "output_tokens": 2},
            }

    monkeypatch.setattr(
        trace_storage_module,
        "get_trace_storage",
        lambda: _FakeTraceStorage(),
    )

    await trace_storage_module._write_usage_log("trace-1")

    assert usage_event_calls == [("trace-1", ["token:usage"])]
    assert storage.upsert_calls == [
        (
            {"trace_id": "trace-1", "session_id": "session-1"},
            {"input_tokens": 1, "output_tokens": 2},
        )
    ]

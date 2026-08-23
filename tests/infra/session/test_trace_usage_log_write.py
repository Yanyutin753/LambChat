import pytest

from src.infra.session import trace_storage as trace_storage_module


class _FakeTraceCollection:
    def __init__(self, doc=None):
        self.doc = doc or {"trace_id": "trace-1", "session_id": "session-1"}

    async def find_one(self, query, projection=None):
        assert query == {"trace_id": "trace-1"}
        assert projection == {"_id": 0, "events": 0}
        return self.doc


class _FakeDatabase(dict):
    def __init__(self, trace_doc=None):
        super().__init__()
        self.trace_doc = trace_doc

    def __getitem__(self, name):
        assert name == trace_storage_module.settings.MONGODB_TRACES_COLLECTION
        return _FakeTraceCollection(self.trace_doc)


class _FakeUsageCollection:
    def __init__(self, trace_doc=None):
        self.database = _FakeDatabase(trace_doc)


class _FakeUsageStorage:
    def __init__(self, trace_doc=None):
        self.collection = _FakeUsageCollection(trace_doc)
        self.upsert_calls = []

    async def upsert_usage_log_from_trace_metadata(self, trace_doc, usage_data, error_data=None):
        self.upsert_calls.append((trace_doc, usage_data, error_data))
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
            if event_types == ["token:usage"]:
                return {
                    "event_type": "token:usage",
                    "data": {"input_tokens": 1, "output_tokens": 2},
                }
            return None

    monkeypatch.setattr(
        trace_storage_module,
        "get_trace_storage",
        lambda: _FakeTraceStorage(),
    )

    await trace_storage_module._write_usage_log("trace-1")

    assert usage_event_calls == [
        ("trace-1", ["token:usage"]),
        ("trace-1", ["error"]),
    ]
    assert storage.upsert_calls == [
        (
            {"trace_id": "trace-1", "session_id": "session-1"},
            {"input_tokens": 1, "output_tokens": 2},
            {},
        )
    ]


@pytest.mark.asyncio
async def test_write_usage_log_passes_last_error_event_for_failed_trace(monkeypatch) -> None:
    trace_doc = {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "status": "error",
    }
    storage = _FakeUsageStorage(trace_doc)
    monkeypatch.setattr(
        "src.infra.usage.storage.get_usage_storage",
        lambda: storage,
    )
    event_calls = []

    class _FakeTraceStorage:
        async def get_last_trace_event(self, trace_id, event_types):
            event_calls.append(list(event_types))
            if event_types == ["token:usage"]:
                return {
                    "event_type": "token:usage",
                    "data": {"input_tokens": 0, "output_tokens": 0},
                }
            if event_types == ["error"]:
                return {
                    "event_type": "error",
                    "data": {
                        "error": "Error code: 429 - rate limit exceeded",
                        "type": "RateLimitError",
                        "run_id": "run-1",
                    },
                }
            return None

    monkeypatch.setattr(
        trace_storage_module,
        "get_trace_storage",
        lambda: _FakeTraceStorage(),
    )

    await trace_storage_module._write_usage_log("trace-1")

    assert ["token:usage"] in event_calls
    assert ["error"] in event_calls
    assert storage.upsert_calls[0][2] == {
        "error": "Error code: 429 - rate limit exceeded",
        "type": "RateLimitError",
        "run_id": "run-1",
    }

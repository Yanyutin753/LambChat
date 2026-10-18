from unittest.mock import AsyncMock

from src.infra.session.dual_writer import DualEventWriter


async def test_usage_is_durable_and_projected_before_write_returns(monkeypatch):
    writer = DualEventWriter()
    writer._flush_event.clear()
    monkeypatch.setattr(writer, "_write_to_redis_direct", AsyncMock(return_value=True))
    durable, projected = [], []

    async def flush(**kwargs):
        assert kwargs == {"require_trace_id": "trace"}
        durable.extend(writer._mongo_buffer)
        writer._mongo_buffer.clear()

    async def project(trace_id):
        assert trace_id == "trace"
        assert not writer._mongo_buffer
        projected.append(durable[-1][2]["input_tokens"])

    monkeypatch.setattr(writer, "flush_mongo_buffer", flush)
    monkeypatch.setattr("src.infra.session.trace_usage_log._write_usage_log", project)
    await writer.write_event("session", "token:usage", {"input_tokens": 10}, trace_id="trace")
    assert projected == [10]
    await writer.write_event("session", "token:usage", {"input_tokens": 20}, trace_id="trace")
    assert projected == [10, 20]

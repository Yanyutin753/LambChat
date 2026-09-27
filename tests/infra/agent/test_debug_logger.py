from __future__ import annotations

import pytest

from src.infra.agent.events import debug_logger


def test_sanitize_truncates_large_debug_event_values() -> None:
    payload = {
        "content": "x" * 5000,
        "items": [{"text": str(index)} for index in range(200)],
    }

    sanitized = debug_logger._sanitize(payload)

    assert sanitized["content"].endswith("[truncated from 5000 chars]")
    assert len(sanitized["items"]) == 101
    assert sanitized["items"][-1] == {"_truncated_items": 100}


@pytest.mark.asyncio
async def test_debug_log_event_offloads_serialization_and_file_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    def fail_sanitize(_event):
        raise AssertionError("debug_log_event should sanitize inside blocking executor")

    def fake_write_event_sync(event):
        assert event == {"event": "on_chain_stream"}

    monkeypatch.setattr(debug_logger, "_ENABLED", True)
    monkeypatch.setattr(debug_logger, "run_long_blocking_io", fake_run_long_blocking_io)
    monkeypatch.setattr(debug_logger, "_sanitize", fail_sanitize)
    monkeypatch.setattr(debug_logger, "_write_event_sync", fake_write_event_sync)

    await debug_logger.debug_log_event({"event": "on_chain_stream"})

    assert calls == ["fake_write_event_sync"]


@pytest.mark.asyncio
async def test_debug_log_event_includes_processing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append((func.__name__, args[1]))
        return None

    monkeypatch.setattr(debug_logger, "_ENABLED", True)
    monkeypatch.setattr(debug_logger, "run_long_blocking_io", fake_run_long_blocking_io)

    await debug_logger.debug_log_event(
        {"event": "on_chat_model_stream"},
        {"trace_id": "trace-1", "run_id": "run-1", "session_id": "session-1"},
    )

    assert calls == [
        (
            "_write_event_sync",
            {"trace_id": "trace-1", "run_id": "run-1", "session_id": "session-1"},
        )
    ]

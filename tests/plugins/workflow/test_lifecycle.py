from __future__ import annotations

import pytest

from src.plugins.workflow import lifecycle


@pytest.mark.asyncio
async def test_startup_reconciles_stale_durable_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    batch_counts = [2, 3, 0]

    class _FakeStorage:
        def __init__(self, **_kwargs) -> None:
            return None

        async def ensure_indexes(self) -> None:
            calls.append("ensure_indexes")

        async def fail_stale_running_runs(self) -> int:
            calls.append("fail_stale_running_runs")
            return batch_counts.pop(0)

        async def delete_terminal_run_logs_before(self, cutoff) -> int:
            calls.append("delete_terminal_run_logs_before")
            return 4

    warnings: list[tuple[str, tuple[object, ...]]] = []
    infos: list[tuple[str, tuple[object, ...]]] = []

    class _FakeLogger:
        def warning(self, message: str, *args: object) -> None:
            warnings.append((message, args))

        def info(self, message: str, *args: object) -> None:
            infos.append((message, args))

    monkeypatch.setattr(lifecycle, "WorkflowPluginStorage", _FakeStorage)
    monkeypatch.setattr(lifecycle, "logger", _FakeLogger())
    monkeypatch.setattr(lifecycle, "resolve_max_event_payload_bytes", lambda: _async_value(65536))
    monkeypatch.setattr(lifecycle, "resolve_run_log_retention_days", lambda: _async_value(30))

    await lifecycle.startup()

    assert calls == [
        "ensure_indexes",
        "fail_stale_running_runs",
        "fail_stale_running_runs",
        "fail_stale_running_runs",
        "delete_terminal_run_logs_before",
    ]
    assert warnings == [("Marked %s stale async/stream workflow runs as failed after startup", (5,))]
    assert infos == [("Deleted %s expired workflow run logs after startup", (4,))]


@pytest.mark.asyncio
async def test_startup_skips_warning_when_no_stale_durable_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        def __init__(self, **_kwargs) -> None:
            return None

        async def ensure_indexes(self) -> None:
            return None

        async def fail_stale_running_runs(self) -> int:
            return 0

        async def delete_terminal_run_logs_before(self, cutoff) -> int:
            return 0

    class _FakeLogger:
        def warning(self, *args: object) -> None:
            raise AssertionError(f"unexpected warning: {args}")

    monkeypatch.setattr(lifecycle, "WorkflowPluginStorage", _FakeStorage)
    monkeypatch.setattr(lifecycle, "logger", _FakeLogger())
    monkeypatch.setattr(lifecycle, "resolve_max_event_payload_bytes", lambda: _async_value(65536))
    monkeypatch.setattr(lifecycle, "resolve_run_log_retention_days", lambda: _async_value(30))

    await lifecycle.startup()


@pytest.mark.asyncio
async def test_startup_stops_before_recovery_when_index_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FakeStorage:
        def __init__(self, **_kwargs) -> None:
            return None

        async def ensure_indexes(self) -> None:
            calls.append("ensure_indexes")
            raise RuntimeError("index setup failed")

        async def fail_stale_running_runs(self) -> int:
            calls.append("fail_stale_running_runs")
            return 0

    monkeypatch.setattr(lifecycle, "WorkflowPluginStorage", _FakeStorage)
    monkeypatch.setattr(lifecycle, "resolve_max_event_payload_bytes", lambda: _async_value(65536))

    with pytest.raises(RuntimeError, match="index setup failed"):
        await lifecycle.startup()

    assert calls == ["ensure_indexes"]


@pytest.mark.asyncio
async def test_startup_skips_run_log_cleanup_when_retention_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FakeStorage:
        def __init__(self, **_kwargs) -> None:
            return None

        async def ensure_indexes(self) -> None:
            calls.append("ensure_indexes")

        async def fail_stale_running_runs(self) -> int:
            calls.append("fail_stale_running_runs")
            return 0

        async def delete_terminal_run_logs_before(self, cutoff) -> int:
            calls.append("delete_terminal_run_logs_before")
            return 0

    monkeypatch.setattr(lifecycle, "WorkflowPluginStorage", _FakeStorage)
    monkeypatch.setattr(lifecycle, "resolve_max_event_payload_bytes", lambda: _async_value(65536))
    monkeypatch.setattr(lifecycle, "resolve_run_log_retention_days", lambda: _async_value(0))

    await lifecycle.startup()

    assert calls == ["ensure_indexes", "fail_stale_running_runs"]


@pytest.mark.asyncio
async def test_create_workflow_storage_uses_resolved_event_payload_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[dict[str, int]] = []

    class _FakeStorage:
        def __init__(self, *, max_event_payload_bytes: int) -> None:
            constructed.append({"max_event_payload_bytes": max_event_payload_bytes})

    monkeypatch.setattr(lifecycle, "WorkflowPluginStorage", _FakeStorage)
    monkeypatch.setattr(lifecycle, "resolve_max_event_payload_bytes", lambda: _async_value(2048))

    storage = await lifecycle.create_workflow_storage()

    assert isinstance(storage, _FakeStorage)
    assert constructed == [{"max_event_payload_bytes": 2048}]


@pytest.mark.asyncio
async def test_resolve_max_event_payload_bytes_reads_plugin_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def __init__(self, **_kwargs) -> None:
            return None

        async def get_int(self, key: str, default: int) -> int:
            assert key == "MAX_EVENT_PAYLOAD_BYTES"
            assert default == lifecycle.DEFAULT_MAX_EVENT_PAYLOAD_BYTES
            return 32768

    monkeypatch.setattr(
        "src.infra.extensions.plugin_settings.PluginSettingsResolver",
        _FakeResolver,
    )

    assert await lifecycle.resolve_max_event_payload_bytes() == 32768


@pytest.mark.asyncio
async def test_resolve_max_event_payload_bytes_falls_back_when_setting_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingResolver:
        def __init__(self, **_kwargs) -> None:
            raise RuntimeError("settings unavailable")

    monkeypatch.setattr(
        "src.infra.extensions.plugin_settings.PluginSettingsResolver",
        _FailingResolver,
    )

    assert await lifecycle.resolve_max_event_payload_bytes() == lifecycle.DEFAULT_MAX_EVENT_PAYLOAD_BYTES


async def _async_value(value):
    return value

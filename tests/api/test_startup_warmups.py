from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from src.api import main as api_main


@pytest.mark.asyncio
async def test_schedule_models_cache_warmup_does_not_wait_for_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def _slow_warm_models_cache() -> None:
        calls.append("started")
        started.set()
        await release.wait()
        calls.append("finished")

    monkeypatch.setattr(api_main, "_warm_models_cache", _slow_warm_models_cache)
    app = SimpleNamespace(state=SimpleNamespace())

    task = api_main._schedule_models_cache_warmup(app)

    await asyncio.wait_for(started.wait(), timeout=1)
    assert task is app.state.models_preload_task
    assert calls == ["started"]
    assert task.done() is False

    release.set()
    await task
    assert calls == ["started", "finished"]


@pytest.mark.asyncio
async def test_warm_models_cache_logs_traceback_on_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_from_refresh_models() -> list[dict[str, object]]:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "src.infra.llm.models_service.refresh_models",
        _raise_from_refresh_models,
    )

    with caplog.at_level(logging.WARNING, logger="src.api.main"):
        await api_main._warm_models_cache()

    record = next(
        record
        for record in caplog.records
        if record.message.startswith("Model cache warm-up failed:")
    )
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_initialize_startup_indexes_runs_independent_groups_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()
    started: list[str] = []
    finished: list[str] = []

    async def _slow_initialize(name: str) -> None:
        started.append(name)
        await release.wait()
        finished.append(name)

    monkeypatch.setattr(
        api_main,
        "_startup_index_initializers",
        lambda: [
            ("agent_config", lambda: _slow_initialize("agent_config")),
            ("model_storage", lambda: _slow_initialize("model_storage")),
            ("channel_storage", lambda: _slow_initialize("channel_storage")),
        ],
    )

    task = asyncio.create_task(api_main._initialize_startup_indexes())

    for _ in range(10):
        if len(started) == 3:
            break
        await asyncio.sleep(0)

    assert started == ["agent_config", "model_storage", "channel_storage"]
    assert finished == []

    release.set()
    await task

    assert finished == ["agent_config", "model_storage", "channel_storage"]


@pytest.mark.asyncio
async def test_startup_index_initializers_include_user_storage_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FakeUserStorage:
        async def ensure_indexes_if_needed(self) -> None:
            calls.append("user_storage")

    monkeypatch.setattr("src.infra.user.storage.UserStorage", _FakeUserStorage)

    initializers = dict(api_main._startup_index_initializers())

    assert "user_storage" in initializers
    await initializers["user_storage"]()
    assert calls == ["user_storage"]


@pytest.mark.asyncio
async def test_run_startup_indexes_waits_for_index_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def _slow_initialize_startup_indexes() -> None:
        calls.append("started")
        started.set()
        await release.wait()
        calls.append("finished")

    monkeypatch.setattr(
        api_main,
        "_initialize_startup_indexes",
        _slow_initialize_startup_indexes,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    task = asyncio.create_task(api_main._run_startup_indexes(app))

    await asyncio.wait_for(started.wait(), timeout=1)
    assert app.state.startup_indexes_task is not None
    assert calls == ["started"]
    assert task.done() is False

    release.set()
    await task
    assert calls == ["started", "finished"]
    assert app.state.startup_indexes_task.done() is True


@pytest.mark.asyncio
async def test_schedule_stale_task_cleanup_does_not_wait_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def _slow_cleanup_stale_tasks() -> None:
        calls.append("started")
        started.set()
        await release.wait()
        calls.append("finished")

    monkeypatch.setattr(api_main, "_cleanup_stale_tasks", _slow_cleanup_stale_tasks)
    app = SimpleNamespace(state=SimpleNamespace())

    task = api_main._schedule_stale_task_cleanup(app)

    await asyncio.wait_for(started.wait(), timeout=1)
    assert task is app.state.stale_task_cleanup_task
    assert calls == ["started"]
    assert task.done() is False

    release.set()
    await task
    assert calls == ["started", "finished"]
    app.state.stale_task_cleanup_recheck_task.cancel()
    await asyncio.gather(app.state.stale_task_cleanup_recheck_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_schedule_stale_task_cleanup_rechecks_after_heartbeat_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sleep_calls: list[float] = []

    async def _cleanup_stale_tasks() -> None:
        calls.append("cleanup")

    async def _sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(api_main, "_cleanup_stale_tasks", _cleanup_stale_tasks)
    monkeypatch.setattr(api_main, "_STALE_TASK_CLEANUP_RECHECK_DELAY_SECONDS", 0.5)
    monkeypatch.setattr(api_main.asyncio, "sleep", _sleep)
    app = SimpleNamespace(state=SimpleNamespace())

    task = api_main._schedule_stale_task_cleanup(app)
    await task
    await app.state.stale_task_cleanup_recheck_task

    assert task is app.state.stale_task_cleanup_task
    assert calls == ["cleanup", "cleanup"]
    assert sleep_calls == [0.5]


@pytest.mark.asyncio
async def test_cancel_background_tasks_awaits_task_cleanup() -> None:
    cleanup_finished = False
    started = asyncio.Event()

    async def _long_running_task() -> None:
        nonlocal cleanup_finished
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_finished = True

    task = asyncio.create_task(_long_running_task())
    await asyncio.wait_for(started.wait(), timeout=1)

    app = SimpleNamespace(state=SimpleNamespace(cleanup_task=task))

    await api_main._cancel_background_tasks(app, "cleanup_task")

    assert task.cancelled() is True
    assert cleanup_finished is True
    assert app.state.cleanup_task is None


@pytest.mark.asyncio
async def test_stop_feishu_channels_for_shutdown_cancels_startup_task_before_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel import feishu as feishu_package

    calls: list[str] = []
    started = asyncio.Event()

    async def _starting_feishu() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            calls.append("startup_cancelled")

    async def _stop_feishu_channels() -> None:
        calls.append("stop")

    monkeypatch.setattr(feishu_package, "stop_feishu_channels", _stop_feishu_channels)

    task = asyncio.create_task(_starting_feishu())
    await asyncio.wait_for(started.wait(), timeout=1)
    app = SimpleNamespace(state=SimpleNamespace(feishu_task=task))

    await api_main._stop_feishu_channels_for_shutdown(app)

    assert task.cancelled() is True
    assert calls == ["startup_cancelled", "stop"]


@pytest.mark.asyncio
async def test_close_route_dependency_singletons_closes_cached_route_managers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _close_notification_manager() -> None:
        calls.append("notification")

    async def _close_revealed_file_storage() -> None:
        calls.append("revealed_file")

    async def _close_upload_route_dependencies() -> None:
        calls.append("upload")

    async def _close_persona_preset_manager() -> None:
        calls.append("persona_preset")

    monkeypatch.setattr(
        api_main.notification,
        "close_notification_manager",
        _close_notification_manager,
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.close_revealed_file_storage",
        _close_revealed_file_storage,
        raising=False,
    )
    monkeypatch.setattr(
        api_main.upload,
        "close_upload_route_dependencies",
        _close_upload_route_dependencies,
        raising=False,
    )
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.close_persona_preset_manager",
        _close_persona_preset_manager,
        raising=False,
    )

    await api_main._close_route_dependency_singletons()

    assert calls == ["notification", "revealed_file", "upload", "persona_preset"]


def test_feedback_shutdown_is_owned_by_plugin_lifecycle() -> None:
    from src.kernel.extensions import FEEDBACK_PLUGIN_ID, build_feedback_plugin_manifest

    source_names = api_main._close_route_dependency_singletons.__code__.co_names
    manifest = build_feedback_plugin_manifest()

    assert "close_feedback_manager" not in source_names
    assert manifest.id == FEEDBACK_PLUGIN_ID
    assert manifest.lifespan_hooks[0].module == (
        "src.plugins.feedback.lifecycle:close_feedback_manager"
    )


@pytest.mark.asyncio
async def test_close_session_sandbox_manager_for_shutdown_delegates_to_close_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _close_session_sandbox_manager() -> None:
        calls.append("sandbox_manager")

    monkeypatch.setattr(
        "src.infra.sandbox.session_manager.close_session_sandbox_manager",
        _close_session_sandbox_manager,
        raising=False,
    )

    await api_main._close_session_sandbox_manager_for_shutdown()

    assert calls == ["sandbox_manager"]


@pytest.mark.asyncio
async def test_cancel_lifespan_background_tasks_for_shutdown_cancels_registered_tasks() -> None:
    cleanup_calls: list[str] = []
    started_events = {
        task_name: asyncio.Event() for task_name in api_main._LIFESPAN_BACKGROUND_TASK_NAMES
    }

    async def _long_running_task(task_name: str) -> None:
        started_events[task_name].set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_calls.append(task_name)

    state = SimpleNamespace()
    tasks: list[asyncio.Task[None]] = []
    for task_name in api_main._LIFESPAN_BACKGROUND_TASK_NAMES:
        task = asyncio.create_task(_long_running_task(task_name))
        setattr(state, task_name, task)
        tasks.append(task)

    for event in started_events.values():
        await asyncio.wait_for(event.wait(), timeout=1)

    app = SimpleNamespace(state=state)

    await api_main._cancel_lifespan_background_tasks_for_shutdown(app)

    assert all(task.cancelled() for task in tasks)
    assert set(cleanup_calls) == set(api_main._LIFESPAN_BACKGROUND_TASK_NAMES)
    assert all(
        getattr(state, task_name) is None for task_name in api_main._LIFESPAN_BACKGROUND_TASK_NAMES
    )


@pytest.mark.asyncio
async def test_shutdown_background_task_list_includes_feishu_task() -> None:
    assert "feishu_task" in api_main._LIFESPAN_BACKGROUND_TASK_NAMES

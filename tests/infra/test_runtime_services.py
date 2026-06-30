from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra import runtime_services


class _FakeAsyncService:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start_listener(self) -> None:
        self.start_calls += 1

    async def stop_listener(self) -> None:
        self.stop_calls += 1


class _FakeTaskManager(_FakeAsyncService):
    async def start_pubsub_listener(self) -> None:
        self.start_calls += 1

    async def stop_pubsub_listener(self) -> None:
        self.stop_calls += 1


class _FakeWebSocketManager(_FakeAsyncService):
    async def start_pubsub_listener(self) -> None:
        self.start_calls += 1

    async def stop_pubsub_listener(self) -> None:
        self.stop_calls += 1


class _FakeScheduledTaskStorage:
    def __init__(self) -> None:
        self.ensure_indexes_calls = 0

    async def ensure_indexes(self) -> None:
        self.ensure_indexes_calls += 1


class _FakeScheduledTaskService:
    def __init__(self) -> None:
        self.load_calls = 0

    async def load_persisted_tasks(self) -> int:
        self.load_calls += 1
        return 0


class _FakeRuntimeScheduler:
    def __init__(self) -> None:
        self.start_calls = 0
        self.registered_job_ids: list[str] = []

    def register_job(self, job) -> None:
        self.registered_job_ids.append(job.id)

    def has_job(self, job_id: str) -> bool:
        return job_id in self.registered_job_ids

    def start(self) -> None:
        self.start_calls += 1


def _patch_runtime_service_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enable_memory: bool,
    enable_scheduled_task: bool,
    task_manager: _FakeTaskManager,
    settings_pubsub: _FakeAsyncService,
    model_config_pubsub: _FakeAsyncService,
    memory_pubsub: _FakeAsyncService,
    websocket_manager: _FakeWebSocketManager,
    channel_pubsub: _FakeAsyncService,
    tool_cache_pubsub: _FakeAsyncService,
    mcp_cache_pubsub: _FakeAsyncService,
    scheduler: _FakeRuntimeScheduler,
    scheduled_task_storage: _FakeScheduledTaskStorage,
    scheduled_task_service: _FakeScheduledTaskService,
    memory_compaction: SimpleNamespace | None = None,
) -> None:
    async def _noop() -> None:
        return None

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(
            ENABLE_MEMORY=enable_memory,
            ENABLE_SCHEDULED_TASK=enable_scheduled_task,
        ),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "start_arq_runtime", _noop)
    monkeypatch.setattr(runtime_services, "start_event_loop_lag_monitor", _noop)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: channel_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: tool_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: mcp_cache_pubsub, raising=False
    )
    if memory_compaction is not None:
        monkeypatch.setattr(
            runtime_services,
            "start_memory_compaction_agent",
            lambda: setattr(memory_compaction, "start_calls", memory_compaction.start_calls + 1),
            raising=False,
        )
    else:
        monkeypatch.setattr(
            runtime_services,
            "start_memory_compaction_agent",
            lambda: None,
            raising=False,
        )
    monkeypatch.setattr(runtime_services, "get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        runtime_services,
        "get_scheduled_task_storage",
        lambda: scheduled_task_storage,
    )
    monkeypatch.setattr(runtime_services, "ScheduledTaskService", lambda: scheduled_task_service)


@pytest.mark.asyncio
async def test_start_runtime_services_starts_all_distributed_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    memory_compaction = SimpleNamespace(start_calls=0)
    scheduler = _FakeRuntimeScheduler()
    arq_runtime = SimpleNamespace(start_calls=0)
    lag_monitor = SimpleNamespace(start_calls=0)
    scheduled_task_storage = _FakeScheduledTaskStorage()
    scheduled_task_service = _FakeScheduledTaskService()

    async def _start_arq_runtime() -> None:
        arq_runtime.start_calls += 1

    async def _start_event_loop_lag_monitor() -> None:
        lag_monitor.start_calls += 1

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=True, ENABLE_SCHEDULED_TASK=True),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "start_arq_runtime", _start_arq_runtime)
    monkeypatch.setattr(
        runtime_services, "start_event_loop_lag_monitor", _start_event_loop_lag_monitor
    )
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: channel_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: tool_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: mcp_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services,
        "start_memory_compaction_agent",
        lambda: setattr(memory_compaction, "start_calls", memory_compaction.start_calls + 1),
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "get_runtime_scheduler",
        lambda: scheduler,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "get_scheduled_task_storage",
        lambda: scheduled_task_storage,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "ScheduledTaskService",
        lambda: scheduled_task_service,
        raising=False,
    )

    await runtime_services.start_runtime_services()

    assert task_manager.start_calls == 1
    assert lag_monitor.start_calls == 1
    assert arq_runtime.start_calls == 1
    assert settings_pubsub.start_calls == 1
    assert model_config_pubsub.start_calls == 1
    assert memory_pubsub.start_calls == 1
    assert websocket_manager.start_calls == 1
    assert channel_pubsub.start_calls == 1
    assert tool_cache_pubsub.start_calls == 1
    assert mcp_cache_pubsub.start_calls == 1
    assert memory_compaction.start_calls == 1
    assert scheduled_task_storage.ensure_indexes_calls == 1
    assert scheduled_task_service.load_calls == 1
    assert scheduler.start_calls == 1


@pytest.mark.asyncio
async def test_start_runtime_services_forwards_plugin_runtime_to_arq_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    scheduler = _FakeRuntimeScheduler()
    scheduled_task_storage = _FakeScheduledTaskStorage()
    scheduled_task_service = _FakeScheduledTaskService()
    plugin_runtime = object()
    plugin_runtime_state_storage = object()
    arq_context = SimpleNamespace(plugin_runtime=None, plugin_runtime_state_storage=None)

    async def _start_arq_runtime(
        *,
        plugin_runtime=None,
        plugin_runtime_state_storage=None,
    ) -> None:
        arq_context.plugin_runtime = plugin_runtime
        arq_context.plugin_runtime_state_storage = plugin_runtime_state_storage

    _patch_runtime_service_dependencies(
        monkeypatch,
        enable_memory=False,
        enable_scheduled_task=False,
        task_manager=task_manager,
        settings_pubsub=settings_pubsub,
        model_config_pubsub=model_config_pubsub,
        memory_pubsub=memory_pubsub,
        websocket_manager=websocket_manager,
        channel_pubsub=channel_pubsub,
        tool_cache_pubsub=tool_cache_pubsub,
        mcp_cache_pubsub=mcp_cache_pubsub,
        scheduler=scheduler,
        scheduled_task_storage=scheduled_task_storage,
        scheduled_task_service=scheduled_task_service,
    )
    monkeypatch.setattr(runtime_services, "start_arq_runtime", _start_arq_runtime)

    await runtime_services.start_runtime_services(
        plugin_runtime=plugin_runtime,
        plugin_runtime_state_storage=plugin_runtime_state_storage,
    )

    assert arq_context.plugin_runtime is plugin_runtime
    assert arq_context.plugin_runtime_state_storage is plugin_runtime_state_storage
    assert task_manager.start_calls == 1


@pytest.mark.asyncio
async def test_start_runtime_services_registers_scheduled_task_reconcile_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = [_FakeAsyncService() for _ in range(6)]
    task_manager = _FakeTaskManager()
    websocket_manager = _FakeWebSocketManager()
    scheduler = _FakeRuntimeScheduler()
    scheduled_task_storage = _FakeScheduledTaskStorage()
    scheduled_task_service = _FakeScheduledTaskService()

    async def _noop() -> None:
        return None

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=False, ENABLE_SCHEDULED_TASK=True),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "start_arq_runtime", _noop)
    monkeypatch.setattr(runtime_services, "start_event_loop_lag_monitor", _noop)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: services[0])
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: services[1])
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: services[2], raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: services[3], raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: services[4], raising=False
    )
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(runtime_services, "get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        runtime_services, "get_scheduled_task_storage", lambda: scheduled_task_storage
    )
    monkeypatch.setattr(runtime_services, "ScheduledTaskService", lambda: scheduled_task_service)

    await runtime_services.start_runtime_services()

    assert "scheduled_tasks.reconcile" in scheduler.registered_job_ids
    assert scheduler.start_calls == 1


@pytest.mark.asyncio
async def test_start_runtime_services_skips_scheduled_task_runtime_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    scheduler = _FakeRuntimeScheduler()
    scheduled_task_storage = _FakeScheduledTaskStorage()
    scheduled_task_service = _FakeScheduledTaskService()

    _patch_runtime_service_dependencies(
        monkeypatch,
        enable_memory=False,
        enable_scheduled_task=False,
        task_manager=task_manager,
        settings_pubsub=settings_pubsub,
        model_config_pubsub=model_config_pubsub,
        memory_pubsub=memory_pubsub,
        websocket_manager=websocket_manager,
        channel_pubsub=channel_pubsub,
        tool_cache_pubsub=tool_cache_pubsub,
        mcp_cache_pubsub=mcp_cache_pubsub,
        scheduler=scheduler,
        scheduled_task_storage=scheduled_task_storage,
        scheduled_task_service=scheduled_task_service,
    )

    await runtime_services.start_runtime_services()

    assert scheduled_task_storage.ensure_indexes_calls == 0
    assert scheduled_task_service.load_calls == 0
    assert scheduler.registered_job_ids == []
    assert scheduler.start_calls == 0


@pytest.mark.asyncio
async def test_start_runtime_services_skips_memory_pubsub_when_memory_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    scheduled_task_storage = _FakeScheduledTaskStorage()
    scheduled_task_service = _FakeScheduledTaskService()

    async def _noop() -> None:
        return None

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=False, ENABLE_SCHEDULED_TASK=True),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "start_arq_runtime", _noop)
    monkeypatch.setattr(runtime_services, "start_event_loop_lag_monitor", _noop)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: channel_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: tool_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: mcp_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services,
        "start_memory_compaction_agent",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "get_runtime_scheduler",
        lambda: _FakeRuntimeScheduler(),
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "get_scheduled_task_storage",
        lambda: scheduled_task_storage,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "ScheduledTaskService",
        lambda: scheduled_task_service,
        raising=False,
    )

    await runtime_services.start_runtime_services()

    assert settings_pubsub.start_calls == 1
    assert model_config_pubsub.start_calls == 1
    assert memory_pubsub.start_calls == 0
    assert websocket_manager.start_calls == 1
    assert scheduled_task_storage.ensure_indexes_calls == 1
    assert scheduled_task_service.load_calls == 1


@pytest.mark.asyncio
async def test_stop_runtime_services_skips_memory_services_when_memory_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    memory_shutdown = SimpleNamespace(calls=0)
    scheduler = SimpleNamespace(stop_calls=0)

    async def _noop() -> None:
        return None

    async def _memory_shutdown() -> None:
        memory_shutdown.calls += 1

    async def _close_runtime_scheduler() -> None:
        scheduler.stop_calls += 1

    async def _close_tool_cache_pubsub() -> None:
        await tool_cache_pubsub.stop_listener()

    async def _close_mcp_cache_pubsub() -> None:
        await mcp_cache_pubsub.stop_listener()

    async def _close_channel_config_pubsub() -> None:
        await channel_pubsub.stop_listener()

    async def _close_memory_pubsub() -> None:
        await memory_pubsub.stop_listener()

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=False),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "stop_arq_runtime", _noop)
    monkeypatch.setattr(runtime_services, "stop_event_loop_lag_monitor", _noop)
    monkeypatch.setattr(runtime_services, "shutdown_blocking_io_executor", lambda: None)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: channel_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: tool_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: mcp_cache_pubsub, raising=False
    )
    monkeypatch.setattr(runtime_services, "memory_shutdown", _memory_shutdown, raising=False)
    monkeypatch.setattr(runtime_services, "drain_mcp_cache_background_tasks", _noop, raising=False)
    monkeypatch.setattr(runtime_services, "drain_mcp_global_background_tasks", _noop, raising=False)
    monkeypatch.setattr(runtime_services, "close_tool_cache_pubsub", _close_tool_cache_pubsub)
    monkeypatch.setattr(runtime_services, "close_mcp_cache_pubsub", _close_mcp_cache_pubsub)
    monkeypatch.setattr(
        runtime_services, "close_channel_config_pubsub", _close_channel_config_pubsub
    )
    monkeypatch.setattr(runtime_services, "close_memory_pubsub", _close_memory_pubsub)
    monkeypatch.setattr(runtime_services, "close_mcp_pool_connections", _noop, raising=False)
    monkeypatch.setattr(runtime_services, "close_runtime_scheduler", _close_runtime_scheduler)

    await runtime_services.stop_runtime_services()

    assert memory_pubsub.stop_calls == 0
    assert memory_shutdown.calls == 0
    assert settings_pubsub.stop_calls == 1
    assert model_config_pubsub.stop_calls == 1
    assert scheduler.stop_calls == 1


@pytest.mark.asyncio
async def test_close_runtime_scheduler_releases_scheduler_service_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _close_runtime_scheduler() -> None:
        calls.append("runtime")

    def _clear_managed_task_signatures() -> None:
        calls.append("signatures")

    def _close_scheduled_task_storage() -> None:
        calls.append("storage")

    monkeypatch.setattr(
        "src.infra.scheduler.runtime.close_runtime_scheduler",
        _close_runtime_scheduler,
    )
    monkeypatch.setattr(
        "src.infra.scheduler.service.clear_managed_task_signatures",
        _clear_managed_task_signatures,
    )
    monkeypatch.setattr(
        "src.infra.scheduler.storage.close_scheduled_task_storage",
        _close_scheduled_task_storage,
        raising=False,
    )

    await runtime_services.close_runtime_scheduler()

    assert calls == ["runtime", "signatures", "storage"]


@pytest.mark.asyncio
async def test_drain_dual_writer_event_buffer_closes_existing_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _close_dual_writer() -> None:
        calls.append("close")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.close_dual_writer",
        _close_dual_writer,
        raising=False,
    )

    await runtime_services.drain_dual_writer_event_buffer()

    assert calls == ["close"]


@pytest.mark.asyncio
async def test_stop_runtime_services_stops_all_distributed_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    channel_pubsub = _FakeAsyncService()
    tool_cache_pubsub = _FakeAsyncService()
    mcp_cache_pubsub = _FakeAsyncService()
    memory_shutdown = SimpleNamespace(calls=0)
    scheduler = SimpleNamespace(stop_calls=0)
    arq_runtime = SimpleNamespace(stop_calls=0)
    lag_monitor = SimpleNamespace(stop_calls=0)
    shutdown_calls = SimpleNamespace(count=0)
    call_order: list[str] = []
    mcp_cache_drain = SimpleNamespace(calls=0)
    mcp_global_drain = SimpleNamespace(calls=0)
    mcp_global_close = SimpleNamespace(calls=0)
    mcp_pool_close = SimpleNamespace(calls=0)
    pubsub_hub_close = SimpleNamespace(calls=0)
    channel_manager_close = SimpleNamespace(calls=0)
    runtime_scheduler_close = SimpleNamespace(calls=0)
    dual_writer_drain = SimpleNamespace(calls=0)
    upload_delete_drain = SimpleNamespace(calls=0)
    user_cleanup_drain = SimpleNamespace(calls=0)
    project_cleanup_drain = SimpleNamespace(calls=0)
    llm_close_drain = SimpleNamespace(calls=0)
    role_cache_close = SimpleNamespace(calls=0)
    ws_rate_limiter_close = SimpleNamespace(calls=0)
    s3_storage_close = SimpleNamespace(calls=0)
    skills_storage_cleanup = SimpleNamespace(calls=0)
    settings_service_close = SimpleNamespace(calls=0)

    async def _memory_shutdown() -> None:
        memory_shutdown.calls += 1

    async def _stop_arq_runtime() -> None:
        arq_runtime.stop_calls += 1

    async def _stop_event_loop_lag_monitor() -> None:
        lag_monitor.stop_calls += 1

    def _shutdown_blocking_io_executor() -> None:
        call_order.append("shutdown_blocking_io")
        shutdown_calls.count += 1

    async def _drain_mcp_cache_background_tasks() -> None:
        mcp_cache_drain.calls += 1

    async def _drain_mcp_global_background_tasks() -> None:
        mcp_global_drain.calls += 1

    async def _close_global_mcp_cache() -> None:
        mcp_global_close.calls += 1

    async def _close_tool_cache_pubsub() -> None:
        await tool_cache_pubsub.stop_listener()

    async def _close_mcp_cache_pubsub() -> None:
        await mcp_cache_pubsub.stop_listener()

    async def _close_channel_config_pubsub() -> None:
        await channel_pubsub.stop_listener()

    async def _close_memory_pubsub() -> None:
        await memory_pubsub.stop_listener()

    async def _close_mcp_pool_connections() -> None:
        mcp_pool_close.calls += 1

    async def _close_pubsub_hub() -> None:
        call_order.append("close_pubsub_hub")
        pubsub_hub_close.calls += 1

    async def _close_channel_manager_instances() -> None:
        call_order.append("close_channel_managers")
        channel_manager_close.calls += 1

    async def _close_runtime_scheduler() -> None:
        call_order.append("close_runtime_scheduler")
        runtime_scheduler_close.calls += 1

    async def _drain_dual_writer_event_buffer() -> None:
        call_order.append("drain_dual_writer")
        dual_writer_drain.calls += 1

    async def _drain_upload_delete_tasks() -> None:
        call_order.append("drain_upload_delete")
        upload_delete_drain.calls += 1

    async def _drain_user_s3_cleanup_tasks() -> None:
        call_order.append("drain_user_cleanup")
        user_cleanup_drain.calls += 1

    async def _drain_project_cleanup_tasks() -> None:
        call_order.append("drain_project_cleanup")
        project_cleanup_drain.calls += 1

    async def _drain_llm_client_close_tasks() -> None:
        call_order.append("drain_llm_close")
        llm_close_drain.calls += 1

    async def _close_role_cache_redis() -> None:
        call_order.append("close_role_cache")
        role_cache_close.calls += 1

    async def _close_ws_rate_limiter() -> None:
        call_order.append("close_ws_rate_limiter")
        ws_rate_limiter_close.calls += 1

    async def _close_s3_storage() -> None:
        call_order.append("close_s3_storage")
        s3_storage_close.calls += 1

    async def _cleanup_skills_storage_cache() -> None:
        call_order.append("cleanup_skills_storage")
        skills_storage_cleanup.calls += 1

    async def _close_settings_service() -> None:
        call_order.append("close_settings_service")
        settings_service_close.calls += 1

    monkeypatch.setattr(
        runtime_services,
        "settings",
        SimpleNamespace(ENABLE_MEMORY=True),
        raising=False,
    )
    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "stop_arq_runtime", _stop_arq_runtime)
    monkeypatch.setattr(
        runtime_services, "stop_event_loop_lag_monitor", _stop_event_loop_lag_monitor
    )
    monkeypatch.setattr(
        runtime_services,
        "shutdown_blocking_io_executor",
        _shutdown_blocking_io_executor,
    )
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(
        runtime_services, "get_channel_config_pubsub", lambda: channel_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_tool_cache_pubsub", lambda: tool_cache_pubsub, raising=False
    )
    monkeypatch.setattr(
        runtime_services, "get_mcp_cache_pubsub", lambda: mcp_cache_pubsub, raising=False
    )
    monkeypatch.setattr(runtime_services, "memory_shutdown", _memory_shutdown)
    monkeypatch.setattr(
        runtime_services,
        "drain_mcp_cache_background_tasks",
        _drain_mcp_cache_background_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_mcp_global_background_tasks",
        _drain_mcp_global_background_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_global_mcp_cache",
        _close_global_mcp_cache,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_tool_cache_pubsub",
        _close_tool_cache_pubsub,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_mcp_cache_pubsub",
        _close_mcp_cache_pubsub,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_channel_config_pubsub",
        _close_channel_config_pubsub,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_memory_pubsub",
        _close_memory_pubsub,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_mcp_pool_connections",
        _close_mcp_pool_connections,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_pubsub_hub",
        _close_pubsub_hub,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_channel_manager_instances",
        _close_channel_manager_instances,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_runtime_scheduler",
        _close_runtime_scheduler,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_dual_writer_event_buffer",
        _drain_dual_writer_event_buffer,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_upload_delete_tasks",
        _drain_upload_delete_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_user_s3_cleanup_tasks",
        _drain_user_s3_cleanup_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_project_cleanup_tasks",
        _drain_project_cleanup_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "drain_llm_client_close_tasks",
        _drain_llm_client_close_tasks,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_role_cache_redis",
        _close_role_cache_redis,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_ws_rate_limiter",
        _close_ws_rate_limiter,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_s3_storage",
        _close_s3_storage,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "cleanup_skills_storage_cache",
        _cleanup_skills_storage_cache,
        raising=False,
    )
    monkeypatch.setattr(
        runtime_services,
        "close_settings_service",
        _close_settings_service,
        raising=False,
    )
    await runtime_services.stop_runtime_services()

    assert task_manager.stop_calls == 1
    assert lag_monitor.stop_calls == 1
    assert arq_runtime.stop_calls == 1
    assert settings_pubsub.stop_calls == 1
    assert model_config_pubsub.stop_calls == 1
    assert memory_pubsub.stop_calls == 1
    assert websocket_manager.stop_calls == 1
    assert channel_pubsub.stop_calls == 1
    assert tool_cache_pubsub.stop_calls == 1
    assert mcp_cache_pubsub.stop_calls == 1
    assert mcp_cache_drain.calls == 1
    assert mcp_global_drain.calls == 1
    assert mcp_global_close.calls == 1
    assert mcp_pool_close.calls == 1
    assert pubsub_hub_close.calls == 1
    assert channel_manager_close.calls == 1
    assert runtime_scheduler_close.calls == 1
    assert dual_writer_drain.calls == 1
    assert upload_delete_drain.calls == 1
    assert user_cleanup_drain.calls == 1
    assert project_cleanup_drain.calls == 1
    assert llm_close_drain.calls == 1
    assert role_cache_close.calls == 1
    assert ws_rate_limiter_close.calls == 1
    assert s3_storage_close.calls == 1
    assert skills_storage_cleanup.calls == 1
    assert settings_service_close.calls == 1
    assert call_order == [
        "close_channel_managers",
        "close_runtime_scheduler",
        "close_pubsub_hub",
        "drain_upload_delete",
        "drain_user_cleanup",
        "drain_project_cleanup",
        "drain_llm_close",
        "close_role_cache",
        "close_ws_rate_limiter",
        "close_s3_storage",
        "cleanup_skills_storage",
        "close_settings_service",
        "drain_dual_writer",
        "shutdown_blocking_io",
    ]
    assert memory_shutdown.calls == 1
    assert shutdown_calls.count == 1


async def _increment_scheduler_stop(scheduler: SimpleNamespace) -> None:
    scheduler.stop_calls += 1

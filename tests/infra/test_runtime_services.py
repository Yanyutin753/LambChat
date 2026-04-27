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


@pytest.mark.asyncio
async def test_start_runtime_services_starts_all_distributed_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()

    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)

    await runtime_services.start_runtime_services()

    assert task_manager.start_calls == 1
    assert settings_pubsub.start_calls == 1
    assert model_config_pubsub.start_calls == 1
    assert memory_pubsub.start_calls == 1
    assert websocket_manager.start_calls == 1


@pytest.mark.asyncio
async def test_stop_runtime_services_stops_all_distributed_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = _FakeTaskManager()
    settings_pubsub = _FakeAsyncService()
    model_config_pubsub = _FakeAsyncService()
    memory_pubsub = _FakeAsyncService()
    websocket_manager = _FakeWebSocketManager()
    memory_shutdown = SimpleNamespace(calls=0)

    async def _memory_shutdown() -> None:
        memory_shutdown.calls += 1

    monkeypatch.setattr(runtime_services, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(runtime_services, "get_settings_pubsub", lambda: settings_pubsub)
    monkeypatch.setattr(runtime_services, "get_model_config_pubsub", lambda: model_config_pubsub)
    monkeypatch.setattr(runtime_services, "get_memory_pubsub", lambda: memory_pubsub)
    monkeypatch.setattr(runtime_services, "get_connection_manager", lambda: websocket_manager)
    monkeypatch.setattr(runtime_services, "memory_shutdown", _memory_shutdown)

    await runtime_services.stop_runtime_services()

    assert task_manager.stop_calls == 1
    assert settings_pubsub.stop_calls == 1
    assert model_config_pubsub.stop_calls == 1
    assert memory_pubsub.stop_calls == 1
    assert websocket_manager.stop_calls == 1
    assert memory_shutdown.calls == 1

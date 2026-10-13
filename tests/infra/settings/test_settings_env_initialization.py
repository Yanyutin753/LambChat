from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.settings import service as settings_service


async def test_initialization_does_not_query_settings_without_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = {f"FIXTURE_ABSENT_SETTING_{index}": {} for index in range(297)}
    for key in definitions:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(settings_service, "SETTING_DEFINITIONS", definitions)
    storage = SimpleNamespace(get=AsyncMock(return_value=None))
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock()

    assert await service.init_from_env() == 0

    storage.get.assert_not_awaited()
    service.set.assert_not_awaited()


async def test_initialization_preserves_existing_environment_setting_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "LLM_REQUEST_TIMEOUT"
    monkeypatch.setattr(
        settings_service,
        "SETTING_DEFINITIONS",
        {key: settings_service.SETTING_DEFINITIONS[key]},
    )
    monkeypatch.setenv(key, "45")
    storage = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(updated_at="2026-10-13T00:00:00Z"))
    )
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock()

    assert await service.init_from_env() == 0

    storage.get.assert_awaited_once_with(key)
    service.set.assert_not_awaited()


async def test_initialization_imports_missing_environment_setting_through_refresh_and_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "LLM_REQUEST_TIMEOUT"
    monkeypatch.setattr(
        settings_service,
        "SETTING_DEFINITIONS",
        {key: settings_service.SETTING_DEFINITIONS[key]},
    )
    monkeypatch.setenv(key, "45")
    stored = SimpleNamespace(value=45)
    storage = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(return_value=stored))
    service = settings_service.SettingsService()
    service._storage = storage
    refresh = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr("src.kernel.config.refresh_settings", refresh)
    monkeypatch.setattr(service, "_publish_change", publish)

    assert await service.init_from_env() == 1

    storage.get.assert_awaited_once_with(key)
    storage.set.assert_awaited_once_with(key, 45, "system:init")
    refresh.assert_awaited_once_with(key)
    publish.assert_awaited_once_with(key, 45)

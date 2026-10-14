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
    storage = SimpleNamespace(get=AsyncMock(return_value=None), get_many=AsyncMock(return_value={}))
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock()

    assert await service.init_from_env() == 0

    storage.get.assert_not_awaited()
    storage.get_many.assert_not_awaited()
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
        get=AsyncMock(return_value=SimpleNamespace(updated_at="2026-10-13T00:00:00Z")),
        get_many=AsyncMock(return_value={key: SimpleNamespace(updated_at="2026-10-13T00:00:00Z")}),
    )
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock()

    assert await service.init_from_env() == 0

    storage.get_many.assert_awaited_once_with([key])
    storage.get.assert_not_awaited()
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
    storage = SimpleNamespace(
        get=AsyncMock(return_value=None),
        get_many=AsyncMock(return_value={}),
        set=AsyncMock(return_value=stored),
    )
    service = settings_service.SettingsService()
    service._storage = storage
    refresh = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr("src.kernel.config.refresh_settings", refresh)
    monkeypatch.setattr(service, "_publish_change", publish)

    assert await service.init_from_env() == 1

    storage.get_many.assert_awaited_once_with([key])
    storage.get.assert_not_awaited()
    storage.set.assert_awaited_once_with(key, 45, "system:init")
    refresh.assert_awaited_once_with(key)
    publish.assert_awaited_once_with(key, 45)


@pytest.mark.parametrize("count", [1, 100])
async def test_initialization_reads_environment_settings_once_in_definition_order(
    monkeypatch, count
):
    keys = [f"FIXTURE_ENV_SETTING_{i}" for i in range(count)]
    definition = settings_service.SETTING_DEFINITIONS["LLM_REQUEST_TIMEOUT"]
    monkeypatch.setattr(settings_service, "SETTING_DEFINITIONS", dict.fromkeys(keys, definition))
    for i, key in enumerate(keys):
        monkeypatch.setenv(key, str(i))
    storage = SimpleNamespace(get_many=AsyncMock(return_value={}), get=AsyncMock(return_value=None))
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock(return_value=SimpleNamespace())

    assert await service.init_from_env() == count
    storage.get_many.assert_awaited_once_with(keys)
    storage.get.assert_not_awaited()
    assert [call.args for call in service.set.await_args_list] == [
        (key, i, "system:init") for i, key in enumerate(keys)
    ]


async def test_initialization_batch_read_failure_retains_partial_import_and_error_order(
    monkeypatch,
):
    keys = ["LLM_REQUEST_TIMEOUT", "LLM_FIRST_EVENT_TIMEOUT"]
    monkeypatch.setattr(
        settings_service,
        "SETTING_DEFINITIONS",
        {key: settings_service.SETTING_DEFINITIONS[key] for key in keys},
    )
    for key in keys:
        monkeypatch.setenv(key, "45")
    storage = SimpleNamespace(
        get_many=AsyncMock(side_effect=RuntimeError("batch unavailable")),
        get=AsyncMock(side_effect=[None, RuntimeError("second read failed")]),
    )
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock(return_value=SimpleNamespace())

    with pytest.raises(RuntimeError, match="second read failed"):
        await service.init_from_env()
    service.set.assert_awaited_once_with(keys[0], 45, "system:init")
    assert [call.args[0] for call in storage.get.await_args_list] == keys


async def test_initialization_set_failure_stops_before_later_settings(monkeypatch):
    keys = ["LLM_REQUEST_TIMEOUT", "LLM_FIRST_EVENT_TIMEOUT"]
    monkeypatch.setattr(
        settings_service,
        "SETTING_DEFINITIONS",
        {key: settings_service.SETTING_DEFINITIONS[key] for key in keys},
    )
    for key in keys:
        monkeypatch.setenv(key, "45")
    storage = SimpleNamespace(get_many=AsyncMock(return_value={}), get=AsyncMock(return_value=None))
    service = settings_service.SettingsService()
    service._storage = storage
    service.set = AsyncMock(side_effect=RuntimeError("first write failed"))

    with pytest.raises(RuntimeError, match="first write failed"):
        await service.init_from_env()
    service.set.assert_awaited_once_with(keys[0], 45, "system:init")

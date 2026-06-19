from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.settings import service as settings_service


class _EmptySettingsStorage:
    async def get(self, key: str):
        assert key == "WELCOME_SUGGESTIONS"
        return None


class _ClosableSettingsStorage:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _PluginOwnedLegacyStorage:
    async def get(self, _key: str):
        raise AssertionError("plugin-owned legacy keys must not use generic get")

    async def get_raw(self, _key: str):
        raise AssertionError("plugin-owned legacy keys must not use generic get_raw")

    async def get_plugin_owned_legacy_raw(self, key: str):
        class _Setting:
            value = "sk-legacy"

        assert key == "IMAGE_GENERATION_API_KEY"
        return _Setting()

    async def set(self, *_args, **_kwargs):
        raise AssertionError("plugin-owned legacy keys must not use generic set")

    async def reset(self, _key=None):
        raise AssertionError("plugin-owned legacy keys must not use generic reset")


@pytest.mark.asyncio
async def test_get_offloads_json_env_value_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    service = settings_service.SettingsService()
    service._storage = _EmptySettingsStorage()  # type: ignore[assignment]

    async def fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(getattr(func, "__name__", ""))
        return func(*args, **kwargs)

    monkeypatch.setenv("WELCOME_SUGGESTIONS", json.dumps({"en": [{"text": "hello"}]}))
    monkeypatch.setattr(settings_service, "run_blocking_io", fake_run_blocking_io)

    value = await service.get("WELCOME_SUGGESTIONS")

    assert calls == ["loads"]
    assert value == {"en": [{"text": "hello"}]}


@pytest.mark.asyncio
async def test_close_releases_settings_service_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _ClosableSettingsStorage()
    service = settings_service.SettingsService()
    service._storage = storage  # type: ignore[assignment]
    monkeypatch.setattr(settings_service.SettingsService, "_instance", service)

    await service.close()

    assert storage.closed is True
    assert settings_service.SettingsService._instance is None


@pytest.mark.asyncio
async def test_plugin_owned_legacy_keys_are_only_read_through_migration_api() -> None:
    service = settings_service.SettingsService()
    service._storage = _PluginOwnedLegacyStorage()  # type: ignore[assignment]

    assert await service.get("IMAGE_GENERATION_API_KEY") is None
    assert await service.get_raw("IMAGE_GENERATION_API_KEY") is None
    assert (
        await service.get_plugin_owned_legacy_raw("IMAGE_GENERATION_API_KEY")
        == "sk-legacy"
    )

    with pytest.raises(ValueError, match="owned by plugin image_generation"):
        await service.set("IMAGE_GENERATION_API_KEY", "sk-new", "admin")

    assert await service.reset("IMAGE_GENERATION_API_KEY") == 0

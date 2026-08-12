from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.infra.settings import service as settings_service
from src.kernel.schemas.setting import SettingCategory, SettingItem, SettingType


class _EmptySettingsStorage:
    async def get(self, key: str):
        assert key == "WELCOME_SUGGESTIONS"
        return None


class _ClosableSettingsStorage:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


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


def _setting(value: str) -> SettingItem:
    return SettingItem(
        key="TEST_SETTING",
        value=value,
        type=SettingType.STRING,
        category=SettingCategory.FRONTEND,
    )


@pytest.mark.asyncio
async def test_get_all_coalesces_inflight_reads_and_returns_independent_snapshots() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.calls = 0
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def get_all(self, **_kwargs):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return {"frontend": [_setting("original")]}

    storage = _Storage()
    service = settings_service.SettingsService()
    service._storage = storage  # type: ignore[assignment]

    first_task = asyncio.create_task(service.get_all(admin_mode=True))
    await storage.started.wait()
    second_task = asyncio.create_task(service.get_all(admin_mode=True))
    await asyncio.sleep(0)
    storage.release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert storage.calls == 1
    assert first == second
    assert first is not second
    first["frontend"][0].value = "mutated"
    third = await service.get_all(admin_mode=True)
    assert third["frontend"][0].value == "original"


@pytest.mark.asyncio
async def test_get_all_retries_after_failed_shared_load() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.calls = 0

        async def get_all(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return {"frontend": [_setting("recovered")]}

    storage = _Storage()
    service = settings_service.SettingsService()
    service._storage = storage  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="temporary failure"):
        await service.get_all()

    result = await service.get_all()
    assert result["frontend"][0].value == "recovered"
    assert storage.calls == 2


@pytest.mark.asyncio
async def test_set_and_reset_invalidate_get_all_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Storage:
        def __init__(self) -> None:
            self.value = "one"
            self.get_all_calls = 0

        async def get_all(self, **_kwargs):
            self.get_all_calls += 1
            return {"frontend": [_setting(self.value)]}

        async def set(self, _key, value, _user_id):
            self.value = value
            return _setting(value)

        async def reset(self, _key=None):
            self.value = "default"
            return 1

    storage = _Storage()
    service = settings_service.SettingsService()
    service._storage = storage  # type: ignore[assignment]
    monkeypatch.setattr("src.kernel.config.refresh_settings", AsyncMock())
    monkeypatch.setattr(service, "_publish_change", AsyncMock())

    assert (await service.get_all())["frontend"][0].value == "one"
    await service.set("TEST_SETTING", "two", "user-1")
    assert (await service.get_all())["frontend"][0].value == "two"
    await service.reset()
    assert (await service.get_all())["frontend"][0].value == "default"
    assert storage.get_all_calls == 3

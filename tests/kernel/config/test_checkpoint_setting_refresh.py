from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.kernel.config import service as config_service


class _FakeSettingsStorage:
    def __init__(self, value: object) -> None:
        self._value = value

    async def get_raw(self, key: str):
        return SimpleNamespace(key=key, value=self._value)


class _FakeSettingsService:
    def __init__(self, value: object) -> None:
        self._storage = _FakeSettingsStorage(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "current", "updated"),
    [
        ("CHECKPOINT_BACKEND", "mongodb", "postgres"),
        ("CHECKPOINT_PG_HOST", "localhost", "postgres.internal"),
        ("CHECKPOINT_PG_POOL_MAX_SIZE", 10, 20),
        ("CHECKPOINT_MONGO_POOL_MAX_SIZE", 10, 20),
    ],
)
async def test_refresh_restart_required_checkpoint_setting_keeps_runtime_state(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    current: object,
    updated: object,
) -> None:
    reset_calls: list[str] = []

    async def _fake_reset_runtime_state() -> None:
        reset_calls.append("reset")

    monkeypatch.setattr(config_service, "_settings_service", _FakeSettingsService(updated))
    monkeypatch.setattr(config_service.settings, key, current)
    monkeypatch.setattr(
        "src.infra.storage.checkpoint.reset_checkpointer_runtime_state",
        _fake_reset_runtime_state,
    )

    await config_service.refresh_settings(key)

    assert getattr(config_service.settings, key) == updated
    assert reset_calls == []


@pytest.mark.asyncio
async def test_refresh_mongo_pool_size_does_not_close_restart_only_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pool-size edits must not invalidate checkpointers cached by compiled agents."""
    reset_calls: list[str] = []

    async def _fake_reset_runtime_state() -> None:
        reset_calls.append("reset")

    monkeypatch.setattr(config_service, "_settings_service", _FakeSettingsService(7))
    monkeypatch.setattr(config_service.settings, "CHECKPOINT_MONGO_POOL_MAX_SIZE", 10)
    monkeypatch.setattr(
        "src.infra.storage.checkpoint.reset_checkpointer_runtime_state",
        _fake_reset_runtime_state,
    )

    await config_service.refresh_settings("CHECKPOINT_MONGO_POOL_MAX_SIZE")

    assert config_service.settings.CHECKPOINT_MONGO_POOL_MAX_SIZE == 7
    assert reset_calls == []


def test_checkpoint_settings_require_restart() -> None:
    from src.infra.settings.service import SettingsService

    checkpoint_settings = [
        "CHECKPOINT_BACKEND",
        "CHECKPOINT_PG_HOST",
        "CHECKPOINT_PG_PORT",
        "CHECKPOINT_PG_USER",
        "CHECKPOINT_PG_PASSWORD",
        "CHECKPOINT_PG_DB",
        "CHECKPOINT_PG_POOL_MIN_SIZE",
        "CHECKPOINT_PG_POOL_MAX_SIZE",
        # Mongo pool sizes mirror the PG pool config: change requests a restart.
        "CHECKPOINT_MONGO_POOL_MIN_SIZE",
        "CHECKPOINT_MONGO_POOL_MAX_SIZE",
    ]

    assert all(SettingsService.requires_restart(key) for key in checkpoint_settings)


def test_mongo_pool_size_definitions_exposed_in_ui() -> None:
    """Pool sizes must be visible in settings UI, grouped under Checkpoint."""
    from src.kernel.config.definitions import SETTING_DEFINITIONS
    from src.kernel.schemas.setting import SettingCategory

    for key in ("CHECKPOINT_MONGO_POOL_MIN_SIZE", "CHECKPOINT_MONGO_POOL_MAX_SIZE"):
        definition = SETTING_DEFINITIONS[key]
        assert definition["category"] is SettingCategory.CHECKPOINT
        assert definition["frontend_visible"] is True

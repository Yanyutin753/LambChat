"""启动加载时连接类配置不被数据库覆盖的策略测试（分布式 P2-1）。

克隆/多环境部署会把生产的 system_settings（含连接串）一并复制过来，
启动加载（initialize_settings）时 RESTART_REQUIRED_SETTINGS 名单内的
配置以 env 为唯一权威，不得被 DB 值覆盖，否则副本连错实例。
运行时面板主动修改（refresh_settings）保持既有覆盖语义。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.kernel.config import service as config_service
from src.kernel.schemas.setting import SettingItem


def _make_items(pairs: list[tuple[str, object]]) -> dict[str, list[SettingItem]]:
    return {
        "redis": [
            SettingItem(key=k, value=v, type="string", category="redis") for k, v in pairs
        ]
    }


class _FakeSettingsService:
    def __init__(self, all_settings: dict[str, list[SettingItem]]) -> None:
        self._all = all_settings
        self._storage = SimpleNamespace(get_raw=self._get_raw)

    async def _get_raw(self, key: str):
        for items in self._all.values():
            for item in items:
                if item.key == key:
                    return item
        return None

    @classmethod
    def get_instance(cls) -> "_FakeSettingsService":
        return cls(cls.pending)

    pending: dict[str, list[SettingItem]] = {}

    async def initialize(self) -> None:
        return None

    async def get_all(self, admin_mode: bool = False, mask_sensitive: bool = True):
        return self._all

    async def close(self) -> None:
        return None


@pytest.fixture()
def _isolated_config_globals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config_service, "_settings_service", None)
    monkeypatch.setattr(config_service, "_settings_cache", {})
    yield


async def _run_initialize(monkeypatch: pytest.MonkeyPatch, pairs: list[tuple[str, object]]):
    _FakeSettingsService.pending = _make_items(pairs)
    monkeypatch.setattr(
        "src.infra.settings.service.SettingsService", _FakeSettingsService
    )
    await config_service.initialize_settings()
    return config_service._settings_service


@pytest.mark.asyncio
async def test_initialize_skips_override_for_restart_required_keys(
    monkeypatch: pytest.MonkeyPatch, _isolated_config_globals
) -> None:
    monkeypatch.setattr(config_service.settings, "MONGODB_URL", "mongodb://env:27018")
    monkeypatch.setattr(config_service.settings, "POSTGRES_DB", "lamb-agent-test")
    monkeypatch.setattr(config_service.settings, "S3_ENABLED", False)
    monkeypatch.setattr(config_service.settings, "EVENT_MERGE_INTERVAL", 60)

    await _run_initialize(
        monkeypatch,
        [
            ("MONGODB_URL", "mongodb://from-db:27017"),
            ("POSTGRES_DB", "lamb-agent"),
            ("S3_ENABLED", True),
            ("EVENT_MERGE_INTERVAL", 90),
        ],
    )

    # 连接类配置保持 env 值（含扩展名单里的 POSTGRES_* / S3_*）
    assert config_service.settings.MONGODB_URL == "mongodb://env:27018"
    assert config_service.settings.POSTGRES_DB == "lamb-agent-test"
    assert config_service.settings.S3_ENABLED is False
    # 行为类配置照常从数据库加载
    assert config_service.settings.EVENT_MERGE_INTERVAL == 90


@pytest.mark.asyncio
async def test_refresh_keeps_panel_override_semantics(
    monkeypatch: pytest.MonkeyPatch, _isolated_config_globals
) -> None:
    """运行时面板主动修改（refresh）保持既有覆盖语义（不因启动策略收紧）。"""
    monkeypatch.setattr(config_service.settings, "REDIS_URL", "redis://env:6380/0")

    service = await _run_initialize(monkeypatch, [])
    service._all = _make_items([("REDIS_URL", "redis://panel-set:6379/5")])

    await config_service.refresh_settings("REDIS_URL")
    assert config_service.settings.REDIS_URL == "redis://panel-set:6379/5"

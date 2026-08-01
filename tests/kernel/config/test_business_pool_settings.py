"""Tests for the motor business connection-pool settings (P0-3).

Covers: default values/types, UI exposure (no depends_on, unlike checkpoint),
and restart-required registration. The motor client is an lru_cache singleton
shared across 30+ storages, so a pool change only takes effect on restart.
"""

from __future__ import annotations


def test_business_pool_defaults_and_types() -> None:
    from src.kernel.config import settings

    assert settings.MONGODB_POOL_MAX_SIZE == 20
    assert settings.MONGODB_POOL_MIN_SIZE == 2
    # Type must be int — motor rejects non-int pool sizes.
    assert type(settings.MONGODB_POOL_MAX_SIZE) is int
    assert type(settings.MONGODB_POOL_MIN_SIZE) is int


def test_mongodb_pool_size_definitions_exposed_in_ui() -> None:
    """Business pool sizes are visible in the UI under MongoDB, unconditionally."""
    from src.kernel.config.definitions import SETTING_DEFINITIONS
    from src.kernel.schemas.setting import SettingCategory, SettingType

    for key in ("MONGODB_POOL_MIN_SIZE", "MONGODB_POOL_MAX_SIZE"):
        definition = SETTING_DEFINITIONS[key]
        assert definition["category"] is SettingCategory.MONGODB
        assert definition["type"] is SettingType.NUMBER
        assert definition["frontend_visible"] is True
        # The business pool exists regardless of backend choice (unlike the
        # checkpoint pool, which depends on CHECKPOINT_BACKEND=mongodb).
        assert "depends_on" not in definition


def test_business_pool_settings_require_restart() -> None:
    from src.infra.settings.service import SettingsService

    assert SettingsService.requires_restart("MONGODB_POOL_MAX_SIZE")
    assert SettingsService.requires_restart("MONGODB_POOL_MIN_SIZE")

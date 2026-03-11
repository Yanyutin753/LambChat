"""Settings service integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from .base import settings

if TYPE_CHECKING:
    from src.infra.settings.service import SettingsService

logger = logging.getLogger(__name__)

# SettingsService integration
_settings_service: Optional["SettingsService"] = None

# Cache for all settings from database
_settings_cache: dict[str, Any] = {}


async def initialize_settings() -> None:
    """Initialize settings from database, importing from .env if needed.

    After calling this function, the global `settings` object will have its
    attributes overridden by values from the database (database > env > default).
    """
    global _settings_service, _settings_cache

    from src.infra.settings.service import SettingsService

    _settings_service = SettingsService.get_instance()
    await _settings_service.initialize()
    logger.info("[Settings] SettingsService initialized")

    # Load all settings from database and update the global settings object
    all_settings = await _settings_service.get_all(admin_mode=True, mask_sensitive=False)
    logger.info(f"[Settings] Loaded {len(all_settings)} categories from database")

    # Flatten the settings dict and cache them
    loaded_count = 0
    for category, items in all_settings.items():
        logger.debug(f"[Settings] Category {category}: {len(items)} items")
        for item in items:
            # Only update if value is not None AND not an empty string
            # This prevents empty DB values from overriding .env values
            if item and item.value is not None and item.value != "":
                _settings_cache[item.key] = item.value
                # Only update if the field exists in Settings class
                if hasattr(settings, item.key):
                    setattr(settings, item.key, item.value)
                    loaded_count += 1

    logger.info(f"[Settings] Loaded {loaded_count} settings into cache")
    logger.info(f"[Settings] REDIS_URL = {settings.REDIS_URL}")


async def refresh_settings(key: Optional[str] = None) -> None:
    """Refresh settings from database.

    Args:
        key: Specific key to refresh, or None for all settings.

    This should be called after database settings are updated.
    """
    global _settings_cache

    if _settings_service is None:
        return

    if key:
        # Refresh single setting
        setting = await _settings_service._storage.get_raw(key)
        # Only update if value is not None AND not an empty string
        if setting and setting.value is not None and setting.value != "":
            _settings_cache[key] = setting.value
            setattr(settings, key, setting.value)
    else:
        # Refresh all settings
        all_settings = await _settings_service.get_all(admin_mode=True, mask_sensitive=False)
        for items in all_settings.values():
            for item in items:
                # Only update if value is not None AND not an empty string
                if item and item.value is not None and item.value != "":
                    _settings_cache[item.key] = item.value
                    setattr(settings, item.key, item.value)

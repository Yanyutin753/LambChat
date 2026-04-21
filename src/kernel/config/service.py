"""Settings service integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from src.infra.logging import get_logger

from .base import settings

if TYPE_CHECKING:
    from src.infra.settings.service import SettingsService

logger = get_logger(__name__)

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

    # Settings that affect LLM model cache (used for title generation etc.)
    llm_affected_settings = {
        "SESSION_TITLE_MODEL",
        "SESSION_TITLE_API_BASE",
        "SESSION_TITLE_API_KEY",
        "LLM_MAX_RETRIES",
    }

    # Settings that require memory backend reinitialization
    memory_affected_settings = {
        "ENABLE_MEMORY",
        "NATIVE_MEMORY_EMBEDDING_API_BASE",
        "NATIVE_MEMORY_EMBEDDING_API_KEY",
    }

    if key:
        # Refresh single setting
        setting = await _settings_service._storage.get_raw(key)
        # Only update if value is not None AND not an empty string
        if setting and setting.value is not None and setting.value != "":
            _settings_cache[key] = setting.value
            setattr(settings, key, setting.value)
            # Clear LLM model cache if this setting affects it
            if key in llm_affected_settings:
                from src.infra.llm.client import LLMClient

                cleared = LLMClient.clear_cache_by_model()
                logger.info(
                    f"[Settings] Cleared {cleared} LLM model cache entries after setting '{key}' changed"
                )
            # Reset memory backend if this setting affects it
            if key in memory_affected_settings:
                from src.infra.memory.tools import schedule_backend_reset

                schedule_backend_reset()
                logger.info(f"[Settings] Memory backend reset after setting '{key}' changed")
    else:
        # Refresh all settings
        all_settings = await _settings_service.get_all(admin_mode=True, mask_sensitive=False)
        any_llm_setting_changed = False
        any_memory_setting_changed = False
        for items in all_settings.values():
            for item in items:
                # Only update if value is not None AND not an empty string
                if item and item.value is not None and item.value != "":
                    _settings_cache[item.key] = item.value
                    setattr(settings, item.key, item.value)
                    if item.key in llm_affected_settings:
                        any_llm_setting_changed = True
                    if item.key in memory_affected_settings:
                        any_memory_setting_changed = True

        # Clear LLM model cache if any affected setting changed
        if any_llm_setting_changed:
            from src.infra.llm.client import LLMClient

            cleared = LLMClient.clear_cache_by_model()
            logger.info(
                f"[Settings] Cleared {cleared} LLM model cache entries after settings refresh"
            )

        # Reset memory backend if any affected setting changed
        if any_memory_setting_changed:
            from src.infra.memory.tools import schedule_backend_reset

            schedule_backend_reset()
            logger.info("[Settings] Memory backend reset after settings refresh")

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

_ALLOW_EMPTY_STRING_SETTINGS = {
    "DEFAULT_MODEL_ID",
    "NATIVE_MEMORY_COMPACTION_MODEL_ID",
    "LLM_FALLBACK_MODEL",
    "LLM_REQUEST_HEADERS",
}


def _normalize_runtime_setting(key: str, value: Any) -> Any:
    """Coerce retired setting values before they reach the live runtime."""
    if key == "HITL_MODE":
        return "interrupt"
    return value


def _mark_runtime_secret_as_explicit(key: str) -> None:
    if key == "JWT_SECRET_KEY":
        settings._jwt_secret_key_generated = False
    elif key == "MCP_ENCRYPTION_SALT":
        settings._mcp_encryption_salt_generated = False
    elif key == "VAPID_PUBLIC_KEY":
        settings._vapid_keys_generated = False


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
            # Empty strings usually mean "keep env fallback", but selected model
            # settings use "" as an intentional "automatic/default" value.
            if (
                item
                and item.value is not None
                and (item.value != "" or item.key in _ALLOW_EMPTY_STRING_SETTINGS)
            ):
                normalized_value = _normalize_runtime_setting(item.key, item.value)
                _settings_cache[item.key] = normalized_value
                # Only update if the field exists in Settings class
                if hasattr(settings, item.key):
                    setattr(settings, item.key, normalized_value)
                    _mark_runtime_secret_as_explicit(item.key)
                    loaded_count += 1

    logger.info(f"[Settings] Loaded {loaded_count} settings into cache")

    # Migrate the retired blocking HITL value so the settings API and all
    # replicas converge on interrupt mode instead of merely coercing locally.
    if any(
        item.key == "HITL_MODE" and item.value != "interrupt"
        for items in all_settings.values()
        for item in items
        if item
    ):
        try:
            await _settings_service.set("HITL_MODE", "interrupt", "system:migration")
            logger.info("[Settings] Migrated HITL_MODE to interrupt")
        except Exception as exc:
            logger.warning("[Settings] Failed to persist HITL_MODE migration: %s", exc)

    # Persist auto-generated VAPID keys to database so they survive restarts
    if settings._vapid_keys_generated and _settings_service is not None:
        try:
            from datetime import datetime, timezone

            collection = _settings_service._storage._get_collection()
            now = datetime.now(timezone.utc).isoformat()
            for key in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
                value = getattr(settings, key, "")
                if value:
                    await collection.update_one(
                        {"_id": key},
                        {
                            "$set": {
                                "value": value,
                                "type": "string",
                                "category": "push",
                                "description": f"Auto-generated VAPID {key} for Web Push",
                                "default_value": "",
                                "updated_at": now,
                                "updated_by": "system",
                            }
                        },
                        upsert=True,
                    )
                    logger.info(f"[Settings] Persisted auto-generated {key} to database")
            _settings_cache["VAPID_PUBLIC_KEY"] = settings.VAPID_PUBLIC_KEY
            _settings_cache["VAPID_PRIVATE_KEY"] = settings.VAPID_PRIVATE_KEY
            settings._vapid_keys_generated = False
            logger.info("[Settings] VAPID keys persisted to database successfully")
        except Exception as exc:
            logger.warning("[Settings] Failed to persist auto-generated VAPID keys: %s", exc)


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
        "DEFAULT_MODEL_ID",
        "SESSION_TITLE_MODEL",
        "SESSION_TITLE_API_BASE",
        "SESSION_TITLE_API_KEY",
        "LLM_MAX_RETRIES",
        "LLM_RETRY_DELAY",
        "LLM_REQUEST_TIMEOUT",
        "LLM_FIRST_EVENT_TIMEOUT",
        "LLM_FALLBACK_MODEL",
        "LLM_OPENAI_API_FORMAT",
        "LLM_REQUEST_HEADERS",
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
        if (
            setting
            and setting.value is not None
            and (setting.value != "" or key in _ALLOW_EMPTY_STRING_SETTINGS)
        ):
            normalized_value = _normalize_runtime_setting(key, setting.value)
            _settings_cache[key] = normalized_value
            setattr(settings, key, normalized_value)
            _mark_runtime_secret_as_explicit(key)
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
                if (
                    item
                    and item.value is not None
                    and (item.value != "" or item.key in _ALLOW_EMPTY_STRING_SETTINGS)
                ):
                    normalized_value = _normalize_runtime_setting(item.key, item.value)
                    _settings_cache[item.key] = normalized_value
                    setattr(settings, item.key, normalized_value)
                    _mark_runtime_secret_as_explicit(item.key)
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

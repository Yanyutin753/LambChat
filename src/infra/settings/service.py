"""
Settings Service - Database-first settings with .env fallback
"""

import json
import os
from typing import Any, Optional

from src.infra.settings.storage import (
    RESTART_REQUIRED_SETTINGS,
    SETTING_DEFINITIONS,
    SettingsStorage,
)
from src.kernel.schemas.setting import SettingItem, SettingType


class SettingsService:
    """
    Database-first settings service.

    Reads settings from MongoDB, falls back to environment variables.
    Handles initialization from .env on first startup.
    """

    _instance: Optional["SettingsService"] = None

    def __init__(self):
        self._storage = SettingsStorage()
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "SettingsService":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        """Initialize service and import from .env if needed"""
        if self._initialized:
            return

        # Import any missing settings from environment
        await self.init_from_env()
        self._initialized = True

    async def get(self, key: str) -> Any:
        """
        Get setting value: DB -> .env fallback (with sensitive values masked)

        Args:
            key: Setting key name

        Returns:
            Setting value (sensitive values will be masked)
        """
        # Check if key is valid
        if key not in SETTING_DEFINITIONS:
            # Try environment variable directly
            return os.environ.get(key)

        # Try database first
        setting = await self._storage.get(key)
        if setting is not None:
            return setting.value

        # Fallback to environment variable
        env_value = os.environ.get(key)
        if env_value is not None:
            return self._parse_env_value(key, env_value)

        # Return default
        return SETTING_DEFINITIONS[key]["default"]

    async def get_raw(self, key: str) -> Any:
        """
        Get raw setting value (without masking) - for internal use only

        Args:
            key: Setting key name

        Returns:
            Raw setting value (sensitive values NOT masked)
        """
        # Check if key is valid
        if key not in SETTING_DEFINITIONS:
            # Try environment variable directly
            return os.environ.get(key)

        # Try database first (without masking)
        setting = await self._storage.get_raw(key)
        if setting is not None:
            return setting.value

        # Fallback to environment variable
        env_value = os.environ.get(key)
        if env_value is not None:
            return self._parse_env_value(key, env_value)

        # Return default
        return SETTING_DEFINITIONS[key]["default"]

    async def get_all(
        self, admin_mode: bool = False, mask_sensitive: bool = True
    ) -> dict[str, list[SettingItem]]:
        """Get all settings grouped by category

        Args:
            admin_mode: If True, return all settings.
                       If False, only return frontend_visible settings.
            mask_sensitive: If True, mask sensitive values with ********.
                           If False, return actual values (for internal use).
        """
        return await self._storage.get_all(admin_mode=admin_mode, mask_sensitive=mask_sensitive)

    async def set(self, key: str, value: Any, user_id: str) -> Optional[SettingItem]:
        """
        Set setting value in database.

        Args:
            key: Setting key name
            value: New value
            user_id: User making the change

        Returns:
            Updated setting item
        """
        result = await self._storage.set(key, value, user_id)

        # Refresh the global settings object to reflect the change
        from src.kernel.config import refresh_settings

        await refresh_settings(key)

        # Broadcast to other instances via Redis pub/sub
        await self._publish_change(key, value)

        return result

    async def init_from_env(self) -> int:
        """
        Import settings from .env to database if not already set.

        Only imports values that don't exist in database yet.
        Each imported setting is also refreshed locally and broadcast to other instances.

        Returns:
            Number of settings imported
        """
        imported = 0

        for key, definition in SETTING_DEFINITIONS.items():
            # Check if already in database
            existing = await self._storage.get(key)
            if existing is not None and existing.updated_at is not None:
                continue  # Already set, skip

            # Get value from environment
            env_value = os.environ.get(key)
            if env_value is None:
                continue  # No env value, skip

            # Parse and store via self.set() to trigger refresh + pub/sub broadcast
            parsed_value = self._parse_env_value(key, env_value)
            result = await self.set(key, parsed_value, "system:init")
            if result is not None:
                imported += 1

        return imported

    async def reset(self, key: Optional[str] = None) -> int:
        """
        Reset settings to default values.

        Args:
            key: Specific key to reset, or None for all

        Returns:
            Number of settings reset
        """
        count = await self._storage.reset(key)

        # Refresh the global settings object to reflect the change
        from src.kernel.config import refresh_settings

        await refresh_settings(key)

        # Broadcast reset to other instances
        await self._publish_change(key, None)

        return count

    def get_sync(self, key: str) -> Any:
        """
        Synchronous get for backward compatibility.

        Note: This only checks environment variables, not database.
        Use async get() for full database access.

        Args:
            key: Setting key name

        Returns:
            Setting value from environment or default
        """
        if key not in SETTING_DEFINITIONS:
            return os.environ.get(key)

        env_value = os.environ.get(key)
        if env_value is not None:
            return self._parse_env_value(key, env_value)

        return SETTING_DEFINITIONS[key]["default"]

    def _parse_env_value(self, key: str, value: str) -> Any:
        """Parse environment variable string to correct type"""
        if key not in SETTING_DEFINITIONS:
            return value

        setting_type = SETTING_DEFINITIONS[key]["type"]

        if setting_type == SettingType.BOOLEAN:
            return value.lower() in ("true", "1", "yes", "on")
        elif setting_type == SettingType.NUMBER:
            try:
                return int(value)
            except ValueError:
                return float(value)
        elif setting_type == SettingType.JSON:
            import json

            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        else:
            return value

    @staticmethod
    def requires_restart(key: str) -> bool:
        """Check if setting requires server restart"""
        return key in RESTART_REQUIRED_SETTINGS

    @staticmethod
    def is_sensitive(key: str) -> bool:
        """Check if setting is sensitive (should be hidden in API)"""
        definition = SETTING_DEFINITIONS.get(key)
        return definition.get("is_sensitive", False) if definition else False

    async def close(self) -> None:
        """Close connections"""
        await self._storage.close()

    @staticmethod
    async def _publish_change(key: Optional[str], value: Any) -> None:
        """Broadcast a settings change to other instances via Redis pub/sub."""
        try:
            from src.infra.settings.pubsub import get_settings_pubsub
            from src.infra.storage.redis import get_redis_client
            from src.infra.task.constants import SETTINGS_CHANNEL

            redis_client = get_redis_client()
            instance_id = get_settings_pubsub().instance_id
            await redis_client.publish(
                SETTINGS_CHANNEL,
                json.dumps({"key": key, "instance_id": instance_id}),
            )
        except Exception as e:
            # Pub/sub failure should not block the setting update
            import logging

            logging.getLogger(__name__).warning(f"Failed to publish setting change: {e}")


# Global instance getter
def get_settings_service() -> SettingsService:
    """Get the global SettingsService instance"""
    return SettingsService.get_instance()

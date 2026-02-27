"""
Settings storage using MongoDB
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.kernel.config import (
    RESTART_REQUIRED_SETTINGS,
    SENSITIVE_SETTINGS,
    SETTING_DEFINITIONS,
    _get_default_from_settings,
    settings,
)
from src.kernel.schemas.setting import SettingItem


class SettingsStorage:
    """Settings storage using MongoDB"""

    def __init__(self):
        self._client = None
        self._collection = None

    def _get_collection(self):
        """Get MongoDB collection lazily"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._collection = db["system_settings"]
        return self._collection

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
        collection = self._get_collection()
        cursor = collection.find({})
        db_settings = {doc["_id"]: doc for doc in await cursor.to_list(length=None)}

        result: dict[str, list[SettingItem]] = {}

        for key, definition in SETTING_DEFINITIONS.items():
            # Filter non-admin users
            if not admin_mode and not definition.get("frontend_visible", False):
                continue

            category = definition["category"].value
            if category not in result:
                result[category] = []

            # Get default from SETTING_DEFINITIONS (single source of truth)
            default_value = _get_default_from_settings(key)

            # Use DB value if exists, otherwise use default
            db_doc = db_settings.get(key)
            value = db_doc["value"] if db_doc else default_value

            # Mask sensitive settings in API responses
            if mask_sensitive and key in SENSITIVE_SETTINGS and value:
                value = "********"

            item = SettingItem(
                key=key,
                value=value,
                type=definition["type"],
                category=definition["category"],
                description=definition["description"],
                default_value=default_value,
                requires_restart=key in RESTART_REQUIRED_SETTINGS,
                is_sensitive=key in SENSITIVE_SETTINGS,
                frontend_visible=definition.get("frontend_visible", False),
                updated_at=db_doc.get("updated_at") if db_doc else None,
                updated_by=db_doc.get("updated_by") if db_doc else None,
            )
            result[category].append(item)

        return result

    async def get(self, key: str) -> Optional[SettingItem]:
        """Get single setting by key (with sensitive values masked)"""
        return await self._get_internal(key, mask_sensitive=True)

    async def get_raw(self, key: str) -> Optional[SettingItem]:
        """Get single setting by key (without masking - for internal use only)"""
        return await self._get_internal(key, mask_sensitive=False)

    async def _get_internal(self, key: str, mask_sensitive: bool = True) -> Optional[SettingItem]:
        """Internal method to get setting by key"""
        definition = SETTING_DEFINITIONS.get(key)
        if not definition:
            return None

        collection = self._get_collection()
        doc = await collection.find_one({"_id": key})

        # Get default from SETTING_DEFINITIONS (single source of truth)
        default_value = _get_default_from_settings(key)

        value = doc["value"] if doc else default_value

        # Mask sensitive settings in API responses (if requested)
        if mask_sensitive and key in SENSITIVE_SETTINGS and value:
            value = "********"

        return SettingItem(
            key=key,
            value=value,
            type=definition["type"],
            category=definition["category"],
            description=definition["description"],
            default_value=default_value,
            requires_restart=key in RESTART_REQUIRED_SETTINGS,
            is_sensitive=key in SENSITIVE_SETTINGS,
            frontend_visible=definition.get("frontend_visible", False),
            updated_at=doc.get("updated_at") if doc else None,
            updated_by=doc.get("updated_by") if doc else None,
        )

    async def set(self, key: str, value: Any, user_id: str) -> Optional[SettingItem]:
        """Set setting value"""
        definition = SETTING_DEFINITIONS.get(key)
        if not definition:
            return None

        # Don't allow setting masked values
        if value == "********":
            raise ValueError("Cannot set masked value")

        # Type validation
        expected_type = definition["type"]
        if expected_type.value == "number":
            if not isinstance(value, (int, float)):
                raise ValueError(f"Setting {key} expects a number")
        elif expected_type.value == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Setting {key} expects a boolean")
        elif expected_type.value == "string":
            value = str(value)
        elif expected_type.value == "text":
            value = str(value)
        elif expected_type.value == "json":
            # JSON type accepts arrays and objects
            if not isinstance(value, (list, dict)):
                raise ValueError(f"Setting {key} expects a JSON array or object")

        collection = self._get_collection()
        now = datetime.now(timezone.utc).isoformat()

        # Get default from SETTING_DEFINITIONS (single source of truth)
        default_value = _get_default_from_settings(key)

        await collection.update_one(
            {"_id": key},
            {
                "$set": {
                    "value": value,
                    "type": expected_type.value,
                    "category": definition["category"].value,
                    "description": definition["description"],
                    "default_value": default_value,
                    "updated_at": now,
                    "updated_by": user_id,
                }
            },
            upsert=True,
        )

        return await self.get(key)

    async def reset(self, key: Optional[str] = None) -> int:
        """Reset settings to default values"""
        collection = self._get_collection()

        if key:
            if key not in SETTING_DEFINITIONS:
                return 0
            result = await collection.delete_one({"_id": key})
            return 1 if result.deleted_count > 0 else 0
        else:
            # Reset all
            keys_to_delete = list(SETTING_DEFINITIONS.keys())
            result = await collection.delete_many({"_id": {"$in": keys_to_delete}})
            return result.deleted_count

    async def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None


# Re-export for backward compatibility
__all__ = [
    "RESTART_REQUIRED_SETTINGS",
    "SENSITIVE_SETTINGS",
    "SETTING_DEFINITIONS",
    "SettingsStorage",
]

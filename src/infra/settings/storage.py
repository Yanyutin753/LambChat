"""
Settings storage using MongoDB
"""

from typing import Any, Optional

from pymongo import ReturnDocument

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import (
    RESTART_REQUIRED_SETTINGS,
    SETTING_DEFINITIONS,
    _get_default_from_settings,
    settings,
)
from src.kernel.schemas.setting import SettingItem

_MONGODB_POOL_SIZE_SETTINGS = {
    "MONGODB_POOL_MIN_SIZE": ("min", "MONGODB_POOL_MAX_SIZE"),
    "MONGODB_POOL_MAX_SIZE": ("max", "MONGODB_POOL_MIN_SIZE"),
    "CHECKPOINT_MONGO_POOL_MIN_SIZE": ("min", "CHECKPOINT_MONGO_POOL_MAX_SIZE"),
    "CHECKPOINT_MONGO_POOL_MAX_SIZE": ("max", "CHECKPOINT_MONGO_POOL_MIN_SIZE"),
}
_MONGODB_POOL_GROUPS = {
    "business": ("MONGODB_POOL_MIN_SIZE", "MONGODB_POOL_MAX_SIZE"),
    "checkpoint": (
        "CHECKPOINT_MONGO_POOL_MIN_SIZE",
        "CHECKPOINT_MONGO_POOL_MAX_SIZE",
    ),
}
_MONGODB_POOL_PAIR_DOC_ID = "__settings_atomic__:mongodb_pools"

logger = get_logger(__name__)


def _validate_mongodb_pool_size_bounds(key: str, value: Any) -> None:
    pool_setting = _MONGODB_POOL_SIZE_SETTINGS.get(key)
    if pool_setting is None:
        return
    kind, _ = pool_setting
    if type(value) is not int:
        raise ValueError(f"Setting {key} pool size must be an integer")
    if (kind == "min" and value < 0) or (kind == "max" and value < 1):
        lower_bound = 0 if kind == "min" else 1
        raise ValueError(f"Setting {key} pool size must be at least {lower_bound}")


def _validate_mongodb_pool_size_pair(key: str, value: int, paired_value: Any) -> None:
    kind, paired_key = _MONGODB_POOL_SIZE_SETTINGS[key]
    _validate_mongodb_pool_size_bounds(paired_key, paired_value)
    if kind == "min" and value > paired_value:
        raise ValueError(f"Setting {key} must not exceed {paired_key} ({paired_value})")
    if kind == "max" and value < paired_value:
        raise ValueError(f"Setting {key} must be at least {paired_key} ({paired_value})")


def _mongodb_pool_group(key: str) -> str:
    return "checkpoint" if key.startswith("CHECKPOINT_") else "business"


def _mongodb_pool_pair_key(_key: str) -> str:
    return _MONGODB_POOL_PAIR_DOC_ID


def _pool_pair_values_from_docs(docs: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Resolve safe authoritative values from legacy documents or defaults."""
    values: dict[str, int] = {}
    for group, (min_key, max_key) in _MONGODB_POOL_GROUPS.items():
        min_value = docs.get(min_key, {}).get("value", _get_default_from_settings(min_key))
        max_value = docs.get(max_key, {}).get("value", _get_default_from_settings(max_key))
        try:
            _validate_mongodb_pool_size_bounds(min_key, min_value)
            _validate_mongodb_pool_size_bounds(max_key, max_value)
            _validate_mongodb_pool_size_pair(min_key, min_value, max_value)
        except ValueError:
            min_value = _get_default_from_settings(min_key)
            max_value = _get_default_from_settings(max_key)
        values[f"{group}_min"] = min_value
        values[f"{group}_max"] = max_value
    return values


def _mongodb_pool_pair_keys() -> list[str]:
    return [_MONGODB_POOL_PAIR_DOC_ID]


def _pool_pair_field(key: str) -> str:
    return f"{_mongodb_pool_group(key)}_{_MONGODB_POOL_SIZE_SETTINGS[key][0]}"


def _pool_pair_condition(key: str, value: int) -> dict[str, Any]:
    kind, _ = _MONGODB_POOL_SIZE_SETTINGS[key]
    paired_field = f"{_mongodb_pool_group(key)}_{'max' if kind == 'min' else 'min'}"
    return {paired_field: {"$gte": value}} if kind == "min" else {paired_field: {"$lte": value}}


def _pool_pair_value(key: str, pair: dict[str, Any]) -> int:
    return pair[_pool_pair_field(key)]


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

    async def _read_mongodb_pool_pair(self, key: str) -> dict[str, Any]:
        collection = self._get_collection()
        pair = await collection.find_one({"_id": _mongodb_pool_pair_key(key)})
        if pair is not None:
            return pair
        docs: dict[str, dict[str, Any]] = {}
        for min_key, max_key in _MONGODB_POOL_GROUPS.values():
            for setting_key in (min_key, max_key):
                doc = await collection.find_one({"_id": setting_key}, {"value": 1})
                if doc is not None:
                    docs[setting_key] = doc
        return _pool_pair_values_from_docs(docs)

    async def _ensure_mongodb_pool_pair(self, key: str) -> dict[str, Any]:
        """Create the authoritative pair once, preserving valid legacy overrides."""
        collection = self._get_collection()
        pair_key = _mongodb_pool_pair_key(key)
        existing = await collection.find_one({"_id": pair_key})
        if existing is not None:
            return existing
        initial = await self._read_mongodb_pool_pair(key)
        await collection.update_one(
            {"_id": pair_key},
            {"$setOnInsert": initial},
            upsert=True,
        )
        pair = await collection.find_one({"_id": pair_key})
        if pair is None:
            raise RuntimeError("Failed to initialize MongoDB pool setting pair")
        return pair

    async def _update_mongodb_pool_pair(self, key: str, value: int) -> None:
        collection = self._get_collection()
        pair = await self._ensure_mongodb_pool_pair(key)
        kind = _pool_pair_field(key)
        paired_key = _MONGODB_POOL_SIZE_SETTINGS[key][1]
        paired_value = pair[_pool_pair_field(paired_key)]
        _validate_mongodb_pool_size_pair(key, value, paired_value)
        updated = await collection.find_one_and_update(
            {"_id": _mongodb_pool_pair_key(key), **_pool_pair_condition(key, value)},
            {"$set": {kind: value}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            # A competing writer changed the counterpart after our first read.
            latest = await self._read_mongodb_pool_pair(key)
            latest_paired = latest[_pool_pair_field(paired_key)]
            _validate_mongodb_pool_size_pair(key, value, latest_paired)
            raise ValueError("Concurrent MongoDB pool setting update; retry the request")

    async def _get_effective_value(self, key: str) -> Any:
        if key in _MONGODB_POOL_SIZE_SETTINGS:
            pair = await self._read_mongodb_pool_pair(key)
            return _pool_pair_value(key, pair)
        collection = self._get_collection()
        doc = await collection.find_one({"_id": key}, {"value": 1})
        return doc["value"] if doc is not None else _get_default_from_settings(key)

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
        setting_keys = list(SETTING_DEFINITIONS.keys())
        stored_keys = [*setting_keys, *_mongodb_pool_pair_keys()]
        cursor = collection.find(
            {"_id": {"$in": stored_keys}},
            {
                "_id": 1,
                "value": 1,
                "business_min": 1,
                "business_max": 1,
                "checkpoint_min": 1,
                "checkpoint_max": 1,
                "updated_at": 1,
                "updated_by": 1,
            },
        )
        db_settings = {doc["_id"]: doc for doc in await cursor.to_list(length=len(stored_keys))}

        result: dict[str, list[SettingItem]] = {}

        for key, definition in SETTING_DEFINITIONS.items():
            # Filter non-admin users
            if not admin_mode and not definition.get("frontend_visible", False):
                continue

            category = definition["category"].value
            if category not in result:
                result[category] = []

            # Get default from SETTING_DEFINITIONS (single source of truth)
            default_value = _get_default_from_settings(key, SETTING_DEFINITIONS)

            # Use DB value if exists, otherwise use default
            db_doc = db_settings.get(key)
            value: Any
            if key in _MONGODB_POOL_SIZE_SETTINGS:
                pair = db_settings.get(_mongodb_pool_pair_key(key))
                if pair is None:
                    pair = _pool_pair_values_from_docs(db_settings)
                value = _pool_pair_value(key, pair)
            else:
                value = db_doc["value"] if db_doc else default_value

            is_sensitive = definition.get("is_sensitive", False)

            # Mask sensitive settings in API responses
            if mask_sensitive and is_sensitive and value:
                value = "********"

            item = SettingItem(
                key=key,
                value=value,
                type=definition["type"],
                category=definition["category"],
                subcategory=definition.get("subcategory", ""),
                description=definition["description"],
                default_value=default_value,
                requires_restart=key in RESTART_REQUIRED_SETTINGS,
                is_sensitive=is_sensitive,
                frontend_visible=definition.get("frontend_visible", False),
                depends_on=definition.get("depends_on"),
                options=definition.get("options"),
                json_schema=definition.get("json_schema"),
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
        """Internal method to get setting by key

        单行坏数据（字段类型漂移等）在此被吞掉并告警，返回 None 视为该行
        不存在（回退默认值）——绝不因一行脏数据炸掉应用启动（生产实测：
        Date 类型的 updated_at 曾让全站 CrashLoop）。
        """
        definition = SETTING_DEFINITIONS.get(key)
        if not definition:
            return None

        collection = self._get_collection()
        doc = await collection.find_one({"_id": key})

        # Get default from SETTING_DEFINITIONS (single source of truth)
        default_value = _get_default_from_settings(key)

        value: Any
        if key in _MONGODB_POOL_SIZE_SETTINGS:
            pair = await self._read_mongodb_pool_pair(key)
            value = _pool_pair_value(key, pair)
        else:
            value = doc["value"] if doc else default_value

        is_sensitive = definition.get("is_sensitive", False)

        # Mask sensitive settings in API responses (if requested)
        if mask_sensitive and is_sensitive and value:
            value = "********"

        try:
            return SettingItem(
                key=key,
                value=value,
                type=definition["type"],
                category=definition["category"],
                subcategory=definition.get("subcategory", ""),
                description=definition["description"],
                default_value=default_value,
                requires_restart=key in RESTART_REQUIRED_SETTINGS,
                is_sensitive=is_sensitive,
                frontend_visible=definition.get("frontend_visible", False),
                depends_on=definition.get("depends_on"),
                options=definition.get("options"),
                json_schema=definition.get("json_schema"),
                updated_at=doc.get("updated_at") if doc else None,
                updated_by=doc.get("updated_by") if doc else None,
            )
        except Exception as exc:
            logger.warning(
                "[Settings] Skipping malformed row %s (%s: %s); falling back to default",
                key,
                type(exc).__name__,
                exc,
            )
            return None

    async def set(self, key: str, value: Any, user_id: str) -> Optional[SettingItem]:
        """Set setting value"""
        definition = SETTING_DEFINITIONS.get(key)
        if not definition:
            return None

        # Don't allow setting masked values
        if value == "********":
            raise ValueError("Cannot set masked value")

        _validate_mongodb_pool_size_bounds(key, value)

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
        elif expected_type.value == "select":
            valid_options = definition.get("options", [])
            if valid_options and value not in valid_options:
                raise ValueError(f"Setting {key} expects one of: {valid_options}")
            value = str(value)
        elif expected_type.value == "json":
            # JSON type accepts arrays and objects
            if not isinstance(value, (list, dict)):
                raise ValueError(f"Setting {key} expects a JSON array or object")

        collection = self._get_collection()
        now = utc_now_iso()

        # Get default from SETTING_DEFINITIONS (single source of truth)
        default_value = _get_default_from_settings(key)

        async def _persist() -> None:
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

        if key not in _MONGODB_POOL_SIZE_SETTINGS:
            await _persist()
        else:
            await self._update_mongodb_pool_pair(key, value)
            try:
                await _persist()
            except Exception as exc:
                logger.warning(
                    "Authoritative pool setting %s was saved, but its audit mirror failed: %s",
                    key,
                    exc,
                )

        return await self.get(key)

    async def reset(self, key: Optional[str] = None) -> int:
        """Reset settings to default values"""
        collection = self._get_collection()

        if key:
            if key not in SETTING_DEFINITIONS:
                return 0
            if key not in _MONGODB_POOL_SIZE_SETTINGS:
                result = await collection.delete_one({"_id": key})
            else:
                default_value = _get_default_from_settings(key)
                _validate_mongodb_pool_size_bounds(key, default_value)
                await self._update_mongodb_pool_pair(key, default_value)
                try:
                    result = await collection.delete_one({"_id": key})
                except Exception as exc:
                    logger.warning(
                        "Authoritative pool setting %s was reset, but its audit mirror failed: %s",
                        key,
                        exc,
                    )

                    class _BestEffortResetResult:
                        deleted_count = 1

                    result = _BestEffortResetResult()
                return 1
            return 1 if result.deleted_count > 0 else 0
        else:
            # Reset all
            non_pool_keys = [
                setting_key
                for setting_key in SETTING_DEFINITIONS
                if setting_key not in _MONGODB_POOL_SIZE_SETTINGS
            ]
            result = await collection.delete_many({"_id": {"$in": non_pool_keys}})
            defaults = {
                f"{group}_min": _get_default_from_settings(min_key)
                for group, (min_key, _) in _MONGODB_POOL_GROUPS.items()
            }
            defaults.update(
                {
                    f"{group}_max": _get_default_from_settings(max_key)
                    for group, (_, max_key) in _MONGODB_POOL_GROUPS.items()
                }
            )
            await collection.update_one(
                {"_id": _MONGODB_POOL_PAIR_DOC_ID},
                {"$set": defaults},
                upsert=True,
            )
            try:
                mirror_result = await collection.delete_many(
                    {"_id": {"$in": list(_MONGODB_POOL_SIZE_SETTINGS)}}
                )
            except Exception as exc:
                logger.warning(
                    "MongoDB pool settings were reset, but audit mirror cleanup failed: %s",
                    exc,
                )
                mirror_count = 0
            else:
                mirror_count = mirror_result.deleted_count
            return result.deleted_count + mirror_count

    async def close(self):
        """Close MongoDB connection (only clears local refs, does not close global client)"""
        self._client = None
        self._collection = None


# Re-export for backward compatibility
__all__ = [
    "RESTART_REQUIRED_SETTINGS",
    "SETTING_DEFINITIONS",
    "SettingsStorage",
]

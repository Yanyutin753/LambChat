"""Storage and service layer for plugin-owned settings."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.infra.utils.datetime import utc_now
from src.kernel.config import SETTING_DEFINITIONS
from src.kernel.extensions.manifest import PluginManifest, PluginSettingDefinition

MASKED_SECRET_VALUE = "********"
SETTINGS_STORAGE_READ_TIMEOUT_SECONDS = 0.75
LEGACY_SYSTEM_SETTING_READ_TIMEOUT_SECONDS = 0.75


@dataclass(frozen=True)
class PluginSettingRecord:
    plugin_id: str
    key: str
    value: Any
    scope: str = "system"
    subject_id: str | None = None
    is_sensitive: bool = False
    source: str = "manual"
    updated_at: Any = None
    updated_by: str | None = None


class InMemoryPluginSettingsStorage:
    """Test-friendly plugin settings storage."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str, str | None], PluginSettingRecord] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def get(
        self,
        *,
        plugin_id: str,
        key: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> PluginSettingRecord | None:
        return self.records.get((plugin_id, scope, key, subject_id))

    async def list(
        self,
        *,
        plugin_id: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> list[PluginSettingRecord]:
        return [
            record
            for (record_plugin_id, record_scope, _key, record_subject_id), record in self.records.items()
            if record_plugin_id == plugin_id
            and record_scope == scope
            and record_subject_id == subject_id
        ]

    async def list_all(self, *, plugin_id: str) -> list[PluginSettingRecord]:
        return [
            record
            for (record_plugin_id, _scope, _key, _subject_id), record in self.records.items()
            if record_plugin_id == plugin_id
        ]

    async def set(
        self,
        *,
        plugin_id: str,
        key: str,
        value: Any,
        scope: str = "system",
        subject_id: str | None = None,
        is_sensitive: bool = False,
        source: str = "manual",
        updated_by: str | None = None,
    ) -> PluginSettingRecord:
        record = PluginSettingRecord(
            plugin_id=plugin_id,
            key=key,
            value=value,
            scope=scope,
            subject_id=subject_id,
            is_sensitive=is_sensitive,
            source=source,
            updated_at=utc_now(),
            updated_by=updated_by,
        )
        self.records[(plugin_id, scope, key, subject_id)] = record
        return record

    async def delete(
        self,
        *,
        plugin_id: str,
        key: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> bool:
        return self.records.pop((plugin_id, scope, key, subject_id), None) is not None


class MongoPluginSettingsStorage:
    """Mongo-backed plugin settings storage."""

    COLLECTION = "plugin_settings"

    def __init__(self) -> None:
        self._collection = None
        self._indexes_created = False

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            client = get_mongo_client()
            self._collection = client[settings.MONGODB_DB][self.COLLECTION]
        return self._collection

    async def ensure_indexes(self) -> None:
        if self._indexes_created:
            return
        await self.collection.create_index(
            [("plugin_id", 1), ("scope", 1), ("subject_id", 1), ("key", 1)],
            unique=True,
        )
        await self.collection.create_index([("plugin_id", 1), ("scope", 1)])
        self._indexes_created = True

    async def get(
        self,
        *,
        plugin_id: str,
        key: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> PluginSettingRecord | None:
        await self.ensure_indexes()
        doc = await self.collection.find_one(
            {"plugin_id": plugin_id, "scope": scope, "subject_id": subject_id, "key": key}
        )
        return _record_from_doc(doc) if doc else None

    async def list(
        self,
        *,
        plugin_id: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> list[PluginSettingRecord]:
        await self.ensure_indexes()
        cursor = self.collection.find(
            {"plugin_id": plugin_id, "scope": scope, "subject_id": subject_id}
        )
        return [_record_from_doc(doc) async for doc in cursor]

    async def list_all(self, *, plugin_id: str) -> list[PluginSettingRecord]:
        await self.ensure_indexes()
        cursor = self.collection.find({"plugin_id": plugin_id})
        return [_record_from_doc(doc) async for doc in cursor]

    async def set(
        self,
        *,
        plugin_id: str,
        key: str,
        value: Any,
        scope: str = "system",
        subject_id: str | None = None,
        is_sensitive: bool = False,
        source: str = "manual",
        updated_by: str | None = None,
    ) -> PluginSettingRecord:
        await self.ensure_indexes()
        now = utc_now()
        doc = {
            "plugin_id": plugin_id,
            "scope": scope,
            "subject_id": subject_id,
            "key": key,
            "value": value,
            "is_sensitive": is_sensitive,
            "source": source,
            "updated_at": now,
            "updated_by": updated_by,
        }
        await self.collection.update_one(
            {"plugin_id": plugin_id, "scope": scope, "subject_id": subject_id, "key": key},
            {"$set": doc},
            upsert=True,
        )
        return _record_from_doc(doc)

    async def delete(
        self,
        *,
        plugin_id: str,
        key: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> bool:
        await self.ensure_indexes()
        result = await self.collection.delete_one(
            {"plugin_id": plugin_id, "scope": scope, "subject_id": subject_id, "key": key}
        )
        return bool(result.deleted_count)


def _record_from_doc(doc: dict[str, Any]) -> PluginSettingRecord:
    return PluginSettingRecord(
        plugin_id=doc["plugin_id"],
        key=doc["key"],
        value=doc.get("value"),
        scope=doc.get("scope", "system"),
        subject_id=doc.get("subject_id"),
        is_sensitive=bool(doc.get("is_sensitive", False)),
        source=doc.get("source", "manual"),
        updated_at=doc.get("updated_at"),
        updated_by=doc.get("updated_by"),
    )


class PluginSettingsService:
    """Manifest-driven plugin settings service."""

    def __init__(self, *, storage: Any | None = None) -> None:
        self.storage = storage or get_plugin_settings_storage()

    async def list_settings(
        self,
        manifest: PluginManifest,
        *,
        mask_sensitive: bool = True,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            stored_records = await asyncio.wait_for(
                self.storage.list(
                    plugin_id=manifest.id,
                    scope=scope,
                    subject_id=subject_id,
                ),
                timeout=SETTINGS_STORAGE_READ_TIMEOUT_SECONDS,
            )
        except Exception:
            stored_records = []
        records = {record.key: record for record in stored_records}
        values = []
        scoped_definitions = [
            definition for definition in manifest.settings if definition.scope == scope
        ]
        for definition in sorted(scoped_definitions, key=lambda item: (item.group, item.order, item.key)):
            record = records.get(definition.key)
            value, source = await self._resolved_value(manifest, definition, record)
            if mask_sensitive and definition.sensitive and value not in (None, ""):
                value = MASKED_SECRET_VALUE
            values.append(
                {
                    "key": definition.key,
                    "qualified_key": f"{manifest.id}.{definition.key}",
                    "value": value,
                    "type": definition.type,
                    "label": definition.label,
                    "description": definition.description,
                    "group": definition.group,
                    "order": definition.order,
                    "default_value": definition.default,
                    "sensitive": definition.sensitive,
                    "required": definition.required,
                    "requires_restart": definition.requires_restart,
                    "scope": definition.scope,
                    "source": record.source if record else source,
                    "updated_at": record.updated_at if record else None,
                    "updated_by": record.updated_by if record else None,
                    "legacy_system_setting_keys": definition.legacy_system_setting_keys,
                    "options": definition.options,
                    "json_schema": definition.json_schema,
                    "visible_when": (
                        definition.visible_when.model_dump() if definition.visible_when else None
                    ),
                }
            )
        return values

    async def export_settings(
        self,
        manifest: PluginManifest,
        *,
        mask_sensitive: bool = True,
    ) -> list[dict[str, Any]]:
        """Export manifest-declared plugin settings across all scopes and subjects."""
        exported: list[dict[str, Any]] = []
        stored_records: list[PluginSettingRecord] = []
        list_all = getattr(self.storage, "list_all", None)
        if callable(list_all):
            try:
                stored_records = await asyncio.wait_for(
                    list_all(plugin_id=manifest.id),
                    timeout=SETTINGS_STORAGE_READ_TIMEOUT_SECONDS,
                )
            except Exception:
                stored_records = []

        exported_keys: set[tuple[str, str, str | None]] = set()
        definitions = {(definition.scope, definition.key): definition for definition in manifest.settings}
        for record in sorted(
            stored_records,
            key=lambda item: (item.scope, item.subject_id or "", item.key),
        ):
            definition = definitions.get((record.scope, record.key))
            if definition is None:
                continue
            exported.append(
                self._setting_payload(
                    manifest,
                    definition,
                    record,
                    value=record.value,
                    source=record.source,
                    mask_sensitive=mask_sensitive,
                    subject_id=record.subject_id,
                )
            )
            exported_keys.add((record.scope, record.key, record.subject_id))

        for definition in sorted(
            manifest.settings,
            key=lambda item: (item.scope, item.group, item.order, item.key),
        ):
            export_key = (definition.scope, definition.key, None)
            if export_key in exported_keys:
                continue
            record = None
            value, source = await self._resolved_value(manifest, definition, record)
            exported.append(
                self._setting_payload(
                    manifest,
                    definition,
                    record,
                    value=value,
                    source=source,
                    mask_sensitive=mask_sensitive,
                    subject_id=None,
                )
            )
        return exported

    async def set_setting(
        self,
        manifest: PluginManifest,
        *,
        key: str,
        value: Any,
        updated_by: str | None,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> PluginSettingRecord:
        definition = _definition_for_key(manifest, key, scope=scope)
        if definition.sensitive and value == MASKED_SECRET_VALUE:
            existing = await self.storage.get(
                plugin_id=manifest.id,
                key=definition.key,
                scope=scope,
                subject_id=subject_id,
            )
            if existing:
                return existing
            value, _source = await self._resolved_value(manifest, definition, None)
        parsed_value = self._parse_value(definition, value)
        return await self.storage.set(
            plugin_id=manifest.id,
            key=definition.key,
            value=parsed_value,
            scope=scope,
            subject_id=subject_id,
            is_sensitive=definition.sensitive,
            source="manual",
            updated_by=updated_by,
        )

    async def reset_setting(
        self,
        manifest: PluginManifest,
        *,
        key: str,
        scope: str = "system",
        subject_id: str | None = None,
    ) -> bool:
        definition = _definition_for_key(manifest, key, scope=scope)
        return await self.storage.delete(
            plugin_id=manifest.id,
            key=definition.key,
            scope=scope,
            subject_id=subject_id,
        )

    async def import_legacy(
        self,
        manifest: PluginManifest,
        *,
        updated_by: str | None = "system:plugin-settings-import",
    ) -> dict[str, Any]:
        imported: list[str] = []
        skipped: list[str] = []
        for definition in manifest.settings:
            if definition.scope != "system":
                skipped.append(definition.key)
                continue
            existing = await self.storage.get(plugin_id=manifest.id, key=definition.key)
            if existing is not None:
                skipped.append(definition.key)
                continue
            value, source = await self._resolved_value(manifest, definition, None)
            if source == "default":
                skipped.append(definition.key)
                continue
            await self.storage.set(
                plugin_id=manifest.id,
                key=definition.key,
                value=self._parse_value(definition, value),
                is_sensitive=definition.sensitive,
                source=source,
                updated_by=updated_by,
            )
            imported.append(definition.key)
        return {"imported": imported, "skipped": skipped, "failed": []}

    def _setting_payload(
        self,
        manifest: PluginManifest,
        definition: PluginSettingDefinition,
        record: PluginSettingRecord | None,
        *,
        value: Any,
        source: str,
        mask_sensitive: bool,
        subject_id: str | None,
    ) -> dict[str, Any]:
        if mask_sensitive and definition.sensitive and value not in (None, ""):
            value = MASKED_SECRET_VALUE
        return {
            "key": definition.key,
            "qualified_key": f"{manifest.id}.{definition.key}",
            "value": value,
            "type": definition.type,
            "label": definition.label,
            "description": definition.description,
            "group": definition.group,
            "order": definition.order,
            "default_value": definition.default,
            "sensitive": definition.sensitive,
            "required": definition.required,
            "requires_restart": definition.requires_restart,
            "scope": definition.scope,
            "subject_id": subject_id,
            "source": record.source if record else source,
            "updated_at": record.updated_at if record else None,
            "updated_by": record.updated_by if record else None,
            "legacy_system_setting_keys": definition.legacy_system_setting_keys,
            "options": definition.options,
            "json_schema": definition.json_schema,
            "visible_when": (
                definition.visible_when.model_dump() if definition.visible_when else None
            ),
        }

    async def _resolved_value(
        self,
        manifest: PluginManifest,
        definition: PluginSettingDefinition,
        record: PluginSettingRecord | None,
    ) -> tuple[Any, str]:
        if record is not None:
            return record.value, record.source
        data_value = _plugin_data_config_value(manifest, definition.key, "current.json")
        if data_value not in (None, "", MASKED_SECRET_VALUE):
            return data_value, "plugin_data:current"
        for legacy_key in definition.legacy_system_setting_keys:
            legacy_value = await _legacy_system_setting_value(legacy_key)
            if legacy_value not in (None, ""):
                return legacy_value, f"legacy:{legacy_key}"
        if definition.env_fallback:
            env_value = os.environ.get(definition.env_fallback)
            if env_value not in (None, ""):
                return env_value, f"env:{definition.env_fallback}"
        data_default = _plugin_data_config_value(manifest, definition.key, "defaults.json")
        if data_default not in (None, "", MASKED_SECRET_VALUE):
            return data_default, "plugin_data:default"
        return definition.default, "default"

    def _parse_value(self, definition: PluginSettingDefinition, value: Any) -> Any:
        if definition.type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in {"true", "1", "yes", "on"}
            return bool(value)
        if definition.type == "number":
            if isinstance(value, int | float):
                return value
            number = float(value)
            return int(number) if number.is_integer() else number
        if definition.type == "select" and definition.options and value not in definition.options:
            raise ValueError(f"invalid option for {definition.key}")
        return value


class PluginSettingsResolver:
    """Typed resolver used by plugin runtime code."""

    def __init__(
        self,
        *,
        plugin_id: str,
        manifests: tuple[PluginManifest, ...] | None = None,
        service: PluginSettingsService | None = None,
    ) -> None:
        from src.kernel.extensions.builtin_plugins import BUILTIN_PLUGIN_MANIFESTS

        self.plugin_id = plugin_id
        self.manifests = manifests or BUILTIN_PLUGIN_MANIFESTS
        self.service = service or PluginSettingsService()

    @property
    def manifest(self) -> PluginManifest:
        for manifest in self.manifests:
            if manifest.id == self.plugin_id:
                return manifest
        raise KeyError(f"unknown plugin {self.plugin_id}")

    async def get(self, key: str, default: Any = None) -> Any:
        definition = _definition_for_key(self.manifest, key)
        try:
            record = await asyncio.wait_for(
                self.service.storage.get(plugin_id=self.plugin_id, key=definition.key),
                timeout=SETTINGS_STORAGE_READ_TIMEOUT_SECONDS,
            )
        except Exception:
            record = None
        value, _source = await self.service._resolved_value(self.manifest, definition, record)
        return default if value is None else self.service._parse_value(definition, value)

    async def get_secret(self, key: str) -> str:
        value = await self.get(key, "")
        return "" if value is None else str(value)

    async def get_str(self, key: str, default: str = "") -> str:
        value = await self.get(key, default)
        return default if value is None else str(value)

    async def get_int(self, key: str, default: int = 0) -> int:
        value = await self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


def _definition_for_key(
    manifest: PluginManifest,
    key: str,
    *,
    scope: str | None = None,
) -> PluginSettingDefinition:
    for definition in manifest.settings:
        if definition.key == key and (scope is None or definition.scope == scope):
            return definition
    suffix = f" in scope {scope}" if scope else ""
    raise KeyError(f"plugin setting {manifest.id}.{key}{suffix} is not declared")


def _plugin_data_config_value(manifest: PluginManifest, key: str, filename: str) -> Any:
    if not manifest.package_data_dir:
        return None
    path = os.path.join(manifest.package_data_dir, "config", filename)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


async def _legacy_system_setting_value(key: str) -> Any:
    if key not in SETTING_DEFINITIONS:
        return os.environ.get(key)
    try:
        from src.infra.settings.service import SettingsService

        return await asyncio.wait_for(
            SettingsService.get_instance().get_plugin_owned_legacy_raw(key),
            timeout=LEGACY_SYSTEM_SETTING_READ_TIMEOUT_SECONDS,
        )
    except Exception:
        env_value = os.environ.get(key)
        return env_value if env_value is not None else SETTING_DEFINITIONS[key].get("default")


def plugin_owned_system_setting_keys(manifests: tuple[PluginManifest, ...]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for manifest in manifests:
        for key in manifest.legacy_setting_keys():
            mapping[key] = manifest.id
    return mapping


@lru_cache
def get_plugin_settings_storage() -> MongoPluginSettingsStorage:
    return MongoPluginSettingsStorage()


def get_plugin_settings_service() -> PluginSettingsService:
    return PluginSettingsService()

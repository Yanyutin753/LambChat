"""Persistent state and audit storage for Plugin Runtime controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.extensions import PluginRuntimeStatus
from src.kernel.extensions.dry_run import PluginUninstallDryRun


@dataclass(frozen=True)
class PluginRuntimeStateOverride:
    plugin_id: str
    status: PluginRuntimeStatus
    updated_at: datetime
    updated_by: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PluginRuntimeAuditRecord:
    plugin_id: str
    action: str
    previous_status: PluginRuntimeStatus | None
    next_status: PluginRuntimeStatus
    actor_user_id: str | None
    actor_username: str | None
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class PluginPackageReviewRecord:
    plugin_id: str
    package_sha256: str
    reviewed_at: datetime
    reviewed_by: str | None = None
    reviewer_username: str | None = None
    reason: str | None = None


class InMemoryPluginRuntimeStateStorage:
    """Test-friendly storage with the same async contract as Mongo storage."""

    def __init__(self) -> None:
        self.overrides: dict[str, PluginRuntimeStateOverride] = {}
        self.audit_records: list[PluginRuntimeAuditRecord] = []
        self.dry_runs: dict[str, PluginUninstallDryRun] = {}
        self.package_reviews: dict[tuple[str, str], PluginPackageReviewRecord] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def get_override(self, plugin_id: str) -> PluginRuntimeStateOverride | None:
        return self.overrides.get(plugin_id)

    async def list_overrides(self) -> list[PluginRuntimeStateOverride]:
        return list(self.overrides.values())

    async def set_override(
        self,
        *,
        plugin_id: str,
        status: PluginRuntimeStatus,
        updated_by: str | None,
        reason: str | None = None,
    ) -> PluginRuntimeStateOverride:
        override = PluginRuntimeStateOverride(
            plugin_id=plugin_id,
            status=status,
            updated_at=utc_now(),
            updated_by=updated_by,
            reason=reason,
        )
        self.overrides[plugin_id] = override
        return override

    async def append_audit(
        self,
        *,
        plugin_id: str,
        action: str,
        previous_status: PluginRuntimeStatus | None,
        next_status: PluginRuntimeStatus,
        actor_user_id: str | None,
        actor_username: str | None,
        reason: str | None = None,
    ) -> PluginRuntimeAuditRecord:
        record = PluginRuntimeAuditRecord(
            plugin_id=plugin_id,
            action=action,
            previous_status=previous_status,
            next_status=next_status,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            reason=reason,
            created_at=utc_now(),
        )
        self.audit_records.append(record)
        return record

    async def list_audit(
        self,
        *,
        plugin_id: str,
        limit: int = 20,
    ) -> list[PluginRuntimeAuditRecord]:
        records = [record for record in self.audit_records if record.plugin_id == plugin_id]
        return list(reversed(records))[: max(1, min(limit, 100))]

    async def save_uninstall_dry_run(
        self,
        *,
        dry_run: PluginUninstallDryRun,
    ) -> PluginUninstallDryRun:
        self.dry_runs[dry_run.plugin_id] = dry_run
        return dry_run

    async def get_uninstall_dry_run(
        self,
        *,
        plugin_id: str,
        snapshot_id: str | None = None,
    ) -> PluginUninstallDryRun | None:
        dry_run = self.dry_runs.get(plugin_id)
        if dry_run is None:
            return None
        if snapshot_id is not None and dry_run.snapshot_id != snapshot_id:
            return None
        return dry_run

    async def set_package_review(
        self,
        *,
        plugin_id: str,
        package_sha256: str,
        reviewed_by: str | None,
        reviewer_username: str | None,
        reason: str | None = None,
    ) -> PluginPackageReviewRecord:
        record = PluginPackageReviewRecord(
            plugin_id=plugin_id,
            package_sha256=package_sha256,
            reviewed_at=utc_now(),
            reviewed_by=reviewed_by,
            reviewer_username=reviewer_username,
            reason=reason,
        )
        self.package_reviews[(plugin_id, package_sha256)] = record
        return record

    async def get_package_review(
        self,
        *,
        plugin_id: str,
        package_sha256: str,
    ) -> PluginPackageReviewRecord | None:
        return self.package_reviews.get((plugin_id, package_sha256))


class MongoPluginRuntimeStateStorage:
    """Mongo-backed runtime state overrides and audit records."""

    OVERRIDES_COLLECTION = "plugin_runtime_state"
    AUDIT_COLLECTION = "plugin_runtime_audit"
    DRY_RUN_COLLECTION = "plugin_uninstall_dry_runs"
    PACKAGE_REVIEW_COLLECTION = "plugin_package_reviews"

    def __init__(self) -> None:
        self._overrides_collection: Any | None = None
        self._audit_collection: Any | None = None
        self._dry_run_collection: Any | None = None
        self._package_review_collection: Any | None = None
        self._indexes_created = False

    @property
    def overrides_collection(self):
        if self._overrides_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._overrides_collection = db[self.OVERRIDES_COLLECTION]
        return self._overrides_collection

    @property
    def audit_collection(self):
        if self._audit_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._audit_collection = db[self.AUDIT_COLLECTION]
        return self._audit_collection

    @property
    def dry_run_collection(self):
        if self._dry_run_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._dry_run_collection = db[self.DRY_RUN_COLLECTION]
        return self._dry_run_collection

    @property
    def package_review_collection(self):
        if self._package_review_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._package_review_collection = db[self.PACKAGE_REVIEW_COLLECTION]
        return self._package_review_collection

    async def ensure_indexes(self) -> None:
        if self._indexes_created:
            return
        await self.overrides_collection.create_index([("plugin_id", 1)], unique=True)
        await self.audit_collection.create_index([("plugin_id", 1), ("created_at", -1)])
        await self.audit_collection.create_index([("created_at", -1)])
        await self.dry_run_collection.create_index([("plugin_id", 1)], unique=True)
        await self.dry_run_collection.create_index([("snapshot_id", 1)])
        await self.package_review_collection.create_index(
            [("plugin_id", 1), ("package_sha256", 1)],
            unique=True,
        )
        await self.package_review_collection.create_index([("reviewed_at", -1)])
        self._indexes_created = True

    async def get_override(self, plugin_id: str) -> PluginRuntimeStateOverride | None:
        await self.ensure_indexes()
        doc = await self.overrides_collection.find_one({"plugin_id": plugin_id})
        return _override_from_doc(doc) if doc else None

    async def list_overrides(self) -> list[PluginRuntimeStateOverride]:
        await self.ensure_indexes()
        cursor = self.overrides_collection.find({})
        return [_override_from_doc(doc) async for doc in cursor]

    async def set_override(
        self,
        *,
        plugin_id: str,
        status: PluginRuntimeStatus,
        updated_by: str | None,
        reason: str | None = None,
    ) -> PluginRuntimeStateOverride:
        await self.ensure_indexes()
        now = utc_now()
        doc = {
            "plugin_id": plugin_id,
            "status": status.value,
            "updated_at": now,
            "updated_by": updated_by,
            "reason": reason,
        }
        await self.overrides_collection.update_one(
            {"plugin_id": plugin_id},
            {"$set": doc},
            upsert=True,
        )
        return PluginRuntimeStateOverride(
            plugin_id=plugin_id,
            status=status,
            updated_at=now,
            updated_by=updated_by,
            reason=reason,
        )

    async def append_audit(
        self,
        *,
        plugin_id: str,
        action: str,
        previous_status: PluginRuntimeStatus | None,
        next_status: PluginRuntimeStatus,
        actor_user_id: str | None,
        actor_username: str | None,
        reason: str | None = None,
    ) -> PluginRuntimeAuditRecord:
        await self.ensure_indexes()
        now = utc_now()
        doc = {
            "plugin_id": plugin_id,
            "action": action,
            "previous_status": previous_status.value if previous_status else None,
            "next_status": next_status.value,
            "actor_user_id": actor_user_id,
            "actor_username": actor_username,
            "reason": reason,
            "created_at": now,
        }
        await self.audit_collection.insert_one(doc)
        return _audit_from_doc(doc)

    async def list_audit(
        self,
        *,
        plugin_id: str,
        limit: int = 20,
    ) -> list[PluginRuntimeAuditRecord]:
        await self.ensure_indexes()
        bounded_limit = max(1, min(limit, 100))
        cursor = (
            self.audit_collection.find({"plugin_id": plugin_id})
            .sort("created_at", -1)
            .limit(bounded_limit)
        )
        return [_audit_from_doc(doc) async for doc in cursor]

    async def save_uninstall_dry_run(
        self,
        *,
        dry_run: PluginUninstallDryRun,
    ) -> PluginUninstallDryRun:
        await self.ensure_indexes()
        doc = dry_run.to_dict()
        doc["plugin_id"] = dry_run.plugin_id
        doc["snapshot_id"] = dry_run.snapshot_id
        await self.dry_run_collection.update_one(
            {"plugin_id": dry_run.plugin_id},
            {"$set": doc},
            upsert=True,
        )
        return dry_run

    async def get_uninstall_dry_run(
        self,
        *,
        plugin_id: str,
        snapshot_id: str | None = None,
    ) -> PluginUninstallDryRun | None:
        await self.ensure_indexes()
        query: dict[str, Any] = {"plugin_id": plugin_id}
        if snapshot_id is not None:
            query["snapshot_id"] = snapshot_id
        doc = await self.dry_run_collection.find_one(query)
        return PluginUninstallDryRun.from_dict(doc) if doc else None

    async def set_package_review(
        self,
        *,
        plugin_id: str,
        package_sha256: str,
        reviewed_by: str | None,
        reviewer_username: str | None,
        reason: str | None = None,
    ) -> PluginPackageReviewRecord:
        await self.ensure_indexes()
        now = utc_now()
        doc = {
            "plugin_id": plugin_id,
            "package_sha256": package_sha256,
            "reviewed_at": now,
            "reviewed_by": reviewed_by,
            "reviewer_username": reviewer_username,
            "reason": reason,
        }
        await self.package_review_collection.update_one(
            {"plugin_id": plugin_id, "package_sha256": package_sha256},
            {"$set": doc},
            upsert=True,
        )
        return _package_review_from_doc(doc)

    async def get_package_review(
        self,
        *,
        plugin_id: str,
        package_sha256: str,
    ) -> PluginPackageReviewRecord | None:
        await self.ensure_indexes()
        doc = await self.package_review_collection.find_one(
            {"plugin_id": plugin_id, "package_sha256": package_sha256}
        )
        return _package_review_from_doc(doc) if doc else None


def _override_from_doc(doc: dict[str, Any]) -> PluginRuntimeStateOverride:
    return PluginRuntimeStateOverride(
        plugin_id=doc["plugin_id"],
        status=PluginRuntimeStatus(doc["status"]),
        updated_at=doc["updated_at"],
        updated_by=doc.get("updated_by"),
        reason=doc.get("reason"),
    )


def _audit_from_doc(doc: dict[str, Any]) -> PluginRuntimeAuditRecord:
    previous_status = doc.get("previous_status")
    return PluginRuntimeAuditRecord(
        plugin_id=doc["plugin_id"],
        action=doc["action"],
        previous_status=PluginRuntimeStatus(previous_status) if previous_status else None,
        next_status=PluginRuntimeStatus(doc["next_status"]),
        actor_user_id=doc.get("actor_user_id"),
        actor_username=doc.get("actor_username"),
        reason=doc.get("reason"),
        created_at=doc["created_at"],
    )


def _package_review_from_doc(doc: dict[str, Any]) -> PluginPackageReviewRecord:
    return PluginPackageReviewRecord(
        plugin_id=doc["plugin_id"],
        package_sha256=doc["package_sha256"],
        reviewed_at=doc["reviewed_at"],
        reviewed_by=doc.get("reviewed_by"),
        reviewer_username=doc.get("reviewer_username"),
        reason=doc.get("reason"),
    )


@lru_cache
def get_plugin_runtime_state_storage() -> MongoPluginRuntimeStateStorage:
    return MongoPluginRuntimeStateStorage()

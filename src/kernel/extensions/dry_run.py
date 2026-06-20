"""Uninstall dry-run planning for plugin-owned resources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from src.kernel.extensions.resources import (
    PluginResourceCleanupStrategy,
    PluginResourceLedger,
    PluginResourceRecord,
)


class PluginDryRunAction(str, Enum):
    DELETE = "delete"
    KEEP = "keep"
    ARCHIVE = "archive"
    MANUAL_REVIEW = "manual_review"
    FORBID_DELETE = "forbid_delete"


@dataclass(frozen=True)
class PluginDryRunResource:
    plugin_id: str
    resource_id: str
    resource_type: str
    action: PluginDryRunAction
    retention_policy: str
    cleanup_strategy: str
    scope: str
    requires_confirmation: bool = False
    irreversible: bool = False
    reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginUninstallDryRun:
    plugin_id: str
    created_at: datetime
    expires_at: datetime
    resource_fingerprint: str
    snapshot_id: str
    resources: list[PluginDryRunResource]
    warnings: list[str] = field(default_factory=list)
    requires_confirmation: list[str] = field(default_factory=list)
    rollback_notes: list[str] = field(default_factory=list)

    @property
    def resource_count(self) -> int:
        return len(self.resources)

    def by_action(self, action: PluginDryRunAction) -> list[PluginDryRunResource]:
        return [resource for resource in self.resources if resource.action is action]

    @property
    def will_delete(self) -> list[PluginDryRunResource]:
        return self.by_action(PluginDryRunAction.DELETE)

    @property
    def will_keep(self) -> list[PluginDryRunResource]:
        return self.by_action(PluginDryRunAction.KEEP)

    @property
    def will_archive(self) -> list[PluginDryRunResource]:
        return self.by_action(PluginDryRunAction.ARCHIVE)

    @property
    def needs_manual_review(self) -> list[PluginDryRunResource]:
        return self.by_action(PluginDryRunAction.MANUAL_REVIEW)

    @property
    def forbidden_to_delete(self) -> list[PluginDryRunResource]:
        return self.by_action(PluginDryRunAction.FORBID_DELETE)

    def to_dict(self) -> dict[str, object]:
        return {
            "plugin_id": self.plugin_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resource_fingerprint": self.resource_fingerprint,
            "snapshot_id": self.snapshot_id,
            "resources": [
                {
                    "plugin_id": resource.plugin_id,
                    "resource_id": resource.resource_id,
                    "resource_type": resource.resource_type,
                    "action": resource.action.value,
                    "retention_policy": resource.retention_policy,
                    "cleanup_strategy": resource.cleanup_strategy,
                    "scope": resource.scope,
                    "requires_confirmation": resource.requires_confirmation,
                    "irreversible": resource.irreversible,
                    "reason": resource.reason,
                    "metadata": dict(resource.metadata),
                }
                for resource in self.resources
            ],
            "warnings": list(self.warnings),
            "requires_confirmation": list(self.requires_confirmation),
            "rollback_notes": list(self.rollback_notes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PluginUninstallDryRun":
        resources_value = value.get("resources", [])
        warnings_value = value.get("warnings", [])
        requires_confirmation_value = value.get("requires_confirmation", [])
        rollback_notes_value = value.get("rollback_notes", [])
        return cls(
            plugin_id=str(value["plugin_id"]),
            created_at=_parse_datetime(str(value["created_at"])),
            expires_at=_parse_datetime(str(value["expires_at"])),
            resource_fingerprint=str(value["resource_fingerprint"]),
            snapshot_id=str(value["snapshot_id"]),
            resources=[
                PluginDryRunResource(
                    plugin_id=str(resource["plugin_id"]),
                    resource_id=str(resource["resource_id"]),
                    resource_type=str(resource["resource_type"]),
                    action=PluginDryRunAction(str(resource["action"])),
                    retention_policy=str(resource["retention_policy"]),
                    cleanup_strategy=str(resource["cleanup_strategy"]),
                    scope=str(resource["scope"]),
                    requires_confirmation=bool(resource.get("requires_confirmation", False)),
                    irreversible=bool(resource.get("irreversible", False)),
                    reason=str(resource.get("reason", "")),
                    metadata={
                        str(key): str(value)
                        for key, value in dict(resource.get("metadata", {})).items()
                    },
                )
                for resource in resources_value
                if isinstance(resource, dict)
            ]
            if isinstance(resources_value, list)
            else [],
            warnings=[str(item) for item in warnings_value]
            if isinstance(warnings_value, list)
            else [],
            requires_confirmation=[str(item) for item in requires_confirmation_value]
            if isinstance(requires_confirmation_value, list)
            else [],
            rollback_notes=[str(item) for item in rollback_notes_value]
            if isinstance(rollback_notes_value, list)
            else [],
        )


@dataclass(frozen=True)
class PluginUninstallDryRunValidation:
    plugin_id: str
    snapshot_id: str | None
    checked_at: datetime
    expires_at: datetime | None
    expected_resource_fingerprint: str | None
    current_resource_fingerprint: str
    allowed: bool
    expired: bool = False
    resource_changed: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


DEFAULT_DRY_RUN_TTL_SECONDS = 15 * 60


def build_uninstall_dry_run(
    *,
    plugin_id: str,
    ledger: PluginResourceLedger,
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_DRY_RUN_TTL_SECONDS,
) -> PluginUninstallDryRun:
    created_at = now or datetime.now(UTC)
    resources = ledger.list(plugin_id=plugin_id)
    dry_run_resources = [_resource_to_dry_run(record) for record in resources]
    resource_fingerprint = build_resource_fingerprint(plugin_id=plugin_id, ledger=ledger)
    expires_at = created_at + timedelta(seconds=max(1, int(ttl_seconds)))
    snapshot_id = _snapshot_id(
        plugin_id=plugin_id,
        created_at=created_at,
        resource_fingerprint=resource_fingerprint,
    )
    warnings: list[str] = []
    requires_confirmation: list[str] = []
    rollback_notes: list[str] = []

    if not dry_run_resources:
        warnings.append("No resource ledger entries were found for this plugin.")
    for resource in dry_run_resources:
        if resource.requires_confirmation:
            requires_confirmation.append(
                f"{resource.resource_type}:{resource.resource_id} requires confirmation"
            )
        if resource.irreversible:
            warnings.append(f"{resource.resource_type}:{resource.resource_id} may be irreversible")

    rollback_notes.append(
        "Uninstall execution must use this dry-run snapshot and only process plugin-owned resources."
    )
    return PluginUninstallDryRun(
        plugin_id=plugin_id,
        created_at=created_at,
        expires_at=expires_at,
        resource_fingerprint=resource_fingerprint,
        snapshot_id=snapshot_id,
        resources=dry_run_resources,
        warnings=warnings,
        requires_confirmation=requires_confirmation,
        rollback_notes=rollback_notes,
    )


def validate_uninstall_dry_run(
    dry_run: PluginUninstallDryRun | None,
    *,
    plugin_id: str,
    ledger: PluginResourceLedger,
    now: datetime | None = None,
    confirmed: bool = False,
) -> PluginUninstallDryRunValidation:
    """Validate that a dry-run snapshot can gate a future uninstall executor.

    This is a preflight only. It does not delete, archive, or mutate resources.
    """
    checked_at = now or datetime.now(UTC)
    current_fingerprint = build_resource_fingerprint(plugin_id=plugin_id, ledger=ledger)
    blockers: list[str] = []
    warnings: list[str] = []

    if dry_run is None:
        blockers.append("dry_run_required")
        return PluginUninstallDryRunValidation(
            plugin_id=plugin_id,
            snapshot_id=None,
            checked_at=checked_at,
            expires_at=None,
            expected_resource_fingerprint=None,
            current_resource_fingerprint=current_fingerprint,
            allowed=False,
            blockers=blockers,
        )

    if dry_run.plugin_id != plugin_id:
        blockers.append("dry_run_plugin_mismatch")

    expired = checked_at > dry_run.expires_at
    if expired:
        blockers.append("dry_run_expired")

    resource_changed = current_fingerprint != dry_run.resource_fingerprint
    if resource_changed:
        blockers.append("dry_run_resource_fingerprint_changed")

    cross_plugin_resources = [
        resource for resource in dry_run.resources if resource.plugin_id != plugin_id
    ]
    if cross_plugin_resources:
        blockers.append("dry_run_contains_other_plugin_resources")

    if dry_run.forbidden_to_delete:
        blockers.append("dry_run_contains_forbidden_delete_resources")
    if dry_run.needs_manual_review:
        blockers.append("dry_run_contains_manual_review_resources")
    if dry_run.requires_confirmation and not confirmed:
        blockers.append("dry_run_requires_confirmation")

    warnings.extend(dry_run.warnings)
    return PluginUninstallDryRunValidation(
        plugin_id=plugin_id,
        snapshot_id=dry_run.snapshot_id,
        checked_at=checked_at,
        expires_at=dry_run.expires_at,
        expected_resource_fingerprint=dry_run.resource_fingerprint,
        current_resource_fingerprint=current_fingerprint,
        allowed=not blockers,
        expired=expired,
        resource_changed=resource_changed,
        blockers=blockers,
        warnings=warnings,
    )


def build_resource_fingerprint(*, plugin_id: str, ledger: PluginResourceLedger) -> str:
    """Build a stable fingerprint for uninstall-relevant resource ownership state."""
    resources = sorted(
        ledger.list(plugin_id=plugin_id),
        key=lambda item: (item.resource_type.value, item.resource_id),
    )
    payload = [
        {
            "plugin_id": resource.plugin_id,
            "resource_id": resource.resource_id,
            "resource_type": resource.resource_type.value,
            "scope": resource.scope.value,
            "owner_user_id": resource.owner_user_id,
            "owner_role": resource.owner_role,
            "created_by_plugin_version": resource.created_by_plugin_version,
            "retention_policy": resource.retention_policy.value,
            "cleanup_strategy": resource.cleanup_strategy.value,
            "metadata": dict(sorted(resource.metadata.items())),
        }
        for resource in resources
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _snapshot_id(
    *,
    plugin_id: str,
    created_at: datetime,
    resource_fingerprint: str,
) -> str:
    encoded = f"{plugin_id}:{created_at.isoformat()}:{resource_fingerprint}"
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _resource_to_dry_run(record: PluginResourceRecord) -> PluginDryRunResource:
    action = _action_for_cleanup(record.cleanup_strategy)
    requires_confirmation = action in {
        PluginDryRunAction.DELETE,
        PluginDryRunAction.MANUAL_REVIEW,
        PluginDryRunAction.FORBID_DELETE,
    }
    irreversible = action is PluginDryRunAction.DELETE
    return PluginDryRunResource(
        plugin_id=record.plugin_id,
        resource_id=record.resource_id,
        resource_type=record.resource_type.value,
        action=action,
        retention_policy=record.retention_policy.value,
        cleanup_strategy=record.cleanup_strategy.value,
        scope=record.scope.value,
        requires_confirmation=requires_confirmation,
        irreversible=irreversible,
        reason=_reason_for_action(action),
        metadata=dict(record.metadata),
    )


def _action_for_cleanup(strategy: PluginResourceCleanupStrategy) -> PluginDryRunAction:
    if strategy is PluginResourceCleanupStrategy.DELETE:
        return PluginDryRunAction.DELETE
    if strategy is PluginResourceCleanupStrategy.ARCHIVE:
        return PluginDryRunAction.ARCHIVE
    if strategy is PluginResourceCleanupStrategy.MANUAL_REVIEW:
        return PluginDryRunAction.MANUAL_REVIEW
    if strategy is PluginResourceCleanupStrategy.FORBID_DELETE:
        return PluginDryRunAction.FORBID_DELETE
    return PluginDryRunAction.KEEP


def _reason_for_action(action: PluginDryRunAction) -> str:
    if action is PluginDryRunAction.DELETE:
        return "Resource is marked delete_on_uninstall and would require explicit confirmation."
    if action is PluginDryRunAction.ARCHIVE:
        return "Resource metadata should be archived for audit/history."
    if action is PluginDryRunAction.MANUAL_REVIEW:
        return "Resource cannot be safely automated and needs operator review."
    if action is PluginDryRunAction.FORBID_DELETE:
        return "Resource is core-owned or protected and must not be deleted by plugin uninstall."
    return "Resource is retained by default."

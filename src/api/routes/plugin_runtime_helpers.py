"""Helper serializers for Plugin Runtime routes."""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from src.api.routes.plugin_runtime_models import (
    PluginRuntimeAcceptanceMatrixResponse,
    PluginRuntimeAcceptanceRequirementResponse,
    PluginRuntimeAuditRecordResponse,
    PluginRuntimeFeedbackGateResponse,
    PluginRuntimeFeedbackMigrationResponse,
    PluginRuntimeGuardSurfaceResponse,
    PluginRuntimePhaseProgressResponse,
)
from src.api.routes.registry import CORE_ROUTE_REGISTRATIONS
from src.infra.extensions import PluginRuntimeAuditRecord, build_package_integrity
from src.kernel.extensions import (
    acceptance_matrix_passed,
    assess_feedback_plugin_migration,
    build_pluginization_acceptance_matrix,
    missing_acceptance_requirements,
)

MAX_PACKAGE_ARCHIVE_BYTES = 50 * 1024 * 1024


def _acceptance_matrix_response() -> PluginRuntimeAcceptanceMatrixResponse:
    matrix = build_pluginization_acceptance_matrix(
        registered_core_route_ids={registration.id for registration in CORE_ROUTE_REGISTRATIONS},
    )
    sections = Counter(requirement.section for requirement in matrix)
    return PluginRuntimeAcceptanceMatrixResponse(
        passed=acceptance_matrix_passed(matrix),
        total=len(matrix),
        passed_count=sum(1 for requirement in matrix if requirement.passed),
        missing=list(missing_acceptance_requirements(matrix)),
        sections=dict(sections),
        requirements=[
            PluginRuntimeAcceptanceRequirementResponse(
                section=requirement.section,
                requirement_id=requirement.requirement_id,
                description=requirement.description,
                passed=requirement.passed,
                evidence_refs=list(requirement.evidence_refs),
            )
            for requirement in matrix
        ],
    )


def _acceptance_sections_passed(
    acceptance: PluginRuntimeAcceptanceMatrixResponse,
) -> set[str]:
    failed_sections = {
        requirement.section for requirement in acceptance.requirements if not requirement.passed
    }
    return set(acceptance.sections) - failed_sections


def _feedback_migration_response() -> PluginRuntimeFeedbackMigrationResponse:
    assessment = assess_feedback_plugin_migration()
    return PluginRuntimeFeedbackMigrationResponse(
        plugin_id=assessment.plugin_id,
        ready_for_first_migration_step=assessment.ready_for_first_migration_step,
        satisfied_gates=list(assessment.satisfied_gates),
        missing_gates=list(assessment.missing_gates),
        gate_evidence=[
            PluginRuntimeFeedbackGateResponse(
                gate_id=gate.gate_id,
                category=gate.category.value,
                passed=gate.passed,
                evidence=gate.evidence,
            )
            for gate in assessment.gate_evidence
        ],
        risks=list(assessment.risks),
        compatibility_notes=list(assessment.compatibility_notes),
    )


def _phase_progress_response(
    acceptance: PluginRuntimeAcceptanceMatrixResponse,
    feedback_migration: PluginRuntimeFeedbackMigrationResponse,
) -> list[PluginRuntimePhaseProgressResponse]:
    passed_sections = _acceptance_sections_passed(acceptance)
    phase_checks = [
        (
            "phase_1_runtime_foundation",
            "Phase 1: Plugin Runtime foundation",
            {"plugin_runtime", "extension_center_boundary", "disabled_semantics"},
            "Manifest validation, plugin state, guards, permissions, static registration, and controlled hook execution are covered.",
        ),
        (
            "phase_2_resource_dry_run",
            "Phase 2: Resource ledger and dry-run",
            {"resource_ledger_and_dry_run"},
            "Plugin-owned resources and uninstall dry-run validation are represented without physical deletion.",
        ),
        (
            "phase_2_core_plugin_matrix",
            "Phase 2: Core/plugin classification matrix",
            {"core_stability", "disabled_semantics"},
            "Core routes remain stable while plugin-owned routes, tools, hooks, and frontend entries can be hidden by runtime state.",
        ),
        (
            "phase_3_feedback_first_step",
            "Phase 3: Feedback first migration step",
            {"feedback_migration"},
            "Feedback migration gates are executable and ready for the first low-coupling plugin migration step.",
        ),
    ]
    progress: list[PluginRuntimePhaseProgressResponse] = []
    for phase, title, required_sections, evidence in phase_checks:
        passed = required_sections <= passed_sections
        if phase == "phase_3_feedback_first_step":
            passed = passed and feedback_migration.ready_for_first_migration_step
        progress.append(
            PluginRuntimePhaseProgressResponse(
                phase=phase,
                title=title,
                status="passed" if passed else "missing_evidence",
                passed=passed,
                evidence=evidence,
            )
        )
    return progress


def _runtime_capabilities() -> dict[str, Any]:
    acceptance = _acceptance_matrix_response()
    feedback_migration = _feedback_migration_response()
    guard_surfaces = [
        PluginRuntimeGuardSurfaceResponse(
            id="route_guard",
            label="Plugin route registration",
            status="enforced",
            enforced=True,
            failure_mode="fail_closed",
            evidence="Plugin routes are wrapped by runtime availability checks before handlers run.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="tool_guard",
            label="Internal MCP tools",
            status="enforced",
            enforced=True,
            failure_mode="fail_closed",
            evidence="Plugin-owned tools are filtered from metadata and rechecked before execution.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="scheduler_guard",
            label="Scheduler jobs",
            status="enforced",
            enforced=True,
            failure_mode="fail_closed",
            evidence="Plugin-owned scheduled jobs are skipped when runtime state is unavailable or disabled.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="listener_guard",
            label="Pub/Sub listeners",
            status="enforced",
            enforced=True,
            failure_mode="fail_closed",
            evidence="Plugin-owned listener dispatch checks runtime state before invoking handlers.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="channel_connector_guard",
            label="Channel connectors",
            status="enforced",
            enforced=True,
            failure_mode="fail_closed",
            evidence="Plugin-owned channel connector metadata, config reloads, and background sends check runtime state before using connector managers.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="lifecycle_hook_guard",
            label="Lifecycle hooks",
            status="enforced",
            enforced=True,
            failure_mode="isolated_error",
            evidence="Startup and shutdown hooks are executed through Plugin Runtime with timeout/error isolation and plugin-level issue records.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="uninstall_guard",
            label="Uninstall dry-run validation",
            status="controlled_execution",
            enforced=True,
            failure_mode="blocked_without_snapshot",
            evidence="Uninstall execution is limited to uninstallable plugins and requires a server-stored dry-run snapshot.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="hot_install_guard",
            label="Hot install and remote packages",
            status="blocked",
            enforced=True,
            failure_mode="not_supported",
            evidence="Runtime accepts local folder plugin packages and static compatibility manifests; remote unsigned hot loading remains blocked.",
        ),
        PluginRuntimeGuardSurfaceResponse(
            id="package_integrity_guard",
            label="User-installed package integrity",
            status="review_required",
            enforced=True,
            failure_mode="unsigned_enable_blocked",
            evidence="User-installed folder packages expose deterministic SHA-256 integrity metadata and unsigned packages cannot be enabled through Plugin Runtime.",
        ),
    ]
    return {
        "api_versions": ["v1"],
        "mode": "local_folder_packages_with_static_compat",
        "supports_hot_install": False,
        "supports_remote_packages": False,
        "supports_local_folder_packages": True,
        "supports_plugin_data_dir": True,
        "supports_package_integrity": True,
        "requires_signed_user_installed_enable": True,
        "supports_physical_uninstall": True,
        "supports_uninstall_dry_run_validation": True,
        "supports_remote_package_import": False,
        "supports_state_persistence": True,
        "supports_audit": True,
        "guard_surfaces": [surface.model_dump() for surface in guard_surfaces],
        "acceptance_matrix": acceptance.model_dump(),
        "phase_progress": [
            phase.model_dump() for phase in _phase_progress_response(acceptance, feedback_migration)
        ],
        "feedback_migration": feedback_migration.model_dump(),
    }


def _dry_run_response_dict(dry_run, validation) -> dict[str, Any]:
    actions = Counter(resource.action.value for resource in dry_run.resources)
    return {
        "plugin_id": dry_run.plugin_id,
        "created_at": dry_run.created_at,
        "expires_at": dry_run.expires_at,
        "snapshot_id": dry_run.snapshot_id,
        "resource_fingerprint": dry_run.resource_fingerprint,
        "resource_count": dry_run.resource_count,
        "actions": dict(actions),
        "warnings": dry_run.warnings,
        "requires_confirmation": dry_run.requires_confirmation,
        "rollback_notes": dry_run.rollback_notes,
        "package_data_policy": _dry_run_package_data_policy(dry_run),
        "validation": {
            "allowed": validation.allowed,
            "expired": validation.expired,
            "resource_changed": validation.resource_changed,
            "blockers": validation.blockers,
            "warnings": validation.warnings,
            "checked_at": validation.checked_at,
            "supports_physical_uninstall": True,
        },
    }


def _dry_run_resource_action(dry_run, resource_type: str) -> str | None:
    for resource in dry_run.resources:
        if resource.resource_type == resource_type:
            return resource.action.value
    return None


def _dry_run_package_data_policy(dry_run) -> dict[str, Any]:
    protected_types = {
        resource.resource_type
        for resource in dry_run.resources
        if resource.resource_type.startswith("plugin_data") and resource.action.value != "delete"
    }
    runtime_data_delete_allowed = any(
        resource.resource_type.startswith("plugin_data") and resource.action.value == "delete"
        for resource in dry_run.resources
    )
    return {
        "package_folder_action": _dry_run_resource_action(
            dry_run,
            "plugin_package_folder",
        ),
        "plugin_data_folder_action": _dry_run_resource_action(
            dry_run,
            "plugin_data_folder",
        ),
        "plugin_data_config_action": _dry_run_resource_action(
            dry_run,
            "plugin_data_config",
        ),
        "plugin_data_storage_action": _dry_run_resource_action(
            dry_run,
            "plugin_data_storage",
        ),
        "frontend_asset_action": _dry_run_resource_action(
            dry_run,
            "plugin_frontend_asset",
        ),
        "runtime_data_delete_allowed": runtime_data_delete_allowed,
        "sensitive_settings_delete_allowed": False,
        "requires_physical_data_delete_confirmation": runtime_data_delete_allowed,
        "default_retention": "keep_user_data",
        "protected_resource_types": sorted(protected_types),
        "notes": [
            "Plugin package folders may be archived by uninstall workflows.",
            "plugin-data is retained by default and is never physically deleted by dry-run.",
            "Sensitive plugin settings remain masked and require separate manual review.",
        ],
    }


def _manifest_export(manifest) -> dict[str, Any] | None:
    if manifest is None:
        return None
    data = manifest.model_dump(mode="json")
    data["uninstallable"] = manifest.uninstallable
    return data


def _package_summary(manifest) -> dict[str, Any]:
    if manifest is None or not manifest.package_source_path:
        return {
            "layout": {},
            "frontend_assets": None,
            "config_defaults": {},
            "data_template": {
                "exists": False,
                "file_count": 0,
                "total_bytes": 0,
                "files": [],
            },
            "standard_files": {},
            "file_count": 0,
            "total_bytes": 0,
            "integrity": None,
            "top_level_entries": [],
        }
    package_root = Path(manifest.package_source_path).resolve()
    standard_relative_paths = (
        "plugin.yaml",
        "config/schema.json",
        "config/defaults.json",
        "resources/resources.yaml",
        "README.md",
        "README",
    )
    standard_files = {
        relative_path: _safe_package_file_exists(package_root, relative_path)
        for relative_path in standard_relative_paths
    }
    file_count = 0
    total_bytes = 0
    if package_root.is_dir():
        for path in package_root.rglob("*"):
            if _skip_package_summary_path(path):
                continue
            if path.is_file():
                file_count += 1
                total_bytes += path.stat().st_size
    return {
        "layout": manifest.package_layout,
        "frontend_assets": (
            manifest.package_frontend_assets.model_dump(mode="json")
            if manifest.package_frontend_assets
            else None
        ),
        "manifest_authority": manifest.package_manifest_authority,
        "static_fallback_used": manifest.package_static_fallback_used,
        "static_fallback_fields": manifest.package_static_fallback_fields,
        "config_defaults": manifest.package_config_defaults,
        "data_template": _package_data_template_summary(
            package_root,
            data_template=manifest.package_data_template,
        ),
        "data_policy": _package_data_policy(manifest),
        "standard_files": standard_files,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "integrity": build_package_integrity(package_root).model_dump(),
        "top_level_entries": _package_top_level_entries(package_root),
    }


def _manifest_data_template_summary(manifest) -> dict[str, Any]:
    if manifest is None or not manifest.package_source_path:
        return {
            "exists": False,
            "file_count": 0,
            "total_bytes": 0,
            "files": [],
        }
    return _package_data_template_summary(
        Path(manifest.package_source_path).resolve(),
        data_template=manifest.package_data_template,
    )


def _package_data_policy(manifest) -> dict[str, Any]:
    return {
        "runtime_data_in_archive": False,
        "snapshot_metadata_in_export": True,
        "default_retention": "keep_user_data",
        "data_dir": manifest.package_data_dir,
        "sensitive_settings_included": False,
        "notes": [
            "plugin-data runtime files are not bundled in package archives.",
            "package-export includes plugin-data snapshot metadata only.",
            "sensitive plugin settings remain masked and are not written into plugin-data archives.",
        ],
    }


def _safe_package_file_exists(package_root, relative_path: str) -> bool:
    candidate = (package_root / relative_path).resolve()
    try:
        candidate.relative_to(package_root)
    except ValueError:
        return False
    return candidate.is_file()


def _skip_package_summary_path(path) -> bool:
    ignored_parts = {"__pycache__", "node_modules", ".git", ".pytest_cache"}
    return any(part in ignored_parts for part in path.parts)


def _package_data_template_summary(
    package_root, *, data_template: str = "plugin-data-template"
) -> dict[str, Any]:
    template_name = str(data_template or "plugin-data-template").replace("\\", "/").strip()
    if not template_name:
        template_name = "plugin-data-template"
    template_root = (package_root / template_name).resolve()
    try:
        template_root.relative_to(package_root.resolve())
    except ValueError:
        return {
            "exists": False,
            "template": template_name,
            "file_count": 0,
            "total_bytes": 0,
            "files": [],
        }
    if not template_root.is_dir() or template_root.is_symlink():
        return {
            "exists": False,
            "template": template_name,
            "file_count": 0,
            "total_bytes": 0,
            "files": [],
        }
    file_count = 0
    total_bytes = 0
    files: list[str] = []
    for path in sorted(template_root.rglob("*")):
        if path.is_symlink() or _skip_package_summary_path(path):
            continue
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(template_root)
        except ValueError:
            continue
        file_count += 1
        total_bytes += path.stat().st_size
        if len(files) < 20:
            files.append("/".join(relative.parts))
    return {
        "exists": True,
        "template": template_name,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "files": files,
    }


def _package_top_level_entries(package_root) -> list[str]:
    if not package_root.is_dir():
        return []
    entries: list[str] = []
    for path in sorted(package_root.iterdir()):
        if path.is_symlink():
            continue
        entries.append(f"{path.name}/" if path.is_dir() else path.name)
    return entries[:50]


def _package_archive_bytes(manifest) -> bytes:
    if manifest is None or not manifest.package_source_path:
        raise HTTPException(status_code=409, detail="plugin package folder is unavailable")
    package_root = Path(manifest.package_source_path).resolve()
    if not package_root.is_dir():
        raise HTTPException(status_code=409, detail="plugin package folder is unavailable")
    archive_root = manifest.id
    total_bytes = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_symlink() or _skip_package_summary_path(path):
                continue
            if not path.is_file():
                continue
            relative = path.resolve().relative_to(package_root)
            archive_name = "/".join((archive_root, *relative.parts))
            total_bytes += path.stat().st_size
            if total_bytes > MAX_PACKAGE_ARCHIVE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="plugin package archive exceeds maximum supported size",
                )
            archive.write(path, archive_name)
        archive.writestr(
            f"{archive_root}/package-summary.json",
            json.dumps(
                {
                    "schema_version": "lambchat.plugin.package-summary.v1",
                    "exported_at": datetime.now(UTC).isoformat(),
                    "plugin_id": manifest.id,
                    "source_type": manifest.package_source_type,
                    "manifest_authority": manifest.package_manifest_authority,
                    "static_fallback_used": manifest.package_static_fallback_used,
                    "static_fallback_fields": manifest.package_static_fallback_fields,
                    "data_policy": _package_data_policy(manifest),
                    "package_summary": _package_summary(manifest),
                    "notes": [
                        "This archive contains the local plugin package folder only.",
                        "plugin-data runtime data and sensitive plugin settings are not included.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
    return buffer.getvalue()


def _audit_response(record: PluginRuntimeAuditRecord) -> PluginRuntimeAuditRecordResponse:
    return PluginRuntimeAuditRecordResponse(
        plugin_id=record.plugin_id,
        action=record.action,
        previous_status=record.previous_status.value if record.previous_status else None,
        next_status=record.next_status.value,
        actor_user_id=record.actor_user_id,
        actor_username=record.actor_username,
        reason=record.reason,
        created_at=record.created_at,
    )

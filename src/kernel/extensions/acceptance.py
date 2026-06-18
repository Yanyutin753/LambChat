"""Executable acceptance evidence for the pluginization matrix."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.kernel.extensions.classification import core_route_ids_required_by_matrix
from src.kernel.extensions.dry_run import build_uninstall_dry_run, validate_uninstall_dry_run
from src.kernel.extensions.manifest import ExtensionType, PluginManifest
from src.kernel.extensions.marketplace import (
    ExtensionMarketplaceEntry,
    build_skill_marketplace_entry,
    extension_uses_plugin_runtime,
)
from src.kernel.extensions.resources import (
    PluginResourceCleanupStrategy,
    PluginResourceLedger,
    PluginResourceRecord,
    PluginResourceRetentionPolicy,
    PluginResourceType,
)
from src.kernel.extensions.runtime import PluginRuntime, PluginRuntimeStatus
from src.plugins.feedback.manifest import (
    FEEDBACK_PLUGIN_ID,
    assess_feedback_plugin_migration,
    build_feedback_plugin_manifest,
)


@dataclass(frozen=True)
class PluginizationAcceptanceRequirement:
    """One checked requirement from the execution package acceptance matrix."""

    section: str
    requirement_id: str
    description: str
    passed: bool
    evidence_refs: tuple[str, ...]


def build_pluginization_acceptance_matrix(
    *,
    registered_core_route_ids: set[str],
) -> tuple[PluginizationAcceptanceRequirement, ...]:
    """Build a machine-checkable view of the current pluginization acceptance state."""
    feedback_assessment = assess_feedback_plugin_migration()
    feedback_gate_ids = {gate.gate_id for gate in feedback_assessment.gate_evidence if gate.passed}
    required_core_routes = core_route_ids_required_by_matrix()
    runtime_checks = _runtime_acceptance_checks()
    extension_checks = _extension_center_acceptance_checks()
    disabled_checks = _disabled_semantics_checks()
    dry_run_checks = _dry_run_acceptance_checks()

    return (
        PluginizationAcceptanceRequirement(
            section="core_stability",
            requirement_id="core_capabilities_survive_plugin_disable",
            description="Core route matrix remains registered when business plugins are disabled.",
            passed=required_core_routes <= registered_core_route_ids
            and FEEDBACK_PLUGIN_ID not in required_core_routes,
            evidence_refs=(
                "tests/api/test_core_route_registry.py::test_core_stability_matrix_routes_exist_when_builtin_plugins_are_disabled",
                "tests/kernel/extensions/test_classification.py::test_core_classification_matrix_maps_to_core_route_registry",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="plugin_runtime",
            requirement_id="manifest_validation_and_unique_plugin_ids",
            description="PluginManifest validates shape and duplicate plugin ids enter plugin error state.",
            passed=runtime_checks["manifest_validation_and_unique_plugin_ids"],
            evidence_refs=(
                "tests/kernel/extensions/test_registry.py::test_plugin_manifest_declared_permissions_collects_nested_permission_strings",
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_duplicate_ids_enter_error_state",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="plugin_runtime",
            requirement_id="namespaced_runtime_contributions",
            description="Route, tool, permission, and frontend contribution declarations are namespace checked.",
            passed=runtime_checks["namespaced_runtime_contributions"],
            evidence_refs=(
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_validates_contribution_namespaces",
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_validation_errors_do_not_block_valid_plugins",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="plugin_runtime",
            requirement_id="states_guards_and_lifecycle_hooks",
            description="Runtime states, guards, lifecycle hook order, timeout, and error recording are covered.",
            passed=runtime_checks["states_guards_and_lifecycle_hooks"],
            evidence_refs=(
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_tracks_enabled_disabled_and_error_states",
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_lifecycle_execution_isolates_hook_failures",
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_lifecycle_execution_records_timeouts",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="extension_center_boundary",
            requirement_id="only_plugin_type_enters_plugin_runtime",
            description="Skills and MCP entries remain Extension Center items; only type=plugin uses Plugin Runtime lifecycle.",
            passed=extension_checks["only_plugin_type_enters_plugin_runtime"],
            evidence_refs=(
                "tests/kernel/extensions/test_registry.py::test_extension_center_plugin_runtime_boundary_only_allows_plugin_type",
                "tests/kernel/extensions/test_classification.py::test_extension_only_types_do_not_enter_business_plugin_runtime_by_default",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="extension_center_boundary",
            requirement_id="extension_center_does_not_manage_plugin_resources",
            description="Extension marketplace entries expose listing metadata without resource ledger or dry-run controls.",
            passed=extension_checks["extension_center_does_not_manage_plugin_resources"],
            evidence_refs=(
                "tests/kernel/extensions/test_registry.py::test_extension_marketplace_entry_accepts_unknown_future_types_without_manifest",
                "src/kernel/extensions/marketplace.py::ExtensionMarketplaceEntry",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="disabled_semantics",
            requirement_id="disabled_contributions_fail_closed_and_keep_data",
            description="Disabling plugins hides executable surfaces, guards tools/scheduler/listeners, and keeps resources.",
            passed=disabled_checks["disabled_contributions_fail_closed_and_keep_data"],
            evidence_refs=(
                "tests/api/test_core_route_registry.py::test_plugin_runtime_control_routes_disable_enable_feedback_guard",
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_filters_and_guards_scheduler_jobs_and_listeners",
                "frontend/src/extensions/__tests__/coreContributions.test.ts::runtime contribution filtering hides disabled or non-executable Feedback",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="disabled_semantics",
            requirement_id="repeated_disable_is_idempotent",
            description="Repeated disable does not delete resources or corrupt runtime state.",
            passed=disabled_checks["repeated_disable_is_idempotent"],
            evidence_refs=(
                "tests/kernel/extensions/test_runtime.py::test_plugin_runtime_repeated_disable_is_idempotent_and_keeps_resources",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="resource_ledger_and_dry_run",
            requirement_id="dry_run_classifies_all_actions",
            description="Dry-run lists plugin resources and classifies delete, keep, archive, manual review, and forbid delete.",
            passed=dry_run_checks["dry_run_classifies_all_actions"],
            evidence_refs=(
                "tests/kernel/extensions/test_dry_run.py::test_uninstall_dry_run_classifies_resource_cleanup_actions",
                "tests/kernel/extensions/test_resources.py::test_resource_ledger_registers_manifest_declarations_with_cleanup_policies",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="resource_ledger_and_dry_run",
            requirement_id="real_uninstall_requires_valid_dry_run",
            description="Missing, expired, changed, cross-plugin, forbidden, or manual-review dry-runs are rejected before execution.",
            passed=dry_run_checks["real_uninstall_requires_valid_dry_run"],
            evidence_refs=(
                "tests/kernel/extensions/test_dry_run.py::test_uninstall_dry_run_validation_blocks_missing_snapshot",
                "tests/kernel/extensions/test_dry_run.py::test_uninstall_dry_run_validation_blocks_expired_snapshot",
                "tests/kernel/extensions/test_dry_run.py::test_uninstall_dry_run_validation_blocks_resource_changes",
                "tests/kernel/extensions/test_dry_run.py::test_uninstall_dry_run_validation_blocks_forbidden_and_manual_resources",
            ),
        ),
        PluginizationAcceptanceRequirement(
            section="feedback_migration",
            requirement_id="feedback_first_migration_gates_pass",
            description="Feedback first migration gates pass with executable evidence and no missing gates.",
            passed=feedback_assessment.ready_for_first_migration_step
            and feedback_assessment.missing_gates == ()
            and {
                "core_routes_stable",
                "plugin_enabled_contributions_visible",
                "plugin_disabled_contributions_hidden",
                "plugin_permissions_declared",
                "plugin_failure_isolated",
                "plugin_resource_ledger_present",
                "plugin_uninstall_dry_run_present",
                "legacy_workflows_compatible",
            }
            <= feedback_gate_ids,
            evidence_refs=(
                "tests/kernel/extensions/test_feedback_plugin.py::test_feedback_static_plugin_boundary_adapts_legacy_implementation",
                "tests/kernel/extensions/test_feedback_plugin.py::test_feedback_migration_assessment_allows_first_step_with_compatibility_notes",
                "tests/api/test_core_route_registry.py::test_plugin_runtime_resource_and_dry_run_detail_routes",
                "frontend/src/extensions/__tests__/coreContributions.test.ts::Feedback message action follows plugin runtime state",
            ),
        ),
    )


def acceptance_matrix_passed(
    requirements: tuple[PluginizationAcceptanceRequirement, ...],
) -> bool:
    return all(requirement.passed for requirement in requirements)


def missing_acceptance_requirements(
    requirements: tuple[PluginizationAcceptanceRequirement, ...],
) -> tuple[str, ...]:
    return tuple(
        requirement.requirement_id for requirement in requirements if not requirement.passed
    )


def _runtime_acceptance_checks() -> dict[str, bool]:
    valid = PluginManifest(
        id="feedback",
        name="Feedback",
        version="1.0.0",
        api_version="v1",
        permissions=["feedback:read"],
        routers=[
            {
                "name": "feedback-api",
                "prefix": "/api/feedback",
                "module": "plugins.feedback.routes",
            }
        ],
        tools=[{"name": "feedback.summary", "module": "plugins.feedback.tools"}],
        frontend={"nav_items": ["feedback:nav"]},
        lifespan_hooks=[
            {
                "name": "feedback:start",
                "module": "plugins.feedback.hooks:start",
                "phase": "startup",
                "order": 20,
            },
            {
                "name": "feedback:stop",
                "module": "plugins.feedback.hooks:stop",
                "phase": "shutdown",
                "order": 10,
            },
        ],
    )
    duplicate_runtime = PluginRuntime([valid, valid.model_copy(update={"name": "Duplicate"})])
    invalid_runtime = PluginRuntime(
        [
            PluginManifest(
                id="bad",
                name="Bad",
                version="1.0.0",
                api_version="v1",
                permissions=["bad:read"],
                routers=[
                    {
                        "name": "shared-api",
                        "prefix": "/api/shared",
                        "module": "plugins.bad.routes",
                    }
                ],
                tools=[{"name": "summarize", "module": "plugins.bad.tools"}],
                frontend={"nav_items": ["shared-nav"]},
            )
        ]
    )
    valid_runtime = PluginRuntime([valid])

    return {
        "manifest_validation_and_unique_plugin_ids": duplicate_runtime.get_state(
            "feedback"
        ).status
        is PluginRuntimeStatus.ERROR,
        "namespaced_runtime_contributions": invalid_runtime.get_state("bad").status
        is PluginRuntimeStatus.ERROR,
        "states_guards_and_lifecycle_hooks": (
            valid_runtime.get_state("feedback").status is PluginRuntimeStatus.ENABLED
            and [hook.name for hook in valid_runtime.lifecycle_hooks(phase="startup")]
            == ["feedback:start"]
            and [hook.name for hook in valid_runtime.lifecycle_hooks(phase="shutdown")]
            == ["feedback:stop"]
        ),
    }


def _extension_center_acceptance_checks() -> dict[str, bool]:
    plugin_entry = ExtensionMarketplaceEntry(
        id="feedback",
        type=ExtensionType.PLUGIN.value,
        name="Feedback",
    )
    skill_entry = build_skill_marketplace_entry(skill_name="planner")
    mcp_entry = ExtensionMarketplaceEntry(
        id="mcp:github",
        type=ExtensionType.MCP.value,
        name="GitHub MCP",
    )

    marketplace_fields = set(ExtensionMarketplaceEntry.model_fields)
    resource_control_fields = {
        "resources",
        "resource_ledger",
        "dry_run_actions",
        "uninstall_dry_run",
    }

    return {
        "only_plugin_type_enters_plugin_runtime": (
            extension_uses_plugin_runtime(plugin_entry)
            and not extension_uses_plugin_runtime(skill_entry.as_manifest())
            and not extension_uses_plugin_runtime(mcp_entry.as_manifest())
        ),
        "extension_center_does_not_manage_plugin_resources": marketplace_fields.isdisjoint(
            resource_control_fields
        ),
    }


def _disabled_semantics_checks() -> dict[str, bool]:
    feedback_runtime = PluginRuntime([build_feedback_plugin_manifest()])
    feedback_runtime.disable_plugin(FEEDBACK_PLUGIN_ID)
    feedback_runtime.disable_plugin(FEEDBACK_PLUGIN_ID)

    guarded_runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                scheduler_jobs=["feedback.sync"],
                resources=[
                    {
                        "id": "feedback.listener",
                        "type": "listener",
                        "retention_policy": "manual_review_required",
                        "cleanup_strategy": "manual_review",
                    }
                ],
            )
        ]
    )
    guarded_runtime.disable_plugin("feedback")

    return {
        "disabled_contributions_fail_closed_and_keep_data": (
            feedback_runtime.routes() == []
            and feedback_runtime.tools() == []
            and feedback_runtime.lifecycle_hooks() == []
            and guarded_runtime.scheduler_jobs() == []
            and guarded_runtime.listeners() == []
            and feedback_runtime.resource_ledger.list(plugin_id=FEEDBACK_PLUGIN_ID) != []
        ),
        "repeated_disable_is_idempotent": feedback_runtime.get_state(
            FEEDBACK_PLUGIN_ID
        ).status
        is PluginRuntimeStatus.DISABLED,
    }


def _dry_run_acceptance_checks() -> dict[str, bool]:
    ledger = PluginResourceLedger(
        [
            _dry_run_record("delete-me", PluginResourceCleanupStrategy.DELETE),
            _dry_run_record("keep-me", PluginResourceCleanupStrategy.KEEP),
            _dry_run_record("archive-me", PluginResourceCleanupStrategy.ARCHIVE),
            _dry_run_record("review-me", PluginResourceCleanupStrategy.MANUAL_REVIEW),
            _dry_run_record("core-owned", PluginResourceCleanupStrategy.FORBID_DELETE),
            PluginResourceRecord(
                plugin_id="audio",
                resource_id="audio-api",
                resource_type=PluginResourceType.BACKEND_ROUTE,
                cleanup_strategy=PluginResourceCleanupStrategy.DELETE,
                retention_policy=PluginResourceRetentionPolicy.DELETE_ON_UNINSTALL,
            ),
        ]
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    dry_run = build_uninstall_dry_run(
        plugin_id="feedback",
        ledger=ledger,
        now=now,
        ttl_seconds=60,
    )
    missing_snapshot = validate_uninstall_dry_run(
        None,
        plugin_id="feedback",
        ledger=ledger,
    )
    expired = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
        now=now + timedelta(seconds=61),
    )
    ledger.register(_dry_run_record("new-resource", PluginResourceCleanupStrategy.KEEP))
    changed = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
        now=now,
    )

    return {
        "dry_run_classifies_all_actions": (
            [resource.resource_id for resource in dry_run.will_delete] == ["delete-me"]
            and [resource.resource_id for resource in dry_run.will_keep] == ["keep-me"]
            and [resource.resource_id for resource in dry_run.will_archive]
            == ["archive-me"]
            and [resource.resource_id for resource in dry_run.needs_manual_review]
            == ["review-me"]
            and [resource.resource_id for resource in dry_run.forbidden_to_delete]
            == ["core-owned"]
            and {resource.plugin_id for resource in dry_run.resources} == {"feedback"}
        ),
        "real_uninstall_requires_valid_dry_run": (
            "dry_run_required" in missing_snapshot.blockers
            and "dry_run_expired" in expired.blockers
            and "dry_run_resource_fingerprint_changed" in changed.blockers
        ),
    }


def _dry_run_record(
    resource_id: str,
    cleanup_strategy: PluginResourceCleanupStrategy,
) -> PluginResourceRecord:
    return PluginResourceRecord(
        plugin_id="feedback",
        resource_id=resource_id,
        resource_type=PluginResourceType.BACKEND_ROUTE,
        cleanup_strategy=cleanup_strategy,
        retention_policy={
            PluginResourceCleanupStrategy.DELETE: PluginResourceRetentionPolicy.DELETE_ON_UNINSTALL,
            PluginResourceCleanupStrategy.KEEP: PluginResourceRetentionPolicy.KEEP_USER_DATA,
            PluginResourceCleanupStrategy.ARCHIVE: PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            PluginResourceCleanupStrategy.MANUAL_REVIEW: PluginResourceRetentionPolicy.MANUAL_REVIEW_REQUIRED,
            PluginResourceCleanupStrategy.FORBID_DELETE: PluginResourceRetentionPolicy.CORE_OWNED_DO_NOT_DELETE,
        }[cleanup_strategy],
    )

"""Feedback static plugin manifest and migration gates."""

from __future__ import annotations

from dataclasses import dataclass

from src.kernel.extensions.classification import (
    PluginMigrationGateCategory,
    core_route_ids_required_by_matrix,
    required_migration_gate_ids,
)
from src.kernel.extensions.dry_run import (
    PluginDryRunAction,
    build_uninstall_dry_run,
    validate_uninstall_dry_run,
)
from src.kernel.extensions.manifest import PluginInstallType, PluginManifest
from src.kernel.extensions.resources import PluginResourceType
from src.kernel.extensions.runtime import PluginRuntime, PluginRuntimeStatus
from src.kernel.types import Permission

FEEDBACK_PLUGIN_ID = "feedback"


@dataclass(frozen=True)
class PluginMigrationGateEvidence:
    gate_id: str
    category: PluginMigrationGateCategory
    passed: bool
    evidence: str


@dataclass(frozen=True)
class PluginMigrationAssessment:
    """Result of checking whether a built-in capability can enter plugin migration."""

    plugin_id: str
    ready_for_first_migration_step: bool
    satisfied_gates: tuple[str, ...]
    missing_gates: tuple[str, ...]
    gate_evidence: tuple[PluginMigrationGateEvidence, ...]
    risks: tuple[str, ...]
    compatibility_notes: tuple[str, ...]


def build_feedback_plugin_manifest() -> PluginManifest:
    """Return the Phase 3 static manifest draft for the Feedback capability."""
    return PluginManifest(
        id=FEEDBACK_PLUGIN_ID,
        name="Feedback",
        version="1.0.0",
        api_version="v1",
        permissions=[
            Permission.FEEDBACK_WRITE.value,
            Permission.FEEDBACK_READ.value,
            Permission.FEEDBACK_ADMIN.value,
        ],
        routers=[
            {
                "name": "feedback-api",
                "prefix": "/api/feedback",
                "module": "src.plugins.feedback.routes",
                "required_permissions": [
                    Permission.FEEDBACK_WRITE.value,
                    Permission.FEEDBACK_READ.value,
                    Permission.FEEDBACK_ADMIN.value,
                ],
                "tags": ["Feedback"],
            }
        ],
        tools=[
            {
                "name": "feedback.summary",
                "module": "src.plugins.feedback.tools",
                "required_permissions": [Permission.FEEDBACK_READ.value],
            }
        ],
        lifespan_hooks=[
            {
                "name": "feedback:shutdown",
                "module": "src.plugins.feedback.lifecycle:close_feedback_manager",
                "phase": "shutdown",
                "order": 20,
            }
        ],
        frontend={
            "routes": ["feedback-route"],
            "panels": ["feedback-panel"],
            "nav_items": ["feedback-nav"],
            "message_actions": ["feedback:message-feedback"],
            "i18n_namespaces": ["feedback"],
            "required_permissions": [Permission.FEEDBACK_READ.value],
        },
        resources=[
            {
                "id": "feedback:message-feedback",
                "type": "message_action",
                "scope": "session",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "frontend_component": "frontend/src/plugins/feedback/FeedbackButtons.tsx",
                    "purpose": "Assistant message thumbs up/down feedback action.",
                },
            },
            {
                "id": "feedback",
                "type": "db_collection",
                "scope": "global",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "manager": "src.infra.feedback.manager.FeedbackManager",
                    "schema": "src.kernel.schemas.feedback.Feedback",
                },
            },
            {
                "id": "feedback.user_run_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "feedback",
                    "fields": "user_id,session_id,run_id",
                    "unique": "true",
                },
            },
            {
                "id": "feedback.session_run_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "feedback", "fields": "session_id,run_id"},
            },
            {
                "id": "feedback.rating_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "feedback", "fields": "rating"},
            },
            {
                "id": "feedback.created_at_sort",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "feedback", "fields": "created_at:-1"},
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.SYSTEM_BUILTIN,
    )


def assess_feedback_plugin_migration() -> PluginMigrationAssessment:
    """Assess Feedback against Phase 3 first-step migration gates."""
    manifest = build_feedback_plugin_manifest()
    runtime = PluginRuntime([manifest])
    state = runtime.get_state(FEEDBACK_PLUGIN_ID)
    dry_run = build_uninstall_dry_run(
        plugin_id=FEEDBACK_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    dry_run_validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id=FEEDBACK_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in runtime.resource_ledger.list(plugin_id=FEEDBACK_PLUGIN_ID)
    }
    executable_routes = {(route.plugin_id, route.prefix) for route in runtime.routes()}
    executable_tools = {(tool.plugin_id, tool.name) for tool in runtime.tools()}
    disabled_runtime = PluginRuntime([manifest])
    disabled_runtime.disable_plugin(FEEDBACK_PLUGIN_ID)
    disabled_contributions_hidden = (
        disabled_runtime.routes() == []
        and disabled_runtime.tools() == []
        and disabled_runtime.lifecycle_hooks() == []
    )

    gate_evidence = (
        PluginMigrationGateEvidence(
            gate_id="core_routes_stable",
            category=PluginMigrationGateCategory.CORE_STABILITY,
            passed=FEEDBACK_PLUGIN_ID not in core_route_ids_required_by_matrix(),
            evidence="Feedback is absent from the required core route matrix and is registered as a plugin route.",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_enabled_contributions_visible",
            category=PluginMigrationGateCategory.ENABLED_BEHAVIOR,
            passed=(
                state is not None
                and state.status is PluginRuntimeStatus.ENABLED
                and (FEEDBACK_PLUGIN_ID, "/api/feedback") in executable_routes
                and (FEEDBACK_PLUGIN_ID, "feedback.summary") in executable_tools
                and manifest.routers[0].module == "src.plugins.feedback.routes"
                and manifest.tools[0].module == "src.plugins.feedback.tools"
                and manifest.lifespan_hooks[0].module
                == "src.plugins.feedback.lifecycle:close_feedback_manager"
                and manifest.frontend.routes == ["feedback-route"]
                and manifest.frontend.panels == ["feedback-panel"]
                and manifest.frontend.nav_items == ["feedback-nav"]
                and manifest.frontend.message_actions == ["feedback:message-feedback"]
                and manifest.lifespan_hooks[0].name == "feedback:shutdown"
            ),
            evidence="Enabled Feedback exposes /api/feedback, feedback.summary, frontend route/panel/nav, and shutdown hook through src.plugins.feedback adapters.",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_disabled_contributions_hidden",
            category=PluginMigrationGateCategory.DISABLED_BEHAVIOR,
            passed=disabled_contributions_hidden,
            evidence="Disabling Feedback removes executable route, tool, and lifecycle hook registrations while preserving the manifest and resources.",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_permissions_declared",
            category=PluginMigrationGateCategory.PERMISSION_SECURITY,
            passed=manifest.declared_permissions()
            == [
                Permission.FEEDBACK_WRITE.value,
                Permission.FEEDBACK_READ.value,
                Permission.FEEDBACK_ADMIN.value,
            ],
            evidence="Feedback declares feedback:write, feedback:read, and feedback:admin before exposing runtime capabilities.",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_failure_isolated",
            category=PluginMigrationGateCategory.FAILURE_ISOLATION,
            passed=state is not None and state.issues == [],
            evidence="Feedback manifest validates without runtime issues; lifecycle hook failures would be isolated by PluginRuntime.execute_lifecycle_hooks().",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_resource_ledger_present",
            category=PluginMigrationGateCategory.DRY_RUN,
            passed={
                (PluginResourceType.BACKEND_ROUTE, "feedback-api"),
                (PluginResourceType.FRONTEND_ROUTE, "feedback-route"),
                (PluginResourceType.PANEL, "feedback-panel"),
                (PluginResourceType.NAV_ITEM, "feedback-nav"),
                (PluginResourceType.MESSAGE_ACTION, "feedback:message-feedback"),
                (PluginResourceType.TOOL, "feedback.summary"),
                (PluginResourceType.DB_COLLECTION, "feedback"),
                (PluginResourceType.DB_INDEX, "feedback.user_run_unique"),
            }
            <= resource_keys,
            evidence="Feedback resource ledger records backend, frontend, message action, tool, collection, and index ownership.",
        ),
        PluginMigrationGateEvidence(
            gate_id="plugin_uninstall_dry_run_present",
            category=PluginMigrationGateCategory.DRY_RUN,
            passed=(
                dry_run.resource_count > 0
                and dry_run_validation.allowed
                and dry_run.will_delete == []
                and dry_run.by_action(PluginDryRunAction.KEEP) != []
                and dry_run.by_action(PluginDryRunAction.ARCHIVE) != []
            ),
            evidence="Feedback dry-run keeps user data, archives metadata, has no delete actions, and validates without blockers.",
        ),
        PluginMigrationGateEvidence(
            gate_id="legacy_workflows_compatible",
            category=PluginMigrationGateCategory.REGRESSION_COMPATIBILITY,
            passed=(
                manifest.routers[0].prefix == "/api/feedback"
                and manifest.frontend.routes == ["feedback-route"]
                and Permission.FEEDBACK_READ.value in manifest.declared_permissions()
            ),
            evidence="Legacy /api/feedback, /feedback route contribution, and feedback:* permission strings remain stable.",
        ),
    )
    satisfied = {gate.gate_id for gate in gate_evidence if gate.passed}
    missing = required_migration_gate_ids() - satisfied
    return PluginMigrationAssessment(
        plugin_id=FEEDBACK_PLUGIN_ID,
        ready_for_first_migration_step=not missing,
        satisfied_gates=tuple(sorted(satisfied)),
        missing_gates=tuple(sorted(missing)),
        gate_evidence=gate_evidence,
        risks=(
            "Feedback Mongo documents are user data and must be retained during any uninstall dry-run.",
        ),
        compatibility_notes=(
            "Keep /api/feedback, /feedback, and feedback:* permission strings stable during migration.",
            "Feedback route registration, frontend contributions, tool declaration, resource ledger, dry-run, and shutdown cleanup are now owned by the src.plugins.feedback static plugin boundary.",
        ),
    )

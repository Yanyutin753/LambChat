"""Executable core/plugin classification matrix for pluginization work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExtensionClassification(str, Enum):
    CORE = "core"
    EXTENSION_ONLY = "extension_only"
    LOW_COUPLING_PLUGIN = "low_coupling_plugin"
    MEDIUM_COUPLING_PLUGIN = "medium_coupling_plugin"


class PluginMigrationGateCategory(str, Enum):
    CORE_STABILITY = "core_stability"
    ENABLED_BEHAVIOR = "enabled_behavior"
    DISABLED_BEHAVIOR = "disabled_behavior"
    PERMISSION_SECURITY = "permission_security"
    FAILURE_ISOLATION = "failure_isolation"
    DRY_RUN = "dry_run"
    UNINSTALL_EXECUTION = "uninstall_execution"
    REGRESSION_COMPATIBILITY = "regression_compatibility"


@dataclass(frozen=True)
class CapabilityClassification:
    id: str
    classification: ExtensionClassification
    reason: str
    required_core_route_ids: tuple[str, ...] = ()
    migration_prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginMigrationGate:
    id: str
    category: PluginMigrationGateCategory
    description: str
    required_before_business_migration: bool = True
    executable_check: str | None = None


CORE_CAPABILITIES: tuple[CapabilityClassification, ...] = (
    CapabilityClassification("chat", ExtensionClassification.CORE, "conversation protocol", ("chat",)),
    CapabilityClassification("sessions", ExtensionClassification.CORE, "session storage", ("sessions",)),
    CapabilityClassification("projects", ExtensionClassification.CORE, "project ownership", ("projects",)),
    CapabilityClassification(
        "scheduled_tasks",
        ExtensionClassification.CORE,
        "task scheduling base capability",
        ("scheduled_tasks",),
    ),
    CapabilityClassification("mcp_core", ExtensionClassification.CORE, "MCP runtime", ("mcp", "mcp_admin")),
    CapabilityClassification("skill_core", ExtensionClassification.CORE, "Skill base capability", ("skills",)),
    CapabilityClassification("memory", ExtensionClassification.CORE, "memory base capability", ("memory",)),
    CapabilityClassification("auth", ExtensionClassification.CORE, "authentication", ("auth",)),
    CapabilityClassification("users", ExtensionClassification.CORE, "user management", ("users",)),
    CapabilityClassification("rbac", ExtensionClassification.CORE, "RBAC role management", ("roles",)),
    CapabilityClassification("settings", ExtensionClassification.CORE, "core settings", ("settings",)),
    CapabilityClassification("upload", ExtensionClassification.CORE, "upload/file access base", ("upload",)),
    CapabilityClassification("files", ExtensionClassification.CORE, "revealed files base", ("files",)),
    CapabilityClassification("usage", ExtensionClassification.CORE, "usage collection base"),
    CapabilityClassification("share", ExtensionClassification.CORE, "share permission base", ("share",)),
    CapabilityClassification("human_approval", ExtensionClassification.CORE, "approval protocol", ("human",)),
    CapabilityClassification("env_vars", ExtensionClassification.CORE, "secret/env key storage", ("env_vars",)),
    CapabilityClassification("notifications", ExtensionClassification.CORE, "notification base", ("notifications",)),
    CapabilityClassification("push", ExtensionClassification.CORE, "push delivery base", ("push",)),
    CapabilityClassification("extension_center", ExtensionClassification.CORE, "extension center", ("marketplace",)),
)

EXTENSION_ONLY_CAPABILITIES: tuple[CapabilityClassification, ...] = (
    CapabilityClassification("skill", ExtensionClassification.EXTENSION_ONLY, "managed by Skill core service"),
    CapabilityClassification("mcp_profile", ExtensionClassification.EXTENSION_ONLY, "managed by MCP core service"),
    CapabilityClassification("theme", ExtensionClassification.EXTENSION_ONLY, "display/config extension"),
)

LOW_COUPLING_PLUGIN_CANDIDATES: tuple[CapabilityClassification, ...] = (
    CapabilityClassification(
        "feedback",
        ExtensionClassification.LOW_COUPLING_PLUGIN,
        "low coupling feedback center",
        migration_prerequisites=(
            "plugin_manifest",
            "route_guard",
            "frontend_contribution",
            "permission_declaration",
            "resource_ledger",
            "uninstall_dry_run",
            "core_stability_tests",
        ),
    ),
    CapabilityClassification("github_installer", ExtensionClassification.LOW_COUPLING_PLUGIN, "external GitHub installer"),
    CapabilityClassification("image_generation", ExtensionClassification.LOW_COUPLING_PLUGIN, "optional media provider"),
    CapabilityClassification("audio_transcription", ExtensionClassification.LOW_COUPLING_PLUGIN, "optional media provider"),
    CapabilityClassification("advanced_file_viewers", ExtensionClassification.LOW_COUPLING_PLUGIN, "optional viewers"),
    CapabilityClassification("usage_reports", ExtensionClassification.LOW_COUPLING_PLUGIN, "usage reporting enhancement"),
    CapabilityClassification(
        "share_publishers",
        ExtensionClassification.LOW_COUPLING_PLUGIN,
        "external share targets only; core share route and shared session storage remain core",
        migration_prerequisites=(
            "external_share_target_contract",
            "share_target_resource_declaration",
            "core_share_route_protection",
            "frontend_share_target_contribution",
        ),
    ),
)

MEDIUM_COUPLING_PLUGIN_CANDIDATES: tuple[CapabilityClassification, ...] = (
    CapabilityClassification("channels", ExtensionClassification.MEDIUM_COUPLING_PLUGIN, "listener/delivery coupling", ("channels",)),
    CapabilityClassification("agent_team", ExtensionClassification.MEDIUM_COUPLING_PLUGIN, "chat context and team model coupling", ("teams",)),
    CapabilityClassification("persona", ExtensionClassification.MEDIUM_COUPLING_PLUGIN, "prompt/context coupling", ("persona_presets",)),
    CapabilityClassification("user_agent", ExtensionClassification.MEDIUM_COUPLING_PLUGIN, "future independent agent model"),
)

PLUGIN_MIGRATION_GATES: tuple[PluginMigrationGate, ...] = (
    PluginMigrationGate(
        "core_routes_stable",
        PluginMigrationGateCategory.CORE_STABILITY,
        "Core route registry still exposes required core capabilities when business plugins are disabled.",
        executable_check="tests/api/test_core_route_registry.py",
    ),
    PluginMigrationGate(
        "plugin_enabled_contributions_visible",
        PluginMigrationGateCategory.ENABLED_BEHAVIOR,
        "Enabled plugins expose declared route/tool/frontend contributions.",
        executable_check="tests/kernel/extensions/test_runtime.py",
    ),
    PluginMigrationGate(
        "plugin_disabled_contributions_hidden",
        PluginMigrationGateCategory.DISABLED_BEHAVIOR,
        "Disabled plugins do not expose executable route/tool/frontend contributions.",
        executable_check="tests/kernel/extensions/test_runtime.py",
    ),
    PluginMigrationGate(
        "plugin_permissions_declared",
        PluginMigrationGateCategory.PERMISSION_SECURITY,
        "Plugin permissions are declared and namespaced before execution.",
        executable_check="tests/kernel/extensions/test_runtime.py",
    ),
    PluginMigrationGate(
        "plugin_failure_isolated",
        PluginMigrationGateCategory.FAILURE_ISOLATION,
        "Invalid manifests and hook failures enter plugin error state without blocking core startup.",
        executable_check="tests/kernel/extensions/test_runtime.py",
    ),
    PluginMigrationGate(
        "plugin_resource_ledger_present",
        PluginMigrationGateCategory.DRY_RUN,
        "Plugin-owned resources are recorded in a resource ledger.",
        executable_check="tests/kernel/extensions/test_resources.py",
    ),
    PluginMigrationGate(
        "plugin_uninstall_dry_run_present",
        PluginMigrationGateCategory.DRY_RUN,
        "Uninstall dry-run can classify delete/keep/archive/manual/forbidden resources.",
        executable_check="tests/kernel/extensions/test_dry_run.py",
    ),
    PluginMigrationGate(
        "real_uninstall_requires_dry_run_and_install_type",
        PluginMigrationGateCategory.UNINSTALL_EXECUTION,
        "Real uninstall execution requires a valid dry-run snapshot and is blocked for protected system preset plugins.",
        required_before_business_migration=False,
    ),
    PluginMigrationGate(
        "legacy_workflows_compatible",
        PluginMigrationGateCategory.REGRESSION_COMPATIBILITY,
        "Legacy API, URL, permission strings, and data reads remain compatible during migration.",
        executable_check="tests/api/test_core_route_registry.py",
    ),
)


def core_route_ids_required_by_matrix() -> set[str]:
    return {
        route_id
        for capability in CORE_CAPABILITIES
        for route_id in capability.required_core_route_ids
    }


def plugin_candidate_ids() -> set[str]:
    return {
        capability.id
        for capability in LOW_COUPLING_PLUGIN_CANDIDATES + MEDIUM_COUPLING_PLUGIN_CANDIDATES
    }


def required_migration_gate_ids() -> set[str]:
    return {
        gate.id for gate in PLUGIN_MIGRATION_GATES if gate.required_before_business_migration
    }

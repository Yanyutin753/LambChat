from src.api.routes.registry import CORE_ROUTE_REGISTRATIONS
from src.kernel.extensions import (
    CORE_CAPABILITIES,
    EXTENSION_ONLY_CAPABILITIES,
    LOW_COUPLING_PLUGIN_CANDIDATES,
    MEDIUM_COUPLING_PLUGIN_CANDIDATES,
    PLUGIN_MIGRATION_GATES,
    ExtensionClassification,
    PluginMigrationGateCategory,
    core_route_ids_required_by_matrix,
    plugin_candidate_ids,
    required_migration_gate_ids,
)


def test_core_classification_matrix_maps_to_core_route_registry() -> None:
    registered_route_ids = {registration.id for registration in CORE_ROUTE_REGISTRATIONS}

    assert core_route_ids_required_by_matrix() <= registered_route_ids
    assert "chat" in core_route_ids_required_by_matrix()
    assert "marketplace" in core_route_ids_required_by_matrix()
    assert "feedback" not in core_route_ids_required_by_matrix()


def test_core_capabilities_are_not_plugin_candidates() -> None:
    core_ids = {capability.id for capability in CORE_CAPABILITIES}

    assert core_ids.isdisjoint(plugin_candidate_ids())
    assert "feedback" in plugin_candidate_ids()
    assert "agent_team" in plugin_candidate_ids()


def test_extension_only_types_do_not_enter_business_plugin_runtime_by_default() -> None:
    assert {capability.id for capability in EXTENSION_ONLY_CAPABILITIES} >= {
        "skill",
        "mcp_profile",
    }
    assert all(
        capability.classification is ExtensionClassification.EXTENSION_ONLY
        for capability in EXTENSION_ONLY_CAPABILITIES
    )


def test_feedback_candidate_declares_migration_prerequisites() -> None:
    feedback = next(
        capability for capability in LOW_COUPLING_PLUGIN_CANDIDATES if capability.id == "feedback"
    )

    assert feedback.classification is ExtensionClassification.LOW_COUPLING_PLUGIN
    assert set(feedback.migration_prerequisites) >= {
        "plugin_manifest",
        "route_guard",
        "frontend_contribution",
        "permission_declaration",
        "resource_ledger",
        "uninstall_dry_run",
        "core_stability_tests",
    }


def test_share_publishers_candidate_does_not_migrate_core_share_boundary() -> None:
    share_core = next(capability for capability in CORE_CAPABILITIES if capability.id == "share")
    share_publishers = next(
        capability
        for capability in LOW_COUPLING_PLUGIN_CANDIDATES
        if capability.id == "share_publishers"
    )

    assert share_core.classification is ExtensionClassification.CORE
    assert share_core.required_core_route_ids == ("share",)
    assert share_publishers.classification is ExtensionClassification.LOW_COUPLING_PLUGIN
    assert share_publishers.required_core_route_ids == ()
    assert set(share_publishers.migration_prerequisites) == {
        "external_share_target_contract",
        "share_target_resource_declaration",
        "core_share_route_protection",
        "frontend_share_target_contribution",
    }


def test_medium_coupling_candidates_keep_legacy_core_routes_until_ready() -> None:
    candidate_routes = {
        capability.id: capability.required_core_route_ids
        for capability in MEDIUM_COUPLING_PLUGIN_CANDIDATES
    }

    assert candidate_routes["channels"] == ("channels",)
    assert candidate_routes["agent_team"] == ("teams",)
    assert candidate_routes["persona"] == ("persona_presets",)


def test_plugin_migration_gate_matrix_covers_required_categories() -> None:
    categories = {gate.category for gate in PLUGIN_MIGRATION_GATES}

    assert categories >= {
        PluginMigrationGateCategory.CORE_STABILITY,
        PluginMigrationGateCategory.ENABLED_BEHAVIOR,
        PluginMigrationGateCategory.DISABLED_BEHAVIOR,
        PluginMigrationGateCategory.PERMISSION_SECURITY,
        PluginMigrationGateCategory.FAILURE_ISOLATION,
        PluginMigrationGateCategory.DRY_RUN,
        PluginMigrationGateCategory.UNINSTALL_EXECUTION,
        PluginMigrationGateCategory.REGRESSION_COMPATIBILITY,
    }
    assert "real_uninstall_requires_dry_run_and_install_type" not in required_migration_gate_ids()


def test_required_plugin_migration_gates_have_executable_checks() -> None:
    missing_checks = [
        gate.id
        for gate in PLUGIN_MIGRATION_GATES
        if gate.required_before_business_migration and not gate.executable_check
    ]

    assert missing_checks == []
    assert required_migration_gate_ids() >= {
        "core_routes_stable",
        "plugin_enabled_contributions_visible",
        "plugin_disabled_contributions_hidden",
        "plugin_permissions_declared",
        "plugin_failure_isolated",
        "plugin_resource_ledger_present",
        "plugin_uninstall_dry_run_present",
        "legacy_workflows_compatible",
    }

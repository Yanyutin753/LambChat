from src.api.routes.registry import CORE_ROUTE_REGISTRATIONS
from src.kernel.extensions import (
    acceptance_matrix_passed,
    build_pluginization_acceptance_matrix,
    missing_acceptance_requirements,
)


def _registered_core_route_ids() -> set[str]:
    return {registration.id for registration in CORE_ROUTE_REGISTRATIONS}


def test_pluginization_acceptance_matrix_maps_execution_package_sections() -> None:
    matrix = build_pluginization_acceptance_matrix(
        registered_core_route_ids=_registered_core_route_ids(),
    )

    assert {requirement.section for requirement in matrix} == {
        "core_stability",
        "plugin_runtime",
        "extension_center_boundary",
        "disabled_semantics",
        "resource_ledger_and_dry_run",
        "feedback_migration",
    }
    assert {requirement.requirement_id for requirement in matrix} >= {
        "core_capabilities_survive_plugin_disable",
        "manifest_validation_and_unique_plugin_ids",
        "namespaced_runtime_contributions",
        "states_guards_and_lifecycle_hooks",
        "only_plugin_type_enters_plugin_runtime",
        "extension_center_does_not_manage_plugin_resources",
        "disabled_contributions_fail_closed_and_keep_data",
        "repeated_disable_is_idempotent",
        "dry_run_classifies_all_actions",
        "real_uninstall_requires_valid_dry_run",
        "feedback_first_migration_gates_pass",
    }


def test_pluginization_acceptance_matrix_passes_with_current_evidence() -> None:
    matrix = build_pluginization_acceptance_matrix(
        registered_core_route_ids=_registered_core_route_ids(),
    )

    assert acceptance_matrix_passed(matrix) is True
    assert missing_acceptance_requirements(matrix) == ()
    assert all(requirement.evidence_refs for requirement in matrix)
    assert all("::" in ref or ref.startswith("src/") for requirement in matrix for ref in requirement.evidence_refs)


def test_pluginization_acceptance_matrix_reports_missing_core_route_evidence() -> None:
    matrix = build_pluginization_acceptance_matrix(registered_core_route_ids=set())

    missing = missing_acceptance_requirements(matrix)

    assert "core_capabilities_survive_plugin_disable" in missing
    assert acceptance_matrix_passed(matrix) is False


def test_feedback_acceptance_requirement_consumes_gate_evidence() -> None:
    matrix = build_pluginization_acceptance_matrix(
        registered_core_route_ids=_registered_core_route_ids(),
    )
    feedback = next(
        requirement
        for requirement in matrix
        if requirement.requirement_id == "feedback_first_migration_gates_pass"
    )

    assert feedback.passed is True
    assert any("test_feedback_plugin.py" in ref for ref in feedback.evidence_refs)
    assert any("coreContributions.test.ts" in ref for ref in feedback.evidence_refs)

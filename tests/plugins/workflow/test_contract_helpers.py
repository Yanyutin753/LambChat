from src.plugins.workflow.contracts import (
    output_contract_status,
    workflow_callable_interface,
    workflow_result_interface,
)


def test_workflow_result_interface_declares_entry_exit_and_debug_contracts() -> None:
    assert workflow_result_interface(
        workflow_id="wf-1",
        version_id="wfv-1",
        run_id="wfr-1",
    ) == {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "schema_tool": "workflow_get_schema",
            "schema_field": "input_schema",
        },
        "exit": {
            "type": "workflow.output",
            "field": "output",
            "schema_tool": "workflow_get_schema",
            "schema_field": "output_schema",
        },
        "debug": {
            "tool": "workflow_get_run",
            "workflow_id": "wf-1",
            "run_id": "wfr-1",
            "events_field": "events",
        },
    }


def test_workflow_callable_interface_declares_schema_run_and_debug_entrypoints() -> None:
    assert workflow_callable_interface(
        workflow_id="wf-1",
        version_id="wfv-1",
    ) == {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "schema_tool": "workflow_get_schema",
            "schema_field": "input_schema",
        },
        "exit": {
            "type": "workflow.output",
            "field": "output",
            "schema_tool": "workflow_get_schema",
            "schema_field": "output_schema",
        },
        "schema": {
            "tool": "workflow_get_schema",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "input_schema_field": "input_schema",
            "output_schema_field": "output_schema",
        },
        "run": {
            "tool": "workflow_run",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "input_argument": "input",
            "output_field": "output",
        },
        "debug": {
            "tool": "workflow_get_run",
            "workflow_id": "wf-1",
            "run_id_field": "run_id",
        },
    }


def test_output_contract_required_paths_do_not_promote_optional_nested_fields() -> None:
    contract = output_contract_status(
        {"profile": {"name": "Ada"}},
        {
            "output_schema": {
                "type": "object",
                "required": ["profile"],
                "properties": {
                    "profile": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                    },
                    "answer": {"type": "string"},
                },
            }
        },
    )

    assert contract is not None
    assert contract["required_fields"] == ["profile"]
    assert contract["required_field_paths"] == ["profile"]
    assert contract["declared_field_paths"] == ["profile.age", "profile.name", "answer"]
    assert contract["valid"] is True


def test_output_contract_required_paths_follow_nested_required_leaves() -> None:
    contract = output_contract_status(
        {"items": [{"score": 1}], "report": {"summary": "Ready"}},
        {
            "output_schema": {
                "type": "object",
                "required": ["items", "report"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["score"],
                            "properties": {
                                "score": {"type": "number"},
                                "label": {"type": "string"},
                            },
                        },
                    },
                    "report": {
                        "type": "object",
                        "required": ["summary"],
                        "properties": {
                            "summary": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                    },
                },
            }
        },
    )

    assert contract is not None
    assert contract["required_fields"] == ["items", "report"]
    assert contract["required_field_paths"] == ["items[].score", "report.summary"]
    assert contract["valid"] is True

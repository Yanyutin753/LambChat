from __future__ import annotations

import asyncio

import pytest

from src.plugins.workflow.executor import (
    MinimalWorkflowExecutor,
    WorkflowExecutionError,
    WorkflowExecutionPaused,
)
from src.plugins.workflow.policy import build_http_request_policy


def test_minimal_executor_runs_linear_answer_workflow() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Hello {{name}}"},
                },
                {"id": "end", "type": "end", "supported": True, "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "answer", "valid": True},
                {"id": "e2", "source": "answer", "target": "end", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "LambChat"})

    assert result.output == {"answer": "Hello LambChat"}
    assert [event["event_type"] for event in result.events] == [
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
    ]
    finished_events = [event for event in result.events if event["event_type"] == "node_finished"]
    assert all(isinstance(event["payload"].get("duration_ms"), int) for event in finished_events)


def test_minimal_executor_answer_accepts_text_parts() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {
                        "content": [
                            {"type": "text", "text": "Hello {{name}}"},
                            " from ",
                            {"type": "markdown", "data": "{{team}}"},
                            {"type": "image", "url": "https://example.invalid/ignored.png"},
                        ]
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "Ada", "team": "Core"})

    assert result.output == {"answer": "Hello Ada from Core"}


@pytest.mark.parametrize("operation", ["filter", "find", "any", "all", "none", "count_matching"])
def test_minimal_executor_rejects_list_condition_operation_without_conditions(operation: str) -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "filter",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": operation,
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "filter", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert validation.runnable is False
    assert (
        "workflow_list_operator_node_not_allowed:filter:workflow_list_operator_filter_conditions_missing"
        in validation.errors
    )


def test_static_validator_reports_entry_and_exit_boundary_edges() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "Done"}},
                {"id": "end", "type": "end", "supported": True, "data": {}},
            ],
            "edges": [
                {"id": "to-start", "source": "answer", "target": "start", "valid": False},
                {"id": "from-exit", "source": "end", "target": "answer", "valid": False},
                {"id": "start-end", "source": "start", "target": "end", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert validation.runnable is False
    assert "workflow_boundary_edge_targets_entry:to-start:answer->start" in validation.errors
    assert "workflow_boundary_edge_starts_from_exit:from-exit:end->answer" in validation.errors


def test_minimal_executor_end_node_accepts_output_mapping_and_selectors() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "assign",
                    "type": "variable_assign",
                    "supported": True,
                    "data": {
                        "assignments": {
                            "summary": "Hello {{name}}",
                            "items": [{"title": "Alpha"}, {"title": "Beta"}],
                            "implicit": "kept",
                        }
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                    "supported": True,
                    "data": {
                        "outputs": {
                            "summary": {"value": "{{summary}}"},
                            "first_title": {"value_selector": ["items", 0, "title"]},
                            "implicit": {},
                            "literal": "done",
                        }
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "valid": True},
                {"id": "e2", "source": "assign", "target": "end", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "LambChat"})

    assert result.output == {
        "summary": "Hello LambChat",
        "first_title": "Alpha",
        "implicit": "kept",
        "literal": "done",
    }


def test_minimal_executor_end_node_accepts_text_part_values() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "end",
                    "type": "end",
                    "supported": True,
                    "data": {
                        "outputs": {
                            "summary": {
                                "value": [
                                    {"type": "text", "text": "Hello {{name}}"},
                                    " from ",
                                    {"type": "markdown", "data": "{{team}}"},
                                    {"type": "image", "url": "https://example.invalid/ignored.png"},
                                ]
                            },
                            "items": {"value": ["alpha", "beta"]},
                            "payload": {"value": {"title": "{{name}}", "count": 2}},
                        }
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "Ada", "team": "Core"})

    assert result.output == {
        "summary": "Hello Ada from Core",
        "items": ["alpha", "beta"],
        "payload": {"title": "Ada", "count": 2},
    }


def test_minimal_executor_applies_start_variable_defaults_without_overriding_input() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {"name": "name", "type": "string", "default": "Visitor"},
                            {"name": "tone", "type": "string", "default_value": "warm"},
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Hello {{name}} in a {{tone}} tone"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    defaulted = MinimalWorkflowExecutor().execute(model, workflow_input={})
    overridden = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "LambChat"})

    assert defaulted.output == {"answer": "Hello Visitor in a warm tone"}
    assert overridden.output == {"answer": "Hello LambChat in a warm tone"}


def test_minimal_executor_rejects_missing_required_start_variable() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {"variables": [{"name": "name", "type": "string", "required": True}]},
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Hello {{name}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_start_required_input_missing:name") as exc_info:
        MinimalWorkflowExecutor().execute(model, workflow_input={})

    assert exc_info.value.events[-1]["event_type"] == "node_failed"
    assert exc_info.value.events[-1]["node_id"] == "start"


def test_minimal_executor_accepts_required_start_variable_from_default() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {"name": "name", "type": "string", "required": True, "default": "Visitor"}
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Hello {{name}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={})

    assert result.output == {"answer": "Hello Visitor"}


def test_minimal_executor_accepts_start_variable_name_aliases() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {
                                "field_name": "topic",
                                "type": "string",
                                "required": True,
                                "default": "workflow",
                            },
                            {
                                "parameterName": "count",
                                "type": "integer",
                                "required": True,
                                "default": 2,
                                "minimum": 1,
                            },
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{topic}} x {{count}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={})

    assert result.output == {"answer": "workflow x 2"}


def test_minimal_executor_accepts_start_variable_mapping() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": {
                            "topic": {
                                "type": "string",
                                "required": True,
                                "default": "workflow",
                                "minLength": 3,
                            },
                            "count": {
                                "type": "integer",
                                "required": True,
                                "default": 2,
                                "minimum": 1,
                            },
                            "tone": "string",
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{topic}} x {{count}} / {{tone}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"tone": "warm"})

    assert result.output == {"answer": "workflow x 2 / warm"}


@pytest.mark.asyncio
async def test_minimal_executor_async_applies_start_schema_defaults() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "default": "hello from default"}
                            },
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Question: {{#sys.query#}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(model, workflow_input={})

    assert result.output == {"answer": "Question: hello from default"}


@pytest.mark.asyncio
async def test_minimal_executor_async_rejects_missing_required_schema_input() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "required": ["message"],
                            "properties": {"message": {"type": "string"}},
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Question: {{#sys.query#}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_start_required_input_missing:message") as exc_info:
        await MinimalWorkflowExecutor().execute_async(model, workflow_input={})

    assert exc_info.value.events[-1]["event_type"] == "node_failed"
    assert exc_info.value.events[-1]["node_id"] == "start"


@pytest.mark.asyncio
async def test_minimal_executor_async_accepts_required_schema_input_from_query_alias() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "required": ["message"],
                            "properties": {"message": {"type": "string"}},
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Question: {{#sys.query#}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(model, workflow_input={"query": "hello"})

    assert result.output == {"answer": "Question: hello"}


def test_minimal_executor_rejects_start_variable_type_mismatch() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {"variables": [{"name": "name", "type": "string"}]},
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Hello {{name}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_start_input_type_mismatch:name:string") as exc_info:
        MinimalWorkflowExecutor().execute(model, workflow_input={"name": 123})

    assert exc_info.value.events[-1]["event_type"] == "node_failed"
    assert exc_info.value.events[-1]["node_id"] == "start"


@pytest.mark.parametrize(
    ("field", "property_schema", "value", "expected_type"),
    [
        ("title", {"type": "string"}, 123, "string"),
        ("count", {"type": "integer"}, 1.5, "integer"),
        ("score", {"type": "number"}, True, "number"),
        ("enabled", {"type": "boolean"}, "true", "boolean"),
        ("items", {"type": "array"}, "alpha", "array"),
        ("payload", {"type": "object"}, "alpha", "object"),
        ("attachment", {"type": "file"}, "alpha", "object"),
        ("attachments", {"type": "files"}, {"name": "report.pdf"}, "array"),
    ],
)
def test_minimal_executor_rejects_start_schema_type_mismatches(
    field: str,
    property_schema: dict[str, object],
    value: object,
    expected_type: str,
) -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "properties": {field: property_schema},
                        }
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(
        WorkflowExecutionError,
        match=f"workflow_start_input_type_mismatch:{field}:{expected_type}",
    ):
        MinimalWorkflowExecutor().execute(model, workflow_input={field: value})


def test_minimal_executor_rejects_start_variable_enum_mismatch() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {
                                "name": "tone",
                                "type": "select",
                                "options": [{"label": "Warm", "value": "warm"}, {"label": "Formal", "value": "formal"}],
                            }
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Tone {{tone}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_start_input_enum_mismatch:tone"):
        MinimalWorkflowExecutor().execute(model, workflow_input={"tone": "cold"})

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"tone": "warm"})

    assert result.output == {"answer": "Tone warm"}


@pytest.mark.asyncio
async def test_minimal_executor_async_accepts_typed_start_schema_defaults() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "required": ["count"],
                            "properties": {"count": {"type": "integer", "default": 2}},
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Count {{count}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(model, workflow_input={})

    assert result.output == {"answer": "Count 2"}


@pytest.mark.parametrize(
    ("field", "property_schema", "value", "constraint"),
    [
        ("name", {"type": "string", "minLength": 3}, "Al", "minLength"),
        ("name", {"type": "string", "maxLength": 4}, "Alice", "maxLength"),
        ("score", {"type": "number", "minimum": 2}, 1, "minimum"),
        ("score", {"type": "number", "maximum": 2}, 3, "maximum"),
        ("score", {"type": "number", "exclusiveMinimum": 2}, 2, "exclusiveMinimum"),
        ("score", {"type": "number", "exclusiveMaximum": 2}, 2, "exclusiveMaximum"),
        ("items", {"type": "array", "minItems": 2}, ["one"], "minItems"),
        ("items", {"type": "array", "maxItems": 1}, ["one", "two"], "maxItems"),
        ("email", {"type": "string", "format": "email"}, "not-email", "format_email"),
        ("site", {"type": "string", "format": "url"}, "not-url", "format_url"),
    ],
)
def test_minimal_executor_rejects_start_schema_constraint_violations(
    field: str,
    property_schema: dict[str, object],
    value: object,
    constraint: str,
) -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "properties": {field: property_schema},
                        }
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(
        WorkflowExecutionError,
        match=f"workflow_start_input_constraint_violation:{field}:{constraint}",
    ):
        MinimalWorkflowExecutor().execute(model, workflow_input={field: value})


def test_minimal_executor_accepts_start_schema_constraint_matches() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "minLength": 3, "maxLength": 8},
                                "score": {"type": "number", "minimum": 1, "maximum": 5},
                                "items": {"type": "array", "minItems": 1, "maxItems": 2},
                                "email": {"type": "string", "format": "email"},
                                "site": {"type": "string", "format": "url"},
                            },
                        }
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "name": "Alice",
            "score": 3,
            "items": ["one"],
            "email": "alice@example.com",
            "site": "https://example.com/path",
        },
    )

    assert result.output == {"answer": "ok"}


def test_minimal_executor_accepts_file_like_start_input_types() -> None:
    model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {"name": "attachment", "type": "file"},
                            {"name": "attachments", "type": "files"},
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{attachment.name}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "attachment": {"name": "report.pdf"},
            "attachments": [{"name": "photo.png"}],
        },
    )

    assert result.output == {"answer": "report.pdf"}


def test_minimal_executor_resolves_list_indexes_in_templates() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "First {{items.0.name}} / second {{items.1.name}} / missing {{items.2.name}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"name": "alpha"}, {"name": "beta"}]},
    )

    assert result.output == {"answer": "First alpha / second beta / missing "}


def test_minimal_executor_resolves_bracket_list_indexes_in_templates() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "First {{items[0].name}} / nested {{matrix[0][1]}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"name": "alpha"}], "matrix": [["zero", "one"]]},
    )

    assert result.output == {"answer": "First alpha / nested one"}


def test_minimal_executor_resolves_workflow_sys_query_from_query_alias() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Question: {{#sys.query#}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"query": "hello"})

    assert result.output == {"answer": "Question: hello"}


@pytest.mark.asyncio
async def test_minimal_executor_async_resolves_workflow_sys_query_from_message_alias() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Question: {{#sys.query#}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(model, workflow_input={"message": "hello"})

    assert result.output == {"answer": "Question: hello"}


def test_minimal_executor_rejects_runtime_unsupported_nodes() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "code",
                    "type": "unsupported",
                    "source_type": "code",
                    "supported": False,
                    "data": {"language": "python3", "code": "return inputs"},
                    "metadata": {"unsupported_reason": "blocked_by_policy"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "code", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_code_node_blocked_by_policy:code"):
        MinimalWorkflowExecutor().execute(model, workflow_input={})


def test_minimal_executor_sync_rejects_llm_without_async_executor() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "llm", "type": "llm", "supported": True, "data": {}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_llm_requires_async_executor"):
        MinimalWorkflowExecutor().execute(model, workflow_input={})


def test_static_validator_rejects_hidden_unsupported_branch() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "branch", "type": "condition", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "llm", "type": "llm", "supported": True, "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "answer", "source_handle": "false", "valid": True},
                {"id": "e3", "source": "branch", "target": "llm", "source_handle": "true", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().validate_static(model)

    assert result.runnable is False
    assert "workflow_llm_node_not_allowed:llm:workflow_llm_invoker_unavailable" in result.errors


def test_static_validator_accepts_llm_when_invoker_available() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {"prompt_template": "Answer {{#sys.query#}}"},
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{llm.text}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "llm", "valid": True},
                {"id": "e2", "source": "llm", "target": "answer", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().validate_static(model, llm_available=True)

    assert result.errors == []


def test_static_validator_checks_all_reachable_tool_calls() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "branch", "type": "condition", "supported": True, "data": {}},
                {
                    "id": "visible",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "echo_tool"},
                },
                {
                    "id": "hidden",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "missing_tool"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "visible", "source_handle": "false", "valid": True},
                {"id": "e3", "source": "branch", "target": "hidden", "source_handle": "true", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().validate_static(model, available_tool_names={"echo_tool"})

    assert result.runnable is False
    assert "workflow_tool_not_available:missing_tool" in result.errors


def test_minimal_executor_runs_condition_true_branch() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {
                                "variable_selector": ["tier"],
                                "comparison_operator": "equals",
                                "value": "pro",
                            }
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Yes"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "No"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {
                    "id": "e2",
                    "source": "branch",
                    "target": "yes",
                    "source_handle": "true",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "branch",
                    "target": "no",
                    "source_handle": "false",
                    "valid": True,
                },
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"tier": "pro"})

    assert result.output == {"answer": "Yes"}
    condition_event = [event for event in result.events if event["node_id"] == "branch"][-1]
    assert condition_event["payload"]["output"] == {"branch": "true", "matched": True}


def test_minimal_executor_runs_condition_case_and_fallback_branch() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "cases": [
                            {
                                "case_id": "case-a",
                                "conditions": [
                                    {
                                        "variable": "score",
                                        "operator": ">=",
                                        "value": 90,
                                    }
                                ],
                            }
                        ]
                    },
                },
                {"id": "a", "type": "answer", "supported": True, "data": {"answer": "A"}},
                {"id": "b", "type": "answer", "supported": True, "data": {"answer": "B"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {
                    "id": "e2",
                    "source": "branch",
                    "target": "a",
                    "source_handle": "case-a",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "branch",
                    "target": "b",
                    "source_handle": "default",
                    "valid": True,
                },
            ],
        }
    }

    matched = MinimalWorkflowExecutor().execute(model, workflow_input={"score": 95})
    fallback = MinimalWorkflowExecutor().execute(model, workflow_input={"score": 60})

    assert matched.output == {"answer": "A"}
    assert fallback.output == {"answer": "B"}


def test_minimal_executor_condition_resolves_right_hand_selector() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {
                                "variable_selector": ["profile", "tier"],
                                "comparison_operator": "equals",
                                "value_selector": ["expected", "tier"],
                            },
                            {
                                "variable": "profile.name",
                                "operator": "equals",
                                "rightSelector": "names[0]",
                            },
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Match"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "No"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "profile": {"tier": "pro", "name": "Alice"},
            "expected": {"tier": "pro"},
            "names": ["Alice"],
        },
    )

    assert result.output == {"answer": "Match"}


def test_minimal_executor_condition_supports_nested_groups() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {"variable": "tier", "operator": "equals", "value": "pro"},
                            {
                                "logicalOperator": "or",
                                "conditions": [
                                    {"variable": "region", "operator": "equals", "value": "us"},
                                    {"variable": "region", "operator": "equals", "value": "eu"},
                                ],
                            },
                            {
                                "combinator": "or",
                                "rules": [
                                    {"variable": "status", "operator": "equals", "value": "blocked"},
                                    {"variable": "status", "operator": "equals", "value": "deleted"},
                                ],
                                "negate": True,
                            },
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Eligible"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "Fallback"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    matched = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"tier": "pro", "region": "eu", "status": "active"},
    )
    fallback = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"tier": "pro", "region": "apac", "status": "active"},
    )
    blocked = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"tier": "pro", "region": "us", "status": "blocked"},
    )

    assert matched.output == {"answer": "Eligible"}
    assert fallback.output == {"answer": "Fallback"}
    assert blocked.output == {"answer": "Fallback"}


def test_minimal_executor_condition_supports_membership_operators() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {
                                "variable": "tier",
                                "operator": "in",
                                "value": ["pro", "team"],
                            },
                            {
                                "variable": "tags",
                                "operator": "not in",
                                "value": "blocked",
                            },
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Allowed"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "Denied"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    allowed = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"tier": "team", "tags": ["beta", "customer"]},
    )
    denied = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"tier": "free", "tags": ["beta"]},
    )

    assert allowed.output == {"answer": "Allowed"}
    assert denied.output == {"answer": "Denied"}


def test_minimal_executor_condition_supports_string_operator_aliases() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {"variable": "title", "operator": "start with", "value": "Invoice"},
                            {"variable": "title", "operator": "end with", "value": "2026"},
                            {"variable": "title", "operator": "not starts with", "value": "Draft"},
                            {"variable": "title", "operator": "not ends with", "value": "2025"},
                            {"variable": "title", "operator": "not contain", "value": "void"},
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Match"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "No"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"title": "Invoice ACME 2026"})

    assert result.output == {"answer": "Match"}


def test_minimal_executor_condition_supports_presence_null_and_boolean_operators() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {"variable": "user.name", "operator": "exists"},
                            {"variable": "deleted_at", "operator": "is null"},
                            {"variable": "profile", "operator": "not null"},
                            {"variable": "enabled", "operator": "is true"},
                            {"variable": "archived", "operator": "is false"},
                            {"variable": "missing", "operator": "not exists"},
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Ready"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "No"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "user": {"name": "Ada"},
            "deleted_at": None,
            "profile": {"tier": "team"},
            "enabled": "yes",
            "archived": "0",
        },
    )

    assert result.output == {"answer": "Ready"}


def test_minimal_executor_condition_supports_regex_operators() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {"variable": "email", "operator": "matches regex", "value": r"^[^@]+@example\.com$"},
                            {"variable": "sku", "operator": "not regex", "value": r"^tmp-"},
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Match"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "No"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    matched = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"email": "alice@example.com", "sku": "prod-1"},
    )
    unmatched = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"email": "alice@example.org", "sku": "prod-1"},
    )

    assert matched.output == {"answer": "Match"}
    assert unmatched.output == {"answer": "No"}


def test_minimal_executor_condition_rejects_invalid_regex() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {"conditions": [{"variable": "text", "operator": "regex", "value": "["}]},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "branch", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_condition_regex_invalid"):
        MinimalWorkflowExecutor().execute(model, workflow_input={"text": "alpha"})


def test_minimal_executor_condition_supports_iso_date_comparison() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "branch",
                    "type": "condition",
                    "supported": True,
                    "data": {
                        "conditions": [
                            {"variable": "started_at", "operator": "on or after", "value": "2026-06-25T00:00:00Z"},
                            {"variable": "due_date", "operator": "before", "value": "2026-07-01"},
                        ]
                    },
                },
                {"id": "yes", "type": "answer", "supported": True, "data": {"answer": "Inside"}},
                {"id": "no", "type": "answer", "supported": True, "data": {"answer": "Outside"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "branch", "valid": True},
                {"id": "e2", "source": "branch", "target": "yes", "source_handle": "true", "valid": True},
                {"id": "e3", "source": "branch", "target": "no", "source_handle": "false", "valid": True},
            ],
        }
    }

    inside = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"started_at": "2026-06-25T08:30:00+08:00", "due_date": "2026-06-30"},
    )
    outside = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"started_at": "2026-06-24T23:59:00Z", "due_date": "2026-06-30"},
    )

    assert inside.output == {"answer": "Inside"}
    assert outside.output == {"answer": "Outside"}


def test_minimal_executor_runs_template_transform_and_variable_aggregator() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "template",
                    "type": "template_transform",
                    "supported": True,
                    "data": {"template": "Hello {{name}}", "output_key": "rendered"},
                },
                {
                    "id": "aggregate",
                    "type": "variable_aggregator",
                    "supported": True,
                    "data": {
                        "output_key": "picked",
                        "variables": [
                            {"variable_selector": ["missing"]},
                            {"variable_selector": ["rendered"]},
                        ],
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{picked}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "template", "valid": True},
                {"id": "e2", "source": "template", "target": "aggregate", "valid": True},
                {"id": "e3", "source": "aggregate", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "LambChat"})

    assert validation.errors == []
    assert result.output == {"answer": "Hello LambChat"}


def test_minimal_executor_template_transform_accepts_text_parts() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "template",
                    "type": "template_transform",
                    "supported": True,
                    "data": {
                        "content": [
                            {"type": "text", "text": "Hello {{name}}"},
                            " from ",
                            {"type": "markdown", "data": "{{team}}"},
                            {"type": "image", "url": "https://example.invalid/ignored.png"},
                        ],
                        "output_key": "rendered",
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{rendered}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "template", "valid": True},
                {"id": "e2", "source": "template", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(model, workflow_input={"name": "Ada", "team": "Core"})

    assert validation.errors == []
    assert result.output == {"answer": "Hello Ada from Core"}


def test_minimal_executor_variable_aggregator_accepts_input_variable_descriptors() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "aggregate",
                    "type": "variable_aggregator",
                    "supported": True,
                    "data": {
                        "output_key": "picked",
                        "input_variables": [
                            {"name": "fallback"},
                            {"value_selector": ["profile", "display_name"]},
                        ],
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{picked}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "aggregate", "valid": True},
                {"id": "e2", "source": "aggregate", "target": "answer", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"fallback": "", "profile": {"display_name": "Ada"}},
    )

    assert result.output == {"answer": "Ada"}


def test_minimal_executor_variable_aggregator_accepts_mapping_and_output_type_array() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "aggregate",
                    "type": "variable_aggregator",
                    "supported": True,
                    "data": {
                        "output_key": "values",
                        "output_type": "array",
                        "variables": {
                            "first": ["profile", "name"],
                            "second": {"selector": ["team", "name"]},
                            "missing": ["missing"],
                        },
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "aggregate", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"profile": {"name": "Ada"}, "team": {"name": "Core"}},
    )

    assert validation.errors == []
    assert result.output["values"] == ["Ada", "Core"]


def test_minimal_executor_variable_aggregator_accepts_grouped_selector_wrappers() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "aggregate",
                    "type": "variable_aggregator",
                    "supported": True,
                    "data": {
                        "output_key": "picked",
                        "variable_groups": [
                            {
                                "group_name": "primary",
                                "value": [
                                    {"value_selector": ["missing"]},
                                    {"selector": ["profile", "display_name"]},
                                ],
                            },
                            {
                                "group_name": "fallback",
                                "selectors": [
                                    {"variable_selector": ["account", "label"]},
                                ],
                            },
                        ],
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{picked}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "aggregate", "valid": True},
                {"id": "e2", "source": "aggregate", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "profile": {"display_name": "Ada"},
            "account": {"label": "Fallback"},
        },
    )

    assert validation.errors == []
    assert result.output == {"answer": "Ada"}


def test_minimal_executor_variable_assign_resolves_selector_values() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "assign",
                    "type": "variable_assign",
                    "supported": True,
                    "data": {
                        "variables": [
                            {
                                "variable": "first_title",
                                "value_selector": ["items", 0, "title"],
                            },
                            {
                                "target_variable": "second_title",
                                "sourceSelector": "items[1].title",
                            },
                        ],
                        "assignments": {
                            "copied_tone": {"valueSelector": ["tone"]},
                        },
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{first_title}} / {{second_title}} / {{copied_tone}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "valid": True},
                {"id": "e2", "source": "assign", "target": "answer", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [{"title": "Alpha"}, {"title": "Beta"}],
            "tone": "warm",
        },
    )

    assert result.output == {"answer": "Alpha / Beta / warm"}


def test_minimal_executor_variable_assign_resolves_structured_values() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "assign",
                    "type": "variable_assign",
                    "supported": True,
                    "data": {
                        "assignments": {
                            "payload": {
                                "title": {"value_selector": ["items", 0, "title"]},
                                "owner": "{{user.name}}",
                                "tags": ["{{tone}}", {"value_selector": ["items", 1, "title"]}],
                            }
                        }
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                    "supported": True,
                    "data": {"outputs": {"payload": {}}},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "valid": True},
                {"id": "e2", "source": "assign", "target": "end", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [{"title": "Alpha"}, {"title": "Beta"}],
            "tone": "warm",
            "user": {"name": "Ada"},
        },
    )

    assert result.output == {
        "payload": {
            "title": "Alpha",
            "owner": "Ada",
            "tags": ["warm", "Beta"],
        }
    }


def test_minimal_executor_variable_assign_accepts_mapping_items() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "assign",
                    "type": "variable_assign",
                    "supported": True,
                    "data": {
                        "variables": {
                            "first_title": {"value_selector": ["items", 0, "title"]},
                            "summary": "Hello {{name}}",
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{summary}} / {{first_title}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "valid": True},
                {"id": "e2", "source": "assign", "target": "answer", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"title": "Alpha"}], "name": "LambChat"},
    )

    assert result.output == {"answer": "Hello LambChat / Alpha"}


def test_minimal_executor_variable_assign_accepts_workflow_assignment_lists() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "assign",
                    "type": "variable_assign",
                    "supported": True,
                    "data": {
                        "variable_assignments": [
                            {
                                "assigned_variable_selector": ["first_title"],
                                "value_selector": ["items", 0, "title"],
                            },
                            {
                                "assignedVariable": "summary",
                                "value": "Hello {{name}}",
                            },
                        ],
                        "assignments": [
                            {
                                "variableSelector": ["second_title"],
                                "sourceSelector": ["items", 1, "title"],
                            }
                        ],
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{summary}} / {{first_title}} / {{second_title}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "assign", "valid": True},
                {"id": "e2", "source": "assign", "target": "answer", "valid": True},
            ],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"title": "Alpha"}, {"title": "Beta"}], "name": "LambChat"},
    )

    assert result.output == {"answer": "Hello LambChat / Alpha / Beta"}


def test_minimal_executor_runs_list_operator_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "pick",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "first",
                        "output_key": "first_item",
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{first_item}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "pick", "valid": True},
                {"id": "e2", "source": "pick", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(model, workflow_input={"items": ["alpha", "beta"]})

    assert validation.errors == []
    assert result.output == {"answer": "alpha"}


@pytest.mark.parametrize(
    ("operation", "data", "expected"),
    [
        ("last", {}, "gamma"),
        ("count", {}, 3),
        ("join", {"separator": "|"}, "alpha|beta|gamma"),
        ("slice", {"start": 1, "limit": 2}, ["beta", "gamma"]),
        ("item_at", {"index": 1}, "beta"),
        ("get", {"index": -1}, "gamma"),
        ("index", {"index": 9}, None),
        ("reverse", {}, ["gamma", "beta", "alpha"]),
        ("unique", {}, ["alpha", "beta", "gamma"]),
        ("sum", {}, 6),
        ("average", {}, 2),
        ("min", {}, 1),
        ("max", {}, 3),
    ],
)
def test_minimal_executor_list_operator_supported_operations(
    operation: str,
    data: dict,
    expected: object,
) -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": operation,
                        "output_key": "result",
                        **data,
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": ["alpha", "beta", "gamma"] if operation not in {"sum", "average", "min", "max"} else [1, 2, 3]},
    )

    assert result.output["result"] == expected


def test_minimal_executor_list_operator_dedupes_structured_items() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "dedupe",
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [
                {"name": "alpha", "tags": ["x", "y"]},
                {"name": "beta", "tags": []},
                {"name": "alpha", "tags": ["x", "y"]},
            ]
        },
    )

    assert result.output["result"] == [
        {"name": "alpha", "tags": ["x", "y"]},
        {"name": "beta", "tags": []},
    ]


def test_minimal_executor_list_operator_sorts_by_object_field_descending() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "sort",
                        "sort_by": "score",
                        "direction": "desc",
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [
                {"name": "beta", "score": 2},
                {"name": "missing"},
                {"name": "alpha", "score": 3},
                {"name": "gamma", "score": 2},
            ]
        },
    )

    assert result.output["result"] == [
        {"name": "alpha", "score": 3},
        {"name": "beta", "score": 2},
        {"name": "gamma", "score": 2},
        {"name": "missing"},
    ]


def test_minimal_executor_list_operator_sums_object_field_values() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "sum",
                        "value_key": "score",
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [
                {"name": "alpha", "score": 3},
                {"name": "beta", "score": "2.5"},
                {"name": "ignored"},
            ]
        },
    )

    assert result.output["result"] == 5.5


def test_minimal_executor_list_operator_plucks_object_field_values() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "pluck",
                        "value_key": "profile.name",
                        "output_key": "names",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "items": [
                {"profile": {"name": "alpha"}},
                {"profile": {"name": "beta"}},
                {"profile": {}},
            ]
        },
    )

    assert result.output["names"] == ["alpha", "beta", None]


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("find", {"name": "beta", "score": 3, "active": True}),
        ("first_match", {"name": "beta", "score": 3, "active": True}),
        ("any", True),
        ("all", False),
        ("none", False),
        ("count_matching", 2),
    ],
)
def test_minimal_executor_list_operator_condition_result_operations(operation: str, expected: object) -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": operation,
                        "conditions": [
                            {"variable_selector": ["item", "score"], "operator": ">=", "value": "{{min_score}}"},
                            {"variable_selector": ["item", "active"], "operator": "is true"},
                        ],
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "min_score": 2,
            "items": [
                {"name": "alpha", "score": 1, "active": True},
                {"name": "beta", "score": 3, "active": True},
                {"name": "gamma", "score": 4, "active": False},
                {"name": "delta", "score": "2.5", "active": True},
            ],
        },
    )

    assert result.output["result"] == expected


def test_minimal_executor_list_operator_all_and_none_on_empty_lists_are_false_and_true() -> None:
    def execute(operation: str) -> object:
        model = {
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "list",
                        "type": "list_operator",
                        "supported": True,
                        "data": {
                            "variable_selector": ["items"],
                            "operation": operation,
                            "conditions": [{"variable": "item", "operator": "not empty"}],
                            "output_key": "result",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
            }
        }
        return MinimalWorkflowExecutor().execute(model, workflow_input={"items": []}).output["result"]

    assert execute("all") is False
    assert execute("none") is True


def test_minimal_executor_list_operator_resolves_dynamic_index_parameter() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "item_at",
                        "index_selector": ["cursor", "position"],
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": ["alpha", "beta", "gamma"], "cursor": {"position": 2}},
    )

    assert result.output["result"] == "gamma"


def test_minimal_executor_list_operator_resolves_dynamic_slice_parameters() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "slice",
                        "startSelector": ["window", "start"],
                        "limit_selector": ["window", "limit"],
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": ["alpha", "beta", "gamma", "delta"], "window": {"start": 1, "limit": 2}},
    )

    assert result.output["result"] == ["beta", "gamma"]


def test_minimal_executor_list_operator_resolves_templated_numeric_parameter() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "list",
                    "type": "list_operator",
                    "supported": True,
                    "data": {
                        "variable_selector": ["items"],
                        "operation": "get",
                        "index": "{{wanted_index}}",
                        "output_key": "result",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": ["alpha", "beta", "gamma"], "wanted_index": 1},
    )

    assert result.output["result"] == "beta"


def test_static_validator_rejects_malformed_list_operator_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "list", "type": "list_operator", "supported": True, "data": {"operation": "map"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "list", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert "workflow_list_operator_node_not_allowed:list:workflow_list_operator_selector_missing" in validation.errors


def test_minimal_executor_runs_iteration_node_with_template() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "loop",
                    "type": "iteration",
                    "supported": True,
                    "data": {
                        "iterator_selector": ["items"],
                        "item_template": "{{index}}:{{item.name}}",
                        "output_key": "rendered_items",
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{rendered_items_count}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "loop", "valid": True},
                {"id": "e2", "source": "loop", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"name": "alpha"}, {"name": "beta"}]},
    )

    assert validation.errors == []
    assert result.output == {"answer": "2"}
    loop_event = next(
        event for event in result.events if event["node_id"] == "loop" and event["event_type"] == "node_finished"
    )
    assert loop_event["payload"]["output"] == {
        "rendered_items": ["0:alpha", "1:beta"],
        "rendered_items_count": 2,
        "iteration_count": 2,
    }


def test_minimal_executor_iteration_accepts_text_part_item_template() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "loop",
                    "type": "iteration",
                    "supported": True,
                    "data": {
                        "iterator_selector": ["items"],
                        "itemTemplate": [
                            {"type": "text", "text": "{{index}}"},
                            ":",
                            {"type": "markdown", "data": "{{item.name}}"},
                            {"type": "image", "url": "https://example.invalid/ignored.png"},
                        ],
                        "output_key": "rendered_items",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "loop", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": [{"name": "alpha"}, {"name": "beta"}]},
    )

    assert result.output["rendered_items"] == ["0:alpha", "1:beta"]
    assert result.output["iteration_count"] == 2


def test_minimal_executor_iteration_defaults_to_original_items() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "loop",
                    "type": "iteration",
                    "supported": True,
                    "data": {"iterator_selector": ["items"], "output_key": "items_out"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "loop", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(model, workflow_input={"items": ["alpha", "beta"]})

    assert result.output["items_out"] == ["alpha", "beta"]
    assert result.output["items_out_count"] == 2


def test_minimal_executor_iteration_resolves_dynamic_max_items() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "loop",
                    "type": "iteration",
                    "supported": True,
                    "data": {
                        "iterator_selector": ["items"],
                        "max_items_selector": ["limits", "max"],
                        "output_key": "items_out",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "loop", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"items": ["alpha", "beta"], "limits": {"max": 2}},
    )

    assert result.output["items_out"] == ["alpha", "beta"]
    assert result.output["iteration_count"] == 2


def test_minimal_executor_iteration_resolves_templated_max_items_limit() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "loop",
                    "type": "iteration",
                    "supported": True,
                    "data": {
                        "iterator_selector": ["items"],
                        "limit": "{{limit}}",
                        "output_key": "items_out",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "loop", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_iteration_item_limit_exceeded:2>1"):
        MinimalWorkflowExecutor().execute(model, workflow_input={"items": ["alpha", "beta"], "limit": 1})


def test_minimal_executor_runs_document_extractor_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "document_extractor",
                    "supported": True,
                    "data": {"variable_selector": ["files"], "output_key": "document_text"},
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{document_text_count}}:{{document_text}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "extract", "valid": True},
                {"id": "e2", "source": "extract", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "files": [
                {"name": "one.md", "content": "Alpha"},
                {"name": "two.md", "markdown": "Beta"},
            ]
        },
    )

    assert validation.errors == []
    assert result.output == {"answer": "2:Alpha\nBeta"}
    extract_event = next(
        event for event in result.events if event["node_id"] == "extract" and event["event_type"] == "node_finished"
    )
    assert extract_event["payload"]["output"]["document_count"] == 2
    assert extract_event["payload"]["output"]["document_text"] == "Alpha\nBeta"


def test_minimal_executor_document_extractor_accepts_indexed_selector() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "document_extractor",
                    "supported": True,
                    "data": {"variable_selector": ["files", 1], "output_key": "document_text"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "files": [
                {"content": "Alpha"},
                {"content": "Beta"},
            ]
        },
    )

    assert result.output["document_text"] == "Beta"
    assert result.output["document_count"] == 1


def test_minimal_executor_document_extractor_accepts_bracket_selector() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "document_extractor",
                    "supported": True,
                    "data": {"variable_selector": "files[1]", "output_key": "document_text"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={"files": [{"content": "Alpha"}, {"markdown": "Beta"}]},
    )

    assert result.output["document_text"] == "Beta"
    assert result.output["document_count"] == 1


def test_minimal_executor_document_extractor_unwraps_workflow_file_payloads() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "document_extractor",
                    "supported": True,
                    "data": {"variable_selector": ["files"], "output_key": "document_text"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().execute(
        model,
        workflow_input={
            "files": [
                {"name": "alpha.pdf", "file": {"metadata": {"extracted_text": "Alpha"}}},
                {"name": "beta.pdf", "document": {"pages": [{"page_content": "Beta 1"}, {"text": "Beta 2"}]}},
            ]
        },
    )

    assert result.output["document_text"] == "Alpha\nBeta 1\nBeta 2"
    assert result.output["document_count"] == 2


def test_static_validator_rejects_malformed_document_extractor_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "extract", "type": "document_extractor", "supported": True, "data": {}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert "workflow_document_extractor_node_not_allowed:extract:workflow_document_extractor_selector_missing" in validation.errors


def test_static_validator_rejects_malformed_iteration_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "loop", "type": "iteration", "supported": True, "data": {}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "loop", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert "workflow_iteration_node_not_allowed:loop:workflow_iteration_selector_missing" in validation.errors


def test_static_validator_rejects_malformed_data_transform_nodes() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "template", "type": "template_transform", "supported": True, "data": {}},
                {"id": "aggregate", "type": "variable_aggregator", "supported": True, "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "template", "valid": True},
                {"id": "e2", "source": "template", "target": "aggregate", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert "workflow_template_transform_template_missing:template" in validation.errors
    assert "workflow_variable_aggregator_selectors_missing:aggregate" in validation.errors


def test_static_validator_rejects_unreachable_nodes() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "orphan", "type": "llm", "supported": True, "data": {"prompt": "hidden"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)

    assert validation.reachable_node_ids == {"start", "answer"}
    assert "workflow_unreachable_node:orphan" in validation.errors


def test_static_validator_treats_answer_to_end_as_reachable() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "end", "type": "end", "supported": True, "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "answer", "valid": True},
                {"id": "e2", "source": "answer", "target": "end", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert validation.errors == []
    assert validation.reachable_node_ids == {"start", "answer", "end"}


def test_minimal_executor_rejects_unreachable_nodes_before_running() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "orphan", "type": "llm", "supported": True, "data": {"prompt": "hidden"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }

    with pytest.raises(
        WorkflowExecutionError,
        match="workflow_static_validation_failed:workflow_unreachable_node:orphan",
    ):
        MinimalWorkflowExecutor().execute(model, workflow_input={})


@pytest.mark.asyncio
async def test_minimal_executor_runs_tool_call_node_with_async_invoker() -> None:
    calls = []

    async def invoke(tool_name: str, arguments: dict) -> dict:
        calls.append((tool_name, arguments))
        return {"echo": arguments["text"]}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {
                        "tool_name": "echo_tool",
                        "arguments": {"text": "Hello {{name}}"},
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{tool_result.echo}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "tool", "valid": True},
                {"id": "e2", "source": "tool", "target": "answer", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"name": "LambChat"},
        tool_invoker=invoke,
    )

    assert calls == [("echo_tool", {"text": "Hello LambChat"})]
    assert result.output == {"answer": "Hello LambChat"}


@pytest.mark.asyncio
async def test_minimal_executor_resolves_structured_selector_descriptors() -> None:
    calls = []

    async def invoke(tool_name: str, arguments: dict) -> dict:
        calls.append((tool_name, arguments))
        return {"echo": arguments}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {
                        "tool_name": "echo_tool",
                        "arguments": {
                            "title": {"value_selector": ["items", 0, "title"]},
                            "owner": {"value": "{{user.name}}"},
                            "literal_object": {"kind": "selector", "selector": ["items", 1, "title"]},
                        },
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                    "supported": True,
                    "data": {"outputs": {"title": {"value_selector": ["tool_result", "echo", "title"]}}},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "tool", "valid": True},
                {"id": "e2", "source": "tool", "target": "end", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={
            "items": [{"title": "Alpha"}, {"title": "Beta"}],
            "user": {"name": "Ada"},
        },
        tool_invoker=invoke,
    )

    assert calls == [
        (
            "echo_tool",
            {
                "title": "Alpha",
                "owner": "Ada",
                "literal_object": {"kind": "selector", "selector": ["items", 1, "title"]},
            },
        )
    ]
    assert result.output == {"title": "Alpha"}


@pytest.mark.asyncio
async def test_minimal_executor_tool_call_accepts_workflow_parameter_descriptors() -> None:
    calls = []

    async def invoke(tool_name: str, arguments: dict) -> dict:
        calls.append((tool_name, arguments))
        return {"echo": arguments}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {
                        "tool_name": "echo_tool",
                        "tool_configurations": [
                            {"name": "scope", "value": "{{scope}}"},
                            {"name": "title", "value_selector": ["items", 0, "title"]},
                            {"key": "limit", "default": 3},
                        ],
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "tool", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"scope": "published", "items": [{"title": "Alpha"}]},
        tool_invoker=invoke,
    )

    assert calls == [("echo_tool", {"scope": "published", "title": "Alpha", "limit": 3})]
    assert result.output["tool_result"] == {"echo": {"scope": "published", "title": "Alpha", "limit": 3}}


@pytest.mark.asyncio
async def test_minimal_executor_runs_knowledge_retrieval_node_with_retriever() -> None:
    requests = []

    async def retrieve(request: dict) -> dict:
        requests.append(request)
        return {
            "success": True,
            "memories": [{"memory_id": "m1", "content": "Workflow memory"}],
        }

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "knowledge",
                    "type": "knowledge_retrieval",
                    "supported": True,
                    "data": {
                        "query_variable_selector": ["message"],
                        "dataset_ids": ["dataset-1"],
                        "output_key": "knowledge",
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{knowledge.text}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "knowledge", "valid": True},
                {"id": "e2", "source": "knowledge", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, knowledge_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "workflow"},
        knowledge_retriever=retrieve,
    )

    assert validation.errors == []
    assert requests == [
        {
            "query": "workflow",
            "dataset_ids": ["dataset-1"],
            "dataset_filters": {},
            "top_k": 5,
            "score_threshold": None,
        }
    ]
    assert result.output == {"answer": "Workflow memory"}


@pytest.mark.asyncio
async def test_minimal_executor_includes_knowledge_dataset_filters() -> None:
    requests = []

    async def retrieve(request: dict) -> dict:
        requests.append(request)
        return {"success": True, "items": []}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "knowledge",
                    "type": "knowledge_retrieval",
                    "supported": True,
                    "data": {
                        "query": "{{message}}",
                        "dataset_ids": ["dataset-1"],
                        "dataset_filter": {"scope": "project"},
                        "metadata_filter": {"owner": "team-a"},
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "knowledge", "valid": True}],
        }
    }

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "workflow"},
        knowledge_retriever=retrieve,
    )

    assert requests == [
        {
            "query": "workflow",
            "dataset_ids": ["dataset-1"],
            "dataset_filters": {"scope": "project", "metadata": {"owner": "team-a"}},
            "top_k": 5,
            "score_threshold": None,
        }
    ]


@pytest.mark.asyncio
async def test_minimal_executor_resolves_dynamic_knowledge_retrieval_limits() -> None:
    requests = []

    async def retrieve(request: dict) -> dict:
        requests.append(request)
        return {"success": True, "items": []}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "knowledge",
                    "type": "knowledge_retrieval",
                    "supported": True,
                    "data": {
                        "query": "{{message}}",
                        "top_k_selector": ["retrieval", "limit"],
                        "scoreThreshold": "{{retrieval.threshold}}",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "knowledge", "valid": True}],
        }
    }

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "workflow", "retrieval": {"limit": 3, "threshold": "0.72"}},
        knowledge_retriever=retrieve,
    )

    assert requests[0]["top_k"] == 3
    assert requests[0]["score_threshold"] == 0.72


def test_static_validator_rejects_knowledge_retrieval_without_retriever() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "knowledge",
                    "type": "knowledge_retrieval",
                    "supported": True,
                    "data": {"query": "{{message}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "knowledge", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)

    assert (
        "workflow_knowledge_retrieval_node_not_allowed:knowledge:workflow_knowledge_retriever_unavailable"
        in validation.errors
    )


@pytest.mark.asyncio
async def test_minimal_executor_stops_between_nodes_when_cancelled() -> None:
    checks = 0

    async def is_cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "first",
                    "type": "template_transform",
                    "supported": True,
                    "data": {"template": "Hello {{name}}", "output_key": "rendered"},
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{rendered}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "first", "valid": True},
                {"id": "e2", "source": "first", "target": "answer", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"name": "LambChat"},
        cancel_checker=is_cancelled,
    )

    assert result.output == {"name": "LambChat"}
    assert [event["node_id"] for event in result.events] == ["start", "start"]
    assert checks == 3


@pytest.mark.asyncio
async def test_minimal_executor_times_out_long_running_llm_node() -> None:
    async def invoke_llm(request: dict) -> dict:
        await asyncio.sleep(1)
        return {"text": "late"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {"prompt_template": "Answer {{message}}", "timeout_seconds": 0.01},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "llm", "valid": True},
            ],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_node_timeout:llm:llm") as exc_info:
        await MinimalWorkflowExecutor().execute_async(
            model,
            workflow_input={"message": "hello"},
            llm_invoker=invoke_llm,
        )

    assert [event["event_type"] for event in exc_info.value.events] == [
        "node_started",
        "node_finished",
        "node_started",
        "node_failed",
    ]
    assert exc_info.value.events[-1]["payload"]["error"] == "workflow_node_timeout:llm:llm"


@pytest.mark.asyncio
async def test_minimal_executor_cancels_in_flight_tool_call() -> None:
    cancelled = False
    checks = 0

    async def invoke_tool(tool_name: str, arguments: dict) -> dict:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return {"late": True}

    async def is_cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "echo_tool", "arguments": {}},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "tool", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_node_cancelled:tool:tool_call"):
        await MinimalWorkflowExecutor().execute_async(
            model,
            workflow_input={},
            tool_invoker=invoke_tool,
            cancel_checker=is_cancelled,
        )

    assert cancelled is True


@pytest.mark.asyncio
async def test_minimal_executor_requires_tool_invoker_for_tool_call_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "echo_tool"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "tool", "valid": True}],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_tool_invoker_unavailable"):
        await MinimalWorkflowExecutor().execute_async(model, workflow_input={})


@pytest.mark.asyncio
async def test_minimal_executor_error_includes_node_failure_events() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "echo_tool"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "tool", "valid": True},
            ],
        }
    }

    with pytest.raises(WorkflowExecutionError, match="workflow_tool_invoker_unavailable") as exc_info:
        await MinimalWorkflowExecutor().execute_async(model, workflow_input={})

    assert [event["event_type"] for event in exc_info.value.events] == [
        "node_started",
        "node_finished",
        "node_started",
        "node_failed",
    ]
    assert exc_info.value.events[-1]["node_id"] == "tool"
    assert exc_info.value.events[-1]["payload"]["error"] == "workflow_tool_invoker_unavailable"
    assert isinstance(exc_info.value.events[-1]["payload"].get("duration_ms"), int)


@pytest.mark.asyncio
async def test_minimal_executor_runs_llm_node_with_async_invoker() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "Hello from LLM", "model": request.get("model"), "usage": {"input_tokens": 3}}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "model": {"provider": "openai", "name": "gpt-4o-mini"},
                        "prompt_template": "Answer {{#sys.query#}}",
                        "temperature": 0.2,
                    },
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "{{llm.text}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "llm", "valid": True},
                {"id": "e2", "source": "llm", "target": "answer", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"sys": {"query": "LambChat"}},
        llm_invoker=invoke_llm,
    )

    assert requests == [
        {
            "prompt": "Answer LambChat",
            "messages": [],
            "model_id": None,
            "model": "openai/gpt-4o-mini",
            "temperature": 0.2,
        }
    ]
    assert result.output == {"answer": "Hello from LLM"}


@pytest.mark.asyncio
async def test_minimal_executor_llm_injects_vault_api_key() -> None:
    requests = []
    resolved_refs: list[str] = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok", "model": request.get("model"), "usage": {}}

    async def resolve_secret(ref: str) -> str | None:
        resolved_refs.append(ref)
        return "llm-secret" if ref == "llm:provider_credential_id:openai-main" else None

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "model": {
                            "provider": "openai",
                            "name": "gpt-4o-mini",
                            "provider_credential_id": "openai-main",
                        },
                        "prompt_template": "Answer {{message}}",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello"},
        llm_invoker=invoke_llm,
        credential_secret_resolver=resolve_secret,
    )

    assert resolved_refs[0] == "openai-main"
    assert "llm:provider_credential_id:openai-main" in resolved_refs
    assert requests[0]["api_key"] == "llm-secret"
    assert result.output["llm_text"] == "ok"
    assert "llm-secret" not in repr(result.events)


@pytest.mark.asyncio
async def test_minimal_executor_llm_injects_json_credential_payload() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok", "model": request.get("model"), "usage": {}}

    async def resolve_secret(ref: str) -> str | None:
        if ref == "llm:llm_provider:openai":
            return '{"api_key":"json-key","base_url":"https://llm.example/v1"}'
        return None

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "model": {"provider": "openai", "name": "gpt-4o-mini"},
                        "prompt_template": "Answer {{message}}",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello"},
        llm_invoker=invoke_llm,
        credential_secret_resolver=resolve_secret,
    )

    assert requests[0]["api_key"] == "json-key"
    assert requests[0]["api_base"] == "https://llm.example/v1"


@pytest.mark.asyncio
async def test_minimal_executor_llm_accepts_workflow_prompt_template_messages() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "prompt_template": [
                            {"name": "system", "text": "You are concise."},
                            {"name": "user", "template": "Question: {{message}}"},
                            {"name": "assistant", "promptTemplate": "Ready."},
                        ]
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "What changed?"},
        llm_invoker=invoke_llm,
    )

    assert validation.errors == []
    assert requests[0]["prompt"] == ""
    assert requests[0]["messages"] == [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Question: What changed?"},
        {"role": "assistant", "content": "Ready."},
    ]
    assert result.output["llm_text"] == "ok"


@pytest.mark.asyncio
async def test_minimal_executor_llm_flattens_text_message_parts() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Question: {{message}}"},
                                    "\nContext: ",
                                    {"type": "input_text", "content": "{{context}}"},
                                    {"type": "image", "url": "https://example.invalid/image.png"},
                                ],
                            },
                            {
                                "role": "assistant",
                                "content": {"type": "markdown", "data": "Ready."},
                            },
                        ]
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "What changed?", "context": "Compatibility expanded."},
        llm_invoker=invoke_llm,
    )

    assert validation.errors == []
    assert requests[0]["messages"] == [
        {"role": "user", "content": "Question: What changed?\nContext: Compatibility expanded."},
        {"role": "assistant", "content": "Ready."},
    ]
    assert result.output["llm_text"] == "ok"


@pytest.mark.asyncio
async def test_minimal_executor_llm_accepts_workflow_generation_parameters() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "prompt_template": "Answer {{message}}",
                        "model_parameters": {
                            "max_tokens": "{{limits.max_tokens}}",
                            "top_p": 0.8,
                            "presence_penalty": 0.1,
                            "frequencyPenalty": 0.2,
                            "stop_sequences": ["END", "{{stop_word}}"],
                        },
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello", "limits": {"max_tokens": 128}, "stop_word": "STOP"},
        llm_invoker=invoke_llm,
    )

    assert requests[0]["max_tokens"] == "128"
    assert requests[0]["top_p"] == 0.8
    assert requests[0]["presence_penalty"] == 0.1
    assert requests[0]["frequency_penalty"] == 0.2
    assert requests[0]["stop"] == ["END", "STOP"]
    assert result.output["llm_text"] == "ok"


@pytest.mark.asyncio
async def test_minimal_executor_llm_accepts_model_nested_generation_parameters() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "prompt_template": "Answer {{message}}",
                        "temperature": 0.2,
                        "model": {
                            "provider": "openai",
                            "name": "gpt-4o-mini",
                            "temperature": 0.9,
                            "completion_params": {
                                "max_tokens": "{{limits.max_tokens}}",
                                "topP": 0.75,
                                "stopSequences": ["DONE"],
                            },
                        },
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "llm", "valid": True}],
        }
    }

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello", "limits": {"max_tokens": 96}},
        llm_invoker=invoke_llm,
    )

    assert requests[0]["model"] == "openai/gpt-4o-mini"
    assert requests[0]["temperature"] == 0.2
    assert requests[0]["max_tokens"] == "96"
    assert requests[0]["top_p"] == 0.75
    assert requests[0]["stop"] == ["DONE"]


@pytest.mark.asyncio
async def test_minimal_executor_runs_parameter_extractor_node_with_llm_invoker() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": '{"topic":"LambChat workflows"}', "model": request.get("model")}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "parameter_extractor",
                    "supported": True,
                    "data": {
                        "query": "Please extract {{message}}",
                        "parameters": [{"name": "topic", "type": "string"}],
                        "output_key": "extracted",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{extracted.topic}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "extract", "valid": True},
                {"id": "e2", "source": "extract", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "LambChat workflows"},
        llm_invoker=invoke_llm,
    )

    assert validation.errors == []
    assert "Extract parameters" in requests[0]["prompt"]
    assert "LambChat workflows" in requests[0]["prompt"]
    assert result.output == {"answer": "LambChat workflows"}
    extractor_event = next(
        event for event in result.events if event["node_id"] == "extract" and event["event_type"] == "node_finished"
    )
    assert extractor_event["payload"]["output"]["extracted"] == {"topic": "LambChat workflows"}


@pytest.mark.asyncio
async def test_minimal_executor_runs_sub_workflow_node_with_guarded_invoker() -> None:
    requests = []

    async def invoke_sub_workflow(request: dict) -> dict:
        requests.append(request)
        return {
            "workflow_id": request["workflow_id"],
            "version_id": "wfv-child",
            "run_id": "wfr-child",
            "status": "succeeded",
            "output": {"answer": f"Child {request['input']['name']}"},
            "events": [{"event_type": "node_finished"}],
        }

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "subflow",
                    "type": "sub_workflow",
                    "supported": True,
                    "data": {
                        "workflow_id": "wf-child",
                        "inputs": {"name": "{{name}}"},
                        "output_key": "child",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{child.answer}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "subflow", "valid": True},
                {"id": "e2", "source": "subflow", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(
        model,
        available_sub_workflow_refs={"wf-child@published"},
    )
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"name": "LambChat"},
        sub_workflow_invoker=invoke_sub_workflow,
    )

    assert validation.errors == []
    assert requests == [{"workflow_id": "wf-child", "version_id": None, "input": {"name": "LambChat"}}]
    assert result.output == {"answer": "Child LambChat"}
    subflow_event = next(
        event
        for event in result.events
        if event["node_id"] == "subflow" and event["event_type"] == "node_finished"
    )
    assert subflow_event["payload"]["output"]["sub_workflow_result"]["run_id"] == "wfr-child"


def test_static_validator_rejects_missing_sub_workflow_reference() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "subflow",
                    "type": "sub_workflow",
                    "supported": True,
                    "data": {"workflow_id": "wf-child"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "subflow", "valid": True}],
        }
    }

    unavailable = MinimalWorkflowExecutor().validate_static(model, available_sub_workflow_refs=set())
    missing_resolver = MinimalWorkflowExecutor().validate_static(model)

    assert unavailable.errors == [
        "workflow_sub_workflow_node_not_allowed:subflow:workflow_sub_workflow_not_available:wf-child"
    ]
    assert missing_resolver.errors == [
        "workflow_sub_workflow_node_not_allowed:subflow:workflow_sub_workflow_refs_unavailable"
    ]


@pytest.mark.asyncio
async def test_minimal_executor_parameter_extractor_preserves_unparseable_text() -> None:
    async def invoke_llm(request: dict) -> dict:
        return {"text": "not json"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "parameter_extractor",
                    "supported": True,
                    "data": {"query": "{{message}}"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello"},
        llm_invoker=invoke_llm,
    )

    assert result.output["parameters"] == {
        "raw_text": "not json",
        "parse_error": "parameter_extractor_json_parse_failed",
    }


@pytest.mark.asyncio
async def test_minimal_executor_parameter_extractor_accepts_variable_selector_alias() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": '{"topic":"invoice"}'}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "parameter_extractor",
                    "supported": True,
                    "data": {
                        "variable_selector": ["payload", "message"],
                        "parameters": [{"name": "topic", "type": "string"}],
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "extract", "valid": True}],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"payload": {"message": "Extract the invoice topic"}},
        llm_invoker=invoke_llm,
    )

    assert validation.errors == []
    assert "Extract the invoice topic" in requests[0]["prompt"]
    assert result.output["parameters"] == {"topic": "invoice"}


@pytest.mark.asyncio
async def test_minimal_executor_runs_question_classifier_branch_with_llm_invoker() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": '{"class":"billing"}'}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "classify",
                    "type": "question_classifier",
                    "supported": True,
                    "data": {
                        "query_variable_selector": ["message"],
                        "classes": [
                            {"id": "billing", "name": "Billing"},
                            {"id": "general", "name": "General"},
                        ],
                        "output_key": "question_class",
                    },
                },
                {"id": "billing", "type": "answer", "supported": True, "data": {"answer": "Billing"}},
                {"id": "general", "type": "answer", "supported": True, "data": {"answer": "General"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "classify", "valid": True},
                {
                    "id": "e2",
                    "source": "classify",
                    "target": "billing",
                    "source_handle": "billing",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "classify",
                    "target": "general",
                    "source_handle": "default",
                    "valid": True,
                },
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model, llm_available=True)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "I need an invoice"},
        llm_invoker=invoke_llm,
    )

    assert validation.errors == []
    assert "Classify the input" in requests[0]["prompt"]
    assert "billing: Billing" in requests[0]["prompt"]
    assert "I need an invoice" in requests[0]["prompt"]
    assert result.output == {"answer": "Billing"}
    classifier_event = next(
        event
        for event in result.events
        if event["node_id"] == "classify" and event["event_type"] == "node_finished"
    )
    assert classifier_event["payload"]["output"]["branch"] == "billing"
    assert classifier_event["payload"]["output"]["question_class"] == "billing"


@pytest.mark.asyncio
async def test_minimal_executor_question_classifier_matches_plain_text_class_name() -> None:
    async def invoke_llm(request: dict) -> dict:
        return {"text": "General"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "classify",
                    "type": "question_classifier",
                    "supported": True,
                    "data": {
                        "query": "{{message}}",
                        "classes": [
                            {"id": "billing", "name": "Billing"},
                            {"id": "general", "name": "General"},
                        ],
                    },
                },
                {"id": "billing", "type": "answer", "supported": True, "data": {"answer": "Billing"}},
                {"id": "general", "type": "answer", "supported": True, "data": {"answer": "General"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "classify", "valid": True},
                {"id": "e2", "source": "classify", "target": "billing", "source_handle": "billing", "valid": True},
                {"id": "e3", "source": "classify", "target": "general", "source_handle": "general", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello"},
        llm_invoker=invoke_llm,
    )

    assert result.output == {"answer": "General"}


@pytest.mark.asyncio
async def test_minimal_executor_question_classifier_accepts_variable_selector_alias() -> None:
    requests = []

    async def invoke_llm(request: dict) -> dict:
        requests.append(request)
        return {"text": "Billing"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "classify",
                    "type": "question_classifier",
                    "supported": True,
                    "data": {
                        "variable_selector": ["payload", "message"],
                        "classes": [
                            {"id": "billing", "name": "Billing"},
                            {"id": "general", "name": "General"},
                        ],
                    },
                },
                {"id": "billing", "type": "answer", "supported": True, "data": {"answer": "Billing"}},
                {"id": "general", "type": "answer", "supported": True, "data": {"answer": "General"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "classify", "valid": True},
                {"id": "e2", "source": "classify", "target": "billing", "source_handle": "billing", "valid": True},
                {"id": "e3", "source": "classify", "target": "general", "source_handle": "default", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"payload": {"message": "Please send the invoice"}},
        llm_invoker=invoke_llm,
    )

    assert "Please send the invoice" in requests[0]["prompt"]
    assert result.output == {"answer": "Billing"}


@pytest.mark.asyncio
async def test_minimal_executor_question_classifier_uses_fallback_for_no_match() -> None:
    async def invoke_llm(request: dict) -> dict:
        return {"text": "unmatched"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "classify",
                    "type": "question_classifier",
                    "supported": True,
                    "data": {
                        "query": "{{message}}",
                        "classes": [{"id": "billing", "name": "Billing"}],
                    },
                },
                {"id": "billing", "type": "answer", "supported": True, "data": {"answer": "Billing"}},
                {"id": "fallback", "type": "answer", "supported": True, "data": {"answer": "Fallback"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "classify", "valid": True},
                {"id": "e2", "source": "classify", "target": "billing", "source_handle": "billing", "valid": True},
                {"id": "e3", "source": "classify", "target": "fallback", "source_handle": "default", "valid": True},
            ],
        }
    }

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"message": "hello"},
        llm_invoker=invoke_llm,
    )

    assert result.output == {"answer": "Fallback"}


def test_static_validator_rejects_http_request_when_policy_disabled() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {"method": "GET", "url": "https://api.example.com/status"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }

    result = MinimalWorkflowExecutor().validate_static(model)

    assert result.runnable is False
    assert "workflow_http_node_not_allowed:http:workflow_http_policy_disabled" in result.errors


@pytest.mark.asyncio
async def test_minimal_executor_pauses_and_resumes_human_approval_node() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "approval",
                    "type": "human_approval",
                    "supported": True,
                    "title": "Manager approval",
                    "data": {
                        "instructions": "Approve {{name}}",
                        "assignee": "manager",
                        "output_key": "manager_approval",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Approved={{manager_approval.approved}} note={{manager_approval.comment}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "approval", "valid": True},
                {"id": "e2", "source": "approval", "target": "answer", "valid": True},
            ],
        }
    }

    validation = MinimalWorkflowExecutor().validate_static(model)
    with pytest.raises(WorkflowExecutionPaused) as exc_info:
        await MinimalWorkflowExecutor().execute_async(model, workflow_input={"name": "LambChat"})

    pause = exc_info.value
    assert validation.errors == []
    assert str(pause) == "workflow_human_approval_paused:approval"
    assert pause.pending_approval["instructions"] == "Approve LambChat"
    assert pause.pause_state["node_id"] == "approval"
    assert pause.events[-1]["event_type"] == "human_approval_required"

    resumed = await MinimalWorkflowExecutor().resume_async(
        model,
        resume_state=pause.pause_state,
        approval_response={"approved": True, "comment": "ship it"},
    )

    assert resumed.output == {"answer": "Approved=True note=ship it"}
    assert [event["event_type"] for event in resumed.events] == [
        "human_approval_resumed",
        "node_finished",
        "node_started",
        "node_finished",
    ]


@pytest.mark.asyncio
async def test_minimal_executor_rejects_human_approval_resume_rejection() -> None:
    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "approval", "type": "human_approval", "supported": True, "data": {}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "approval", "valid": True}],
        }
    }
    with pytest.raises(WorkflowExecutionPaused) as exc_info:
        await MinimalWorkflowExecutor().execute_async(model, workflow_input={})

    with pytest.raises(WorkflowExecutionError, match="workflow_human_approval_rejected:approval") as rejected:
        await MinimalWorkflowExecutor().resume_async(
            model,
            resume_state=exc_info.value.pause_state,
            approval_response={"approved": False},
        )

    assert rejected.value.events[-1]["event_type"] == "node_failed"


@pytest.mark.asyncio
async def test_minimal_executor_runs_http_request_with_allowlist_policy() -> None:
    requests = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {"content-type": "text/plain"}, "body": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "POST",
                        "url": "https://api.example.com/status/{{tenant}}",
                        "headers": {"X-Test": "{{tenant}}"},
                        "body": {"message": "Hello {{name}}"},
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{http.body}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "http", "valid": True},
                {"id": "e2", "source": "http", "target": "answer", "valid": True},
            ],
        }
    }
    policy = build_http_request_policy(
        policy="allowlist",
        allowlist=["api.example.com"],
        timeout_seconds=5,
        max_response_bytes=100,
    )

    validation = MinimalWorkflowExecutor().validate_static(model, http_policy=policy)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={"tenant": "acme", "name": "LambChat"},
        http_policy=policy,
        http_invoker=invoke_http,
    )

    assert validation.errors == []
    assert requests == [
        {
            "method": "POST",
            "url": "https://api.example.com/status/acme",
            "headers": {"X-Test": "acme"},
            "params": {},
            "body": {"message": "Hello LambChat"},
            "timeout_seconds": 5.0,
            "max_response_bytes": 100,
        }
    ]
    assert result.output == {"answer": "ok"}


@pytest.mark.asyncio
async def test_minimal_executor_http_request_accepts_workflow_descriptor_fields() -> None:
    requests = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "ok"}

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "request_method": "POST",
                        "endpoint": "https://api.example.com/search",
                        "header_parameters": [
                            {"name": "X-Tenant", "value": "{{tenant}}"},
                            {"name": "X-Trace", "value_selector": ["trace_id"]},
                        ],
                        "query_parameters": [
                            {"name": "q", "value": "{{message}}"},
                            {"name": "limit", "default": 3},
                        ],
                        "request_body": {
                            "owner": {"value_selector": ["user", "id"]},
                            "mode": "{{mode}}",
                        },
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    validation = MinimalWorkflowExecutor().validate_static(model, http_policy=policy)
    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={
            "tenant": "acme",
            "trace_id": "trace-1",
            "message": "workflow",
            "mode": "debug",
            "user": {"id": "user-1"},
        },
        http_policy=policy,
        http_invoker=invoke_http,
    )

    assert validation.errors == []
    assert requests == [
        {
            "method": "POST",
            "url": "https://api.example.com/search",
            "headers": {"X-Tenant": "acme", "X-Trace": "trace-1"},
            "params": {"q": "workflow", "limit": 3},
            "body": {"owner": "user-1", "mode": "debug"},
            "timeout_seconds": 10.0,
            "max_response_bytes": 65536,
        }
    ]
    assert result.output["http_result"]["body"] == "ok"


@pytest.mark.asyncio
async def test_minimal_executor_http_request_injects_vault_bearer_secret() -> None:
    requests: list[dict] = []
    resolved_refs: list[str] = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "ok"}

    async def resolve_secret(ref: str) -> str | None:
        resolved_refs.append(ref)
        return "vault-token" if ref == "http:http_auth" else None

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "GET",
                        "url": "https://api.example.com/status",
                        "authorization": {"type": "bearer"},
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={},
        http_policy=policy,
        http_invoker=invoke_http,
        credential_secret_resolver=resolve_secret,
    )

    assert resolved_refs == ["http:http_auth"]
    assert requests[0]["headers"] == {"Authorization": "Bearer vault-token"}
    assert result.output["http_result"]["body"] == "ok"
    assert "vault-token" not in repr(result.events)


@pytest.mark.asyncio
async def test_minimal_executor_http_request_injects_explicit_custom_credential_header() -> None:
    requests: list[dict] = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "ok"}

    async def resolve_secret(ref: str) -> str | None:
        return "key-123" if ref == "http-custom" else None

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "GET",
                        "url": "https://api.example.com/status",
                        "credential_ref": "http-custom",
                        "auth": {"header_name": "X-API-Key", "prefix": "Token "},
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={},
        http_policy=policy,
        http_invoker=invoke_http,
        credential_secret_resolver=resolve_secret,
    )

    assert requests[0]["headers"] == {"X-API-Key": "Token key-123"}


@pytest.mark.asyncio
async def test_minimal_executor_http_request_injects_json_credential_payload() -> None:
    requests: list[dict] = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "ok"}

    async def resolve_secret(ref: str) -> str | None:
        if ref == "http-custom":
            return '{"api_key":"key-123","header_name":"X-API-Key","prefix":"Token ","headers":{"X-Tenant":"acme"}}'
        return None

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "GET",
                        "url": "https://api.example.com/status",
                        "credential_ref": "http-custom",
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={},
        http_policy=policy,
        http_invoker=invoke_http,
        credential_secret_resolver=resolve_secret,
    )

    assert requests[0]["headers"] == {
        "X-Tenant": "acme",
        "X-API-Key": "Token key-123",
    }


@pytest.mark.asyncio
async def test_minimal_executor_http_request_does_not_override_explicit_auth_header() -> None:
    requests: list[dict] = []

    async def invoke_http(request: dict) -> dict:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "ok"}

    async def resolve_secret(ref: str) -> str | None:
        return "vault-token"

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "GET",
                        "url": "https://api.example.com/status",
                        "headers": {"Authorization": "Bearer explicit-token"},
                        "authorization": {"type": "bearer"},
                    },
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http", "valid": True}],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={},
        http_policy=policy,
        http_invoker=invoke_http,
        credential_secret_resolver=resolve_secret,
    )

    assert requests[0]["headers"] == {"Authorization": "Bearer explicit-token"}


@pytest.mark.asyncio
async def test_minimal_executor_redacts_sensitive_values_in_debug_events() -> None:
    async def invoke_http(request: dict) -> dict:
        return {
            "status_code": 200,
            "headers": {
                "Authorization": "Bearer response-secret",
                "content-type": "text/plain",
            },
            "body": "ok access_token=response-token",
        }

    model = {
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "POST",
                        "url": "https://api.example.com/status",
                        "headers": {"Authorization": "Bearer request-secret"},
                        "body": {"api_key": "request-key"},
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{http.body}}"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "http", "valid": True},
                {"id": "e2", "source": "http", "target": "answer", "valid": True},
            ],
        }
    }
    policy = build_http_request_policy(policy="allowlist", allowlist=["api.example.com"])

    result = await MinimalWorkflowExecutor().execute_async(
        model,
        workflow_input={},
        http_policy=policy,
        http_invoker=invoke_http,
    )

    assert result.output == {"answer": "ok access_token=response-token"}
    serialized_events = repr(result.events)
    assert "response-secret" not in serialized_events
    assert "response-token" not in serialized_events
    assert "[redacted]" in serialized_events
    http_finished = next(
        event
        for event in result.events
        if event["node_id"] == "http" and event["event_type"] == "node_finished"
    )
    headers = http_finished["payload"]["output"]["http"]["headers"]
    assert headers["Authorization"] == "[redacted]"
    assert headers["content-type"] == "text/plain"

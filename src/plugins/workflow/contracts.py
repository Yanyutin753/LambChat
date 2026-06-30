"""Shared IO contract helpers for workflow callers."""

from __future__ import annotations

from typing import Any


def schema_properties(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def schema_required(schema: Any) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    required = schema.get("required")
    if not isinstance(required, list):
        return set()
    return {str(field) for field in required if field}


def schema_type_name(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        return "|".join(str(item) for item in raw_type if item) or "unknown"
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    if isinstance(schema.get("properties"), dict):
        return "object"
    if isinstance(schema.get("items"), dict):
        return "array"
    return "unknown"


def json_value_matches_schema_type(value: Any, raw_type: Any) -> bool:
    expected_types = raw_type if isinstance(raw_type, list) else [raw_type]
    aliases = {
        "str": "string",
        "text": "string",
        "paragraph": "string",
        "select": "string",
        "email": "string",
        "url": "string",
        "uri": "string",
        "int": "integer",
        "float": "number",
        "double": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "map": "object",
    }
    normalized = {
        aliases.get(str(item).strip().lower(), str(item).strip().lower())
        for item in expected_types
        if item
    }
    if not normalized:
        return True
    return any(
        (expected == "string" and isinstance(value, str))
        or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (
            expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        or (expected == "boolean" and isinstance(value, bool))
        or (expected == "array" and isinstance(value, list))
        or (expected == "object" and isinstance(value, dict))
        or (expected == "null" and value is None)
        for expected in normalized
    )


def _field_path(parent: str, field: str) -> str:
    return f"{parent}.{field}" if parent else field


def workflow_result_interface(
    *,
    workflow_id: Any,
    version_id: Any,
    run_id: Any,
) -> dict[str, Any]:
    return {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": workflow_id,
            "version_id": version_id,
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
            "workflow_id": workflow_id,
            "run_id": run_id,
            "events_field": "events",
        },
    }


def workflow_callable_interface(
    *,
    workflow_id: Any,
    version_id: Any,
    run_id: Any = None,
) -> dict[str, Any]:
    debug: dict[str, Any] = {
        "tool": "workflow_get_run",
        "workflow_id": workflow_id,
        "run_id_field": "run_id",
    }
    if run_id:
        debug["run_id"] = run_id
    return {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": workflow_id,
            "version_id": version_id,
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
            "workflow_id": workflow_id,
            "version_id": version_id,
            "input_schema_field": "input_schema",
            "output_schema_field": "output_schema",
        },
        "run": {
            "tool": "workflow_run",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "input_argument": "input",
            "output_field": "output",
        },
        "debug": debug,
    }


def workflow_next_action(
    *,
    status: Any,
    run_id: Any,
    workflow_id: Any = None,
    pause: Any = None,
) -> dict[str, Any]:
    status_value = str(status or "")
    pause_payload = pause if isinstance(pause, dict) else {}
    if status_value == "paused" and run_id and pause_payload.get("kind") == "human_approval":
        pending_approval = pause_payload.get("pending_approval")
        approval = pending_approval if isinstance(pending_approval, dict) else {}
        workflow_path_id = str(workflow_id or "{workflow_id}")
        return {
            "type": "await_human_approval",
            "tool": "workflow_get_run",
            "reason": "workflow_run_paused_human_approval",
            "field": "pause.pending_approval",
            "approval": {
                "kind": "human_approval",
                "node_id": approval.get("node_id"),
                "title": approval.get("title"),
                "assignee": approval.get("assignee"),
                "output_key": approval.get("output_key"),
            },
            "pending": {
                "method": "GET",
                "path": "/api/plugins/workflow/approvals/pending",
            },
            "resume": {
                "tool": "workflow_resume",
                "method": "POST",
                "path": f"/api/plugins/workflow/workflows/{workflow_path_id}/runs/{run_id}/resume",
                "body": {"approved": True, "comment": "", "values": {}},
                "arguments": {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "approved": True,
                    "comment": "",
                    "values": {},
                },
            },
        }
    if status_value in {"queued", "running", "paused"} and run_id:
        return {
            "type": "inspect_run",
            "tool": "workflow_get_run",
            "reason": f"workflow_run_{status_value}",
        }
    if status_value == "succeeded":
        return {
            "type": "use_output",
            "field": "output",
            "reason": "workflow_run_succeeded",
        }
    if status_value in {"failed", "cancelled"}:
        action: dict[str, Any] = {
            "type": "handle_terminal_error",
            "field": "error",
            "reason": f"workflow_run_{status_value}",
        }
        if run_id:
            action["tool"] = "workflow_get_run"
        return action
    return {
        "type": "inspect_run" if run_id else "read_status",
        "tool": "workflow_get_run" if run_id else None,
        "reason": "workflow_run_status_unknown",
    }


def schema_field_descriptors(schema: Any, *, prefix: str = "") -> list[dict[str, str]]:
    properties = schema_properties(schema)
    required = schema_required(schema)
    ordered_fields = [field for field in sorted(required) if field in properties]
    ordered_fields.extend(
        field for field in sorted(str(field) for field in properties) if field not in ordered_fields
    )
    descriptors: list[dict[str, str]] = []
    for field in ordered_fields:
        raw_schema = properties.get(field)
        field = str(field).strip()
        if not field:
            continue
        child_schema = raw_schema if isinstance(raw_schema, dict) else {}
        field_type = schema_type_name(child_schema)
        path = _field_path(prefix, field)
        if field_type == "object":
            nested = schema_field_descriptors(child_schema, prefix=path)
            descriptors.extend(nested or [{"field": path, "type": field_type}])
            continue
        if field_type == "array":
            item_schema = child_schema.get("items")
            nested = schema_field_descriptors(
                item_schema if isinstance(item_schema, dict) else {},
                prefix=f"{path}[]",
            )
            descriptors.extend(nested or [{"field": path, "type": field_type}])
            continue
        descriptors.append({"field": path, "type": field_type})
    return descriptors


def required_schema_field_paths(schema: Any, *, prefix: str = "") -> list[str]:
    properties = schema_properties(schema)
    required = schema_required(schema)
    paths: list[str] = []
    for field in sorted(required):
        raw_schema = properties.get(field)
        child_schema = raw_schema if isinstance(raw_schema, dict) else {}
        path = _field_path(prefix, field)
        field_type = schema_type_name(child_schema)
        if field_type == "object":
            nested_paths = required_schema_field_paths(child_schema, prefix=path)
            paths.extend(nested_paths or [path])
            continue
        if field_type == "array":
            item_schema = child_schema.get("items")
            nested_paths = required_schema_field_paths(
                item_schema if isinstance(item_schema, dict) else {},
                prefix=f"{path}[]",
            )
            paths.extend(nested_paths or [path])
            continue
        paths.append(path)
    return paths


def _actual_type_name(value: Any) -> str:
    return type(value).__name__


def _schema_enum_values(schema: dict[str, Any]) -> list[Any] | None:
    enum_values = schema.get("enum")
    return enum_values if isinstance(enum_values, list) else None


def _is_present_output_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def workflow_output_path_value(output: dict[str, Any], path: str) -> Any:
    def resolve(current: Any, segments: list[str]) -> Any:
        if not segments:
            return current
        segment = segments[0]
        if segment.endswith("[]"):
            key = segment[:-2]
            if not isinstance(current, dict):
                return None
            items = current.get(key)
            if not isinstance(items, list):
                return None
            for item in items:
                value = resolve(item, segments[1:])
                if _is_present_output_value(value):
                    return value
            return None
        if not isinstance(current, dict):
            return None
        return resolve(current.get(segment), segments[1:])

    if not isinstance(output, dict) or not path:
        return None
    return resolve(output, path.split("."))


def workflow_output_contract_value(output: dict[str, Any], io_contract: Any) -> Any:
    if not isinstance(output, dict):
        return None
    output_schema = io_contract.get("output_schema") if isinstance(io_contract, dict) else None
    for descriptor in schema_field_descriptors(output_schema):
        value = workflow_output_path_value(output, descriptor["field"])
        if _is_present_output_value(value):
            return value
    answer = workflow_output_path_value(output, "answer")
    return answer if _is_present_output_value(answer) else None


def schema_value_mismatches(
    value: Any,
    schema: Any,
    path: str,
    *,
    ignore_required_defaults: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []

    mismatches: list[dict[str, Any]] = []
    expected = schema.get("type")
    if not json_value_matches_schema_type(value, expected):
        return [
            {
                "field": path,
                "expected": expected,
                "actual": _actual_type_name(value),
            }
        ]

    enum_values = _schema_enum_values(schema)
    if enum_values is not None and value not in enum_values:
        mismatches.append(
            {
                "field": path,
                "expected": {"enum": enum_values},
                "actual": value,
            }
        )

    properties = schema_properties(schema)
    required = schema_required(schema)
    if isinstance(value, dict) and (properties or required):
        for field in sorted(required):
            raw_field_schema = properties.get(field)
            field_schema: dict[str, Any] = (
                raw_field_schema if isinstance(raw_field_schema, dict) else {}
            )
            if ignore_required_defaults and "default" in field_schema:
                continue
            if field not in value or value.get(field) is None:
                mismatches.append(
                    {
                        "field": _field_path(path, field),
                        "expected": "required",
                        "actual": "missing",
                    }
                )
        for field, child_schema in properties.items():
            if field not in value or value.get(field) is None:
                continue
            mismatches.extend(
                schema_value_mismatches(
                    value[field],
                    child_schema,
                    _field_path(path, str(field)),
                    ignore_required_defaults=ignore_required_defaults,
                )
            )

    items_schema = schema.get("items")
    if isinstance(value, list) and isinstance(items_schema, dict):
        for index, item in enumerate(value):
            mismatches.extend(
                schema_value_mismatches(
                    item,
                    items_schema,
                    f"{path}[{index}]",
                    ignore_required_defaults=ignore_required_defaults,
                )
            )

    return mismatches


def output_contract_status(
    output: dict[str, Any],
    io_contract: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(io_contract, dict):
        return None
    output_schema = io_contract.get("output_schema")
    properties = schema_properties(output_schema)
    required = schema_required(output_schema)
    descriptors = schema_field_descriptors(output_schema)
    required_field_paths = required_schema_field_paths(output_schema)
    missing_required = sorted(
        field for field in required if field not in output or output.get(field) is None
    )
    type_mismatches: list[dict[str, Any]] = []
    for field, raw_schema in properties.items():
        if field not in output or output.get(field) is None:
            continue
        type_mismatches.extend(schema_value_mismatches(output[field], raw_schema, str(field)))
    extra_fields = sorted(field for field in output if properties and field not in properties)
    return {
        "valid": not missing_required and not type_mismatches,
        "schema_field": "output_schema",
        "declared_fields": sorted(properties),
        "declared_field_paths": [descriptor["field"] for descriptor in descriptors],
        "required_fields": sorted(required),
        "required_field_paths": required_field_paths,
        "missing_required": missing_required,
        "type_mismatches": type_mismatches,
        "extra_fields": extra_fields,
    }


def workflow_output_schema_summary(io_contract: Any) -> str | None:
    if not isinstance(io_contract, dict):
        return None
    output_schema = io_contract.get("output_schema")
    fields = [
        f"{descriptor['field']}:{descriptor['type']}"
        for descriptor in schema_field_descriptors(output_schema)
    ]
    return ", ".join(fields) if fields else None

"""Internal tool stubs for the workflow plugin."""

from __future__ import annotations

import json
import re
import sys
from typing import Annotated, Any, Literal

from langchain.tools import tool
from langchain_core.tools import InjectedToolArg

from src.infra.tool.backend_utils import get_user_id_from_runtime
from src.plugins.workflow.contracts import (
    output_contract_status as _output_contract_status,
)
from src.plugins.workflow.contracts import (
    workflow_callable_interface,
    workflow_result_interface,
)
from src.plugins.workflow.contracts import (
    workflow_next_action as _workflow_next_action,
)
from src.plugins.workflow.service import create_workflow_service
from src.plugins.workflow.user_context import workflow_user_for_user_id

try:
    from langchain.tools import ToolRuntime
except ImportError:  # pragma: no cover
    _mod = type(sys)("langchain.tools")
    _mod.ToolRuntime = Any  # type: ignore[attr-defined]
    sys.modules.setdefault("langchain.tools", _mod)
    from langchain.tools import ToolRuntime


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _event_payload_truncation(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("truncated") is not True
        or payload.get("reason") != "workflow_event_payload_too_large"
    ):
        return None
    keys = payload.get("keys")
    return {
        "reason": "workflow_event_payload_too_large",
        "original_bytes": payload.get("original_bytes"),
        "max_bytes": payload.get("max_bytes"),
        "keys": [key for key in keys if isinstance(key, str)] if isinstance(keys, list) else [],
    }


def _event_payload(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        payload = dict(event)
        truncation = _event_payload_truncation(payload.get("payload"))
        if truncation is not None:
            payload["payload_truncation"] = truncation
        return payload
    model_dump = getattr(event, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        truncation = _event_payload_truncation(
            payload.get("payload") if isinstance(payload, dict) else None
        )
        if truncation is not None:
            payload["payload_truncation"] = truncation
        return payload
    payload = {
        "event_id": getattr(event, "event_id", None),
        "run_id": getattr(event, "run_id", None),
        "workflow_id": getattr(event, "workflow_id", None),
        "version_id": getattr(event, "version_id", None),
        "sequence": getattr(event, "sequence", None),
        "event_type": getattr(event, "event_type", None),
        "node_id": getattr(event, "node_id", None),
        "node_type": getattr(event, "node_type", None),
        "payload": getattr(event, "payload", {}) or {},
        "created_at": getattr(event, "created_at", None),
    }
    truncation = _event_payload_truncation(payload["payload"])
    if truncation is not None:
        payload["payload_truncation"] = truncation
    return payload


def _workflow_list_item_interface(workflow: dict[str, Any]) -> dict[str, Any]:
    workflow_id = workflow.get("workflow_id")
    version_id = workflow.get("published_version_id") or workflow.get("latest_version_id")
    return workflow_callable_interface(workflow_id=workflow_id, version_id=version_id)


def _schema_type(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        return "|".join(str(item) for item in raw_type if item)
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    if isinstance(schema.get("properties"), dict):
        return "object"
    if isinstance(schema.get("items"), dict):
        return "array"
    return "unknown"


def _schema_field_hints(schema: Any, *, prefix: str = "") -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = {str(item) for item in schema.get("required") or [] if item}
    hints: list[dict[str, Any]] = []
    for raw_name, raw_property in properties.items():
        name = str(raw_name)
        if not name:
            continue
        field_path = f"{prefix}.{name}" if prefix else name
        property_schema = raw_property if isinstance(raw_property, dict) else {}
        field_type = _schema_type(property_schema)
        hint: dict[str, Any] = {
            "field": field_path,
            "type": field_type,
            "required": name in required,
        }
        description = property_schema.get("description")
        if isinstance(description, str) and description.strip():
            hint["description"] = description.strip()
        enum_values = property_schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            hint["enum"] = enum_values
        hints.append(hint)
        if field_type == "object":
            hints.extend(_schema_field_hints(property_schema, prefix=field_path))
        elif field_type == "array":
            item_schema = property_schema.get("items")
            if isinstance(item_schema, dict):
                hints.extend(_schema_field_hints(item_schema, prefix=f"{field_path}[]"))
    return hints


def _sample_value_for_schema(schema: Any, *, field_name: str = "value") -> Any:
    if not isinstance(schema, dict):
        return "value"
    if "default" in schema:
        return schema["default"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    field_type = _schema_type(schema).split("|", 1)[0]
    if field_type == "object":
        return _sample_object_for_schema(schema)
    if field_type == "array":
        item_schema = schema.get("items")
        return [_sample_value_for_schema(item_schema, field_name=field_name)]
    if field_type in {"integer", "int"}:
        return 1
    if field_type in {"number", "float"}:
        return 1
    if field_type in {"boolean", "bool"}:
        return True
    normalized = field_name.lower().replace("-", "_")
    if normalized in {
        "message",
        "input",
        "query",
        "prompt",
        "question",
        "topic",
        "text",
        "content",
        "name",
    }:
        return "LambChat"
    return "value"


def _sample_object_for_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    required = {str(item) for item in schema.get("required") or [] if item}
    sample: dict[str, Any] = {}
    for raw_name, raw_property in properties.items():
        name = str(raw_name)
        property_schema = raw_property if isinstance(raw_property, dict) else {}
        if name in required or "default" in property_schema:
            sample[name] = _sample_value_for_schema(property_schema, field_name=name)
    if not sample:
        for raw_name, raw_property in list(properties.items())[:3]:
            name = str(raw_name)
            property_schema = raw_property if isinstance(raw_property, dict) else {}
            sample[name] = _sample_value_for_schema(property_schema, field_name=name)
    return sample


def _payload_with_schema_hints(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    input_schema = result.get("input_schema")
    output_schema = result.get("output_schema")
    if isinstance(input_schema, dict):
        result["input_fields"] = _schema_field_hints(input_schema)
        result["input_example"] = _sample_object_for_schema(input_schema)
    if isinstance(output_schema, dict):
        result["output_fields"] = _schema_field_hints(output_schema)
    return result


def _schema_payload_with_interface(
    payload: dict[str, Any],
    *,
    workflow_id: Any,
    version_id: Any,
) -> dict[str, Any]:
    result = dict(payload)
    resolved_workflow_id = result.get("workflow_id") or workflow_id
    resolved_version_id = result.get("version_id") or version_id
    result.setdefault("workflow_id", resolved_workflow_id)
    if resolved_version_id is not None:
        result.setdefault("version_id", resolved_version_id)
    result["interface"] = workflow_callable_interface(
        workflow_id=resolved_workflow_id,
        version_id=resolved_version_id,
    )
    return result


async def _workflow_io_contract_from_service(
    service: Any,
    *,
    workflow_id: Any,
    owner_user_id: str,
    version_id: Any,
) -> dict[str, Any] | None:
    if not workflow_id:
        return None
    get_io_contract = getattr(service, "get_workflow_io_contract", None)
    if callable(get_io_contract):
        try:
            return await get_io_contract(
                str(workflow_id),
                owner_user_id=owner_user_id,
                version_id=str(version_id) if version_id else None,
            )
        except Exception:  # noqa: BLE001 - contract hints must not mask run results
            return None
    return None


def _run_payload(
    run: Any,
    *,
    events: list[Any] | None = None,
    io_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow_id = getattr(run, "workflow_id", None)
    version_id = getattr(run, "version_id", None)
    run_id = getattr(run, "run_id", None)
    status = getattr(run, "status", None)
    raw_output = getattr(run, "output", {}) or {}
    output_payload = raw_output if isinstance(raw_output, dict) else {}
    payload = {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "run_id": run_id,
        "mode": getattr(run, "mode", None),
        "status": status,
        "output": output_payload,
        "error": getattr(run, "error", None),
        "pause": getattr(run, "pause", {}) or {},
        "started_at": getattr(run, "started_at", None),
        "finished_at": getattr(run, "finished_at", None),
        "interface": workflow_result_interface(
            workflow_id=workflow_id,
            version_id=version_id,
            run_id=run_id,
        ),
        "next_action": _workflow_next_action(
            status=status,
            run_id=run_id,
            workflow_id=workflow_id,
            pause=getattr(run, "pause", {}) or {},
        ),
    }
    if events is not None:
        payload["events"] = [_event_payload(event) for event in events]
    if io_contract is not None:
        payload["io_contract"] = io_contract
        normalized_contract = io_contract if isinstance(io_contract, dict) else {}
        output_contract = _output_contract_status(output_payload, normalized_contract)
        if output_contract is not None:
            payload["output_contract"] = output_contract
    return payload


def _run_error_payload(
    *,
    workflow_id: Any,
    version_id: Any,
    run_id: Any = None,
    mode: Any,
    error: str,
) -> dict[str, Any]:
    return {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "run_id": run_id,
        "mode": mode,
        "status": "failed",
        "output": {},
        "error": error,
        "interface": workflow_result_interface(
            workflow_id=workflow_id,
            version_id=version_id,
            run_id=run_id,
        ),
        "next_action": _workflow_next_action(status="failed", run_id=run_id),
    }


async def _workflow_user_from_runtime(runtime: ToolRuntime | None):
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return None
    return await workflow_user_for_user_id(user_id)


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_SYSTEM_INPUT_ALIASES = {"sys.query": "query", "sys.input": "input"}
_INTERNAL_TEMPLATE_KEYS = {
    "item",
    "iteration_item",
    "index",
    "iteration_index",
}
_NODE_OUTPUT_DEFAULTS: dict[str, set[str]] = {
    "condition": {"branch", "matched"},
    "tool_call": {"tool_result", "tool_name"},
    "knowledge_retrieval": {"knowledge_result"},
    "llm": {"llm_result", "llm_text"},
    "parameter_extractor": {"parameters", "parameter_extractor_text"},
    "question_classifier": {
        "branch",
        "matched",
        "question_class",
        "question_class_name",
        "question_classifier_text",
    },
    "iteration": {"iteration_count"},
    "document_extractor": {"document_text", "document_count"},
}


def _infer_input_schema(internal_model: dict[str, Any]) -> dict[str, Any]:
    graph = internal_model.get("graph") if isinstance(internal_model, dict) else None
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []

    schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": True}
    explicit_schema = _explicit_input_schema_from_start_nodes(nodes)
    if explicit_schema:
        schema.update(explicit_schema)
        schema["type"] = "object"
        schema.setdefault("properties", {})
        schema["additionalProperties"] = explicit_schema.get("additionalProperties", True)

    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        properties = {}
        schema["properties"] = properties
    required = set(str(item) for item in schema.get("required") or [] if item)
    declared_or_produced = set(properties) | _produced_variable_names(nodes)
    inferred: set[str] = set()

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        if node_type == "start":
            continue
        for candidate in _input_candidates_from_value(node.get("data")):
            field = _schema_field_name(candidate)
            if not field or field in declared_or_produced or field in _INTERNAL_TEMPLATE_KEYS:
                continue
            inferred.add(field)

    for field in sorted(inferred):
        properties.setdefault(field, _default_schema_for_field(field, source="inferred"))

    if required:
        schema["required"] = sorted(required)
    elif "required" in schema:
        schema.pop("required", None)
    return schema


def _schema_metadata(internal_model: dict[str, Any]) -> dict[str, Any]:
    graph = internal_model.get("graph") if isinstance(internal_model, dict) else None
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    has_explicit = bool(_explicit_input_schema_from_start_nodes(nodes))
    explicit_properties = set(
        _explicit_input_schema_from_start_nodes(nodes).get("properties") or {}
    )
    inferred = sorted(
        {
            field
            for node in nodes
            if isinstance(node, dict) and str(node.get("type") or "") != "start"
            for field in (
                _schema_field_name(candidate)
                for candidate in _input_candidates_from_value(node.get("data"))
            )
            if field and field not in _INTERNAL_TEMPLATE_KEYS
        }
        - _produced_variable_names(nodes)
        - explicit_properties
    )
    return {
        "schema_source": "declared_and_inferred"
        if has_explicit and inferred
        else "declared"
        if has_explicit
        else "inferred",
        "inferred_fields": inferred,
    }


def infer_workflow_input_schema_payload(
    *,
    workflow_id: str,
    status: str,
    version_id: str,
    version_number: int,
    internal_model: dict[str, Any],
) -> dict[str, Any]:
    schema = _infer_input_schema(internal_model)
    metadata = _schema_metadata(internal_model)
    return {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "version_number": version_number,
        "input_schema": schema,
        "status": status,
        **metadata,
    }


def infer_workflow_output_schema_payload(
    *,
    workflow_id: str,
    status: str,
    version_id: str,
    version_number: int,
    internal_model: dict[str, Any],
) -> dict[str, Any]:
    schema, metadata = _infer_output_schema_with_metadata(internal_model)
    return {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "version_number": version_number,
        "output_schema": schema,
        "status": status,
        **metadata,
    }


def infer_workflow_io_contract_payload(
    *,
    workflow_id: str,
    status: str,
    version_id: str,
    version_number: int,
    internal_model: dict[str, Any],
) -> dict[str, Any]:
    input_payload = infer_workflow_input_schema_payload(
        workflow_id=workflow_id,
        status=status,
        version_id=version_id,
        version_number=version_number,
        internal_model=internal_model,
    )
    output_payload = infer_workflow_output_schema_payload(
        workflow_id=workflow_id,
        status=status,
        version_id=version_id,
        version_number=version_number,
        internal_model=internal_model,
    )
    return {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "version_number": version_number,
        "status": status,
        "input_schema": input_payload["input_schema"],
        "output_schema": output_payload["output_schema"],
        "input_schema_source": input_payload["schema_source"],
        "output_schema_source": output_payload["schema_source"],
        "inferred_input_fields": input_payload["inferred_fields"],
        "inferred_output_fields": output_payload["inferred_fields"],
    }


def _infer_output_schema_with_metadata(
    internal_model: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = internal_model.get("graph") if isinstance(internal_model, dict) else None
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []

    explicit_schema = _explicit_output_schema_from_exit_nodes(nodes)
    if explicit_schema:
        schema = dict(explicit_schema)
        schema["type"] = "object"
        schema.setdefault("properties", {})
        schema.setdefault("additionalProperties", True)
        inferred_fields: list[str] = []
        source = "declared"
    else:
        properties: dict[str, Any] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "")
            raw_data = node.get("data")
            data = raw_data if isinstance(raw_data, dict) else {}
            if node_type == "end":
                properties.update(_end_output_properties(data))
            elif node_type == "answer":
                properties.setdefault(
                    "answer", _default_schema_for_field("answer", source="inferred")
                )
        if not properties:
            properties["output"] = {
                "type": "object",
                "additionalProperties": True,
                "x-lambchat-source": "inferred",
            }
        schema = {"type": "object", "properties": properties, "additionalProperties": True}
        inferred_fields = sorted(properties)
        source = "inferred"

    return schema, {"schema_source": source, "inferred_fields": inferred_fields}


def _explicit_output_schema_from_exit_nodes(nodes: list[Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for node in nodes:
        if not isinstance(node, dict) or str(node.get("type") or "") not in {"answer", "end"}:
            continue
        raw_data = node.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        raw_schema = data.get("output_schema") or data.get("outputSchema") or data.get("schema")
        if isinstance(raw_schema, dict) and (
            raw_schema.get("type") == "object" or isinstance(raw_schema.get("properties"), dict)
        ):
            merged = _merge_schema(merged, raw_schema)
    return merged


def _end_output_properties(data: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for item_data in _end_output_items_from_data(data.get("outputs")):
        name = _end_output_name(item_data)
        if not name:
            continue
        properties[name] = _default_schema_for_field(
            name,
            source="inferred",
            raw_type=(
                item_data.get("type")
                or item_data.get("output_type")
                or item_data.get("outputType")
                or item_data.get("data_type")
                or item_data.get("dataType")
            ),
            description=item_data.get("description") or item_data.get("label"),
            default=item_data.get("default"),
        )
    direct = data.get("output") or data.get("result")
    if isinstance(direct, dict):
        for name, value in direct.items():
            properties[str(name)] = _schema_for_output_value(str(name), value)
    return properties


def _end_output_items_from_data(raw_outputs: Any) -> list[dict[str, Any]]:
    if isinstance(raw_outputs, list):
        return [item for item in raw_outputs if isinstance(item, dict)]
    if isinstance(raw_outputs, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_outputs.items():
            item = dict(raw_item) if isinstance(raw_item, dict) else {"value": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _end_output_name(item_data: dict[str, Any]) -> str:
    return str(
        item_data.get("variable")
        or item_data.get("name")
        or item_data.get("key")
        or item_data.get("output_key")
        or item_data.get("outputKey")
        or ""
    ).strip()


def _schema_for_output_value(name: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        raw_type = "boolean"
    elif isinstance(value, int) and not isinstance(value, bool):
        raw_type = "integer"
    elif isinstance(value, float):
        raw_type = "number"
    elif isinstance(value, list):
        raw_type = "array"
    elif isinstance(value, dict):
        raw_type = "object"
    else:
        raw_type = "string"
    return _default_schema_for_field(name, source="inferred", raw_type=raw_type)


def _explicit_input_schema_from_start_nodes(nodes: list[Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for node in nodes:
        if not isinstance(node, dict) or str(node.get("type") or "") != "start":
            continue
        raw_data = node.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        raw_schema = (
            data.get("input_schema")
            or data.get("inputSchema")
            or data.get("schema")
            or data.get("parameters")
        )
        if isinstance(raw_schema, dict):
            schema = dict(raw_schema)
            if schema.get("type") == "object" or isinstance(schema.get("properties"), dict):
                merged = _merge_schema(merged, schema)
        for raw_variables in (data.get("variables"), data.get("inputs")):
            variables_schema = _schema_from_start_variables(raw_variables)
            if variables_schema:
                merged = _merge_schema(merged, variables_schema)
    return merged


def _merge_schema(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    merged = dict(base)
    properties = dict(merged.get("properties") or {})
    properties.update(incoming.get("properties") or {})
    merged["properties"] = properties
    required = sorted(
        {str(item) for item in (merged.get("required") or []) + (incoming.get("required") or [])}
    )
    if required:
        merged["required"] = required
    if "additionalProperties" in incoming:
        merged["additionalProperties"] = incoming["additionalProperties"]
    return merged


def _schema_from_start_variables(raw_variables: Any) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for item_data in _start_variable_items(raw_variables):
        name = _start_variable_name(item_data)
        if not name:
            continue
        field_schema = _default_schema_for_field(
            name,
            source="declared",
            raw_type=(
                item_data.get("type")
                or item_data.get("input_type")
                or item_data.get("inputType")
                or item_data.get("field_type")
                or item_data.get("fieldType")
                or item_data.get("data_type")
                or item_data.get("dataType")
                or item_data.get("variable_type")
                or item_data.get("variableType")
                or item_data.get("value_type")
                or item_data.get("valueType")
            ),
            description=item_data.get("description") or item_data.get("label"),
            default=_start_variable_default(item_data),
            enum_values=_start_enum_values(item_data),
            constraints=_start_input_constraints(item_data),
        )
        properties[name] = field_schema
        if bool(item_data.get("required")):
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        schema["required"] = sorted(set(required))
    return schema


def _start_variable_items(raw_variables: Any) -> list[dict[str, Any]]:
    if isinstance(raw_variables, list):
        return [item for item in raw_variables if isinstance(item, dict)]
    if isinstance(raw_variables, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_variables.items():
            if isinstance(raw_item, dict):
                item = dict(raw_item)
            else:
                item = {"type": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _default_schema_for_field(
    field: str,
    *,
    source: str,
    raw_type: Any = None,
    description: Any = None,
    default: Any = None,
    enum_values: list[Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema_type = _json_schema_type(raw_type, field=field)
    schema: dict[str, Any] = {"type": schema_type, "x-lambchat-source": source}
    input_kind = _lambchat_input_kind(raw_type)
    if input_kind:
        schema["x-lambchat-input-kind"] = input_kind
        if input_kind == "file" and schema_type == "array":
            schema["items"] = {"type": "object", "additionalProperties": True}
    if isinstance(description, str) and description.strip():
        schema["description"] = description.strip()
    if default is not None:
        schema["default"] = default
    if enum_values:
        schema["enum"] = enum_values
    if constraints:
        schema.update(constraints)
    return schema


def _start_variable_default(item_data: dict[str, Any]) -> Any:
    for key in ("default", "default_value", "defaultValue", "value"):
        if key in item_data:
            return item_data.get(key)
    return None


def _start_enum_values(item_data: dict[str, Any]) -> list[Any]:
    for key in ("enum", "options", "choices", "select_options", "selectOptions"):
        raw_values = item_data.get(key)
        if isinstance(raw_values, list):
            return [_start_option_value(option) for option in raw_values]
    return []


def _start_input_constraints(item_data: dict[str, Any]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for target, keys in {
        "minLength": ("minLength", "min_length"),
        "maxLength": ("maxLength", "max_length"),
        "minimum": ("minimum", "min_value", "minValue"),
        "maximum": ("maximum", "max_value", "maxValue"),
        "exclusiveMinimum": ("exclusiveMinimum", "exclusive_minimum", "exclusiveMinimumValue"),
        "exclusiveMaximum": ("exclusiveMaximum", "exclusive_maximum", "exclusiveMaximumValue"),
        "minItems": ("minItems", "min_items"),
        "maxItems": ("maxItems", "max_items"),
    }.items():
        value = _first_mapping_value(item_data, *keys)
        if value is not None:
            constraints[target] = value
    raw_format = (
        item_data.get("format") or item_data.get("input_format") or item_data.get("inputFormat")
    )
    normalized_format = str(raw_format or item_data.get("type") or "").strip().lower()
    if normalized_format in {"email", "url", "uri"}:
        constraints["format"] = "url" if normalized_format == "uri" else normalized_format
    return constraints


def _first_mapping_value(item_data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item_data:
            return item_data.get(key)
    return None


def _start_variable_name(item_data: dict[str, Any]) -> str:
    return str(
        item_data.get("variable")
        or item_data.get("name")
        or item_data.get("key")
        or item_data.get("field")
        or item_data.get("field_name")
        or item_data.get("fieldName")
        or item_data.get("parameter")
        or item_data.get("parameter_name")
        or item_data.get("parameterName")
        or item_data.get("id")
        or item_data.get("label")
        or ""
    ).strip()


def _start_option_value(option: Any) -> Any:
    if isinstance(option, dict):
        for key in ("value", "name", "label", "key", "id"):
            if key in option:
                return option.get(key)
    return option


def _json_schema_type(raw_type: Any, *, field: str) -> str:
    normalized = str(raw_type or "").strip().lower()
    if normalized in {
        "file",
        "image",
        "audio",
        "video",
        "document",
        "upload",
        "upload_file",
        "file_upload",
    }:
        return "object"
    if normalized in {"files", "file-list", "file_list", "image-list", "image_list", "uploads"}:
        return "array"
    if normalized in {"string", "text", "paragraph", "select", "email", "url"}:
        return "string"
    if normalized in {"number", "float", "double"}:
        return "number"
    if normalized in {"integer", "int"}:
        return "integer"
    if normalized in {"boolean", "bool"}:
        return "boolean"
    if normalized in {"array", "list"}:
        return "array"
    if normalized in {"object", "dict", "map"}:
        return "object"
    if field in {"items", "documents", "dataset_ids"} or field.endswith("_ids"):
        return "array"
    return "string"


def _lambchat_input_kind(raw_type: Any) -> str | None:
    normalized = str(raw_type or "").strip().lower()
    if normalized in {
        "file",
        "files",
        "file-list",
        "file_list",
        "image",
        "image-list",
        "image_list",
        "audio",
        "video",
        "document",
        "upload",
        "uploads",
        "upload_file",
        "file_upload",
    }:
        return "file"
    return None


def _produced_variable_names(nodes: list[Any]) -> set[str]:
    produced: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        node_id = str(node.get("id") or "")
        raw_data = node.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        produced.update(_NODE_OUTPUT_DEFAULTS.get(node_type, set()))
        if node_id and node_type in {
            "llm",
            "parameter_extractor",
            "question_classifier",
            "knowledge_retrieval",
            "http_request",
            "document_extractor",
        }:
            produced.add(node_id)
        output_key = (
            data.get("output_key")
            or data.get("outputKey")
            or data.get("variable")
            or data.get("name")
        )
        if output_key:
            produced.add(str(output_key))
        if node_type == "variable_assign":
            produced.update(_variable_assign_outputs(data))
    return produced


def _variable_assign_outputs(data: dict[str, Any]) -> set[str]:
    outputs: set[str] = set()
    for item in _assignment_items_from_data(data):
        name = _assignment_target_name(item)
        if name:
            outputs.add(name)
    assignments = data.get("assignments")
    if isinstance(assignments, dict):
        outputs.update(str(key) for key in assignments)
    return outputs


def _assignment_items_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in (
        "variables",
        "items",
        "assignments",
        "variable_assignments",
        "variableAssignments",
        "assignment_items",
        "assignmentItems",
    ):
        value = data.get(key)
        if key == "assignments" and isinstance(value, dict):
            continue
        items.extend(_assignment_items(value))
    return items


def _assignment_target_name(item: dict[str, Any]) -> str:
    for key in (
        "variable",
        "name",
        "key",
        "output_key",
        "outputKey",
        "target_variable",
        "targetVariable",
        "assigned_variable",
        "assignedVariable",
        "assigned_variable_selector",
        "assignedVariableSelector",
        "variable_selector",
        "variableSelector",
        "target",
        "selector",
    ):
        value = item.get(key)
        if value in (None, "", [], {}):
            continue
        return _selector_to_key(value) if isinstance(value, list) else str(value)
    return ""


def _assignment_items(raw_items: Any) -> list[dict[str, Any]]:
    if isinstance(raw_items, list):
        return [item for item in raw_items if isinstance(item, dict)]
    if isinstance(raw_items, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_items.items():
            item = dict(raw_item) if isinstance(raw_item, dict) else {"value": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _input_candidates_from_value(value: Any) -> set[str]:
    candidates: set[str] = set()
    if isinstance(value, str):
        candidates.update(_template_variables(value))
        return candidates
    if isinstance(value, list):
        for item in value:
            candidates.update(_input_candidates_from_value(item))
        return candidates
    if not isinstance(value, dict):
        return candidates
    for key, item in value.items():
        if _is_selector_key(str(key)):
            candidates.add(_selector_to_key(item))
        else:
            candidates.update(_input_candidates_from_value(item))
    return candidates


def _template_variables(template: str) -> set[str]:
    result: set[str] = set()
    for match in _TEMPLATE_PATTERN.finditer(template):
        raw = match.group(1).strip().strip("#").strip()
        if not raw:
            continue
        result.add(raw)
    return result


def _is_selector_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized.endswith("selector") or normalized in {
        "variable_selector",
        "variableselector",
        "query_variable_selector",
        "queryvariableselector",
        "iterator_selector",
        "iteratorselector",
        "input_selector",
        "inputselector",
        "selector",
    }


def _selector_to_key(selector: Any) -> str:
    if isinstance(selector, list):
        return ".".join(str(part) for part in selector if part not in (None, ""))
    if isinstance(selector, str):
        return selector.strip()
    return ""


def _schema_field_name(candidate: str) -> str:
    normalized = candidate.replace("#", ".").strip(".").strip()
    normalized = re.sub(r"\[(\d+)\]", r".\1", normalized)
    normalized = _SYSTEM_INPUT_ALIASES.get(normalized, normalized)
    if not normalized:
        return ""
    return normalized.split(".", 1)[0]


@tool("workflow_run")
async def workflow_run(
    workflow_id: Annotated[str, "Workflow id to execute."],
    input: Annotated[dict[str, Any] | None, "Workflow input payload."] = None,
    version_id: Annotated[str | None, "Optional workflow version id."] = None,
    mode: Annotated[Literal["sync", "async", "stream"], "Execution mode."] = "sync",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Execute a published workflow; call workflow_get_schema first to satisfy its input/output contract."""
    user = await _workflow_user_from_runtime(runtime)
    if user is None:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=version_id,
                mode=mode,
                error="No user context available",
            )
        )
    try:
        service = await create_workflow_service()
        run, events = await service.run_workflow(
            workflow_id=workflow_id,
            version_id=version_id,
            workflow_input=input or {},
            mode=mode,
            user=user,
        )
        io_contract = await _workflow_io_contract_from_service(
            service,
            workflow_id=getattr(run, "workflow_id", workflow_id),
            owner_user_id=user.sub,
            version_id=getattr(run, "version_id", version_id),
        )
    except (LookupError, ValueError) as exc:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=version_id,
                mode=mode,
                error=str(exc),
            )
        )
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=version_id,
                mode=mode,
                error=f"workflow_tool_unexpected_error:{exc}",
            )
        )
    return _json(_run_payload(run, events=events, io_contract=io_contract))


@tool("workflow_list")
async def workflow_list(
    scope: Annotated[
        Literal["all", "published", "project", "session"], "Workflow scope."
    ] = "published",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """List visible workflows so an agent can choose the right published workflow before running it."""
    user = await _workflow_user_from_runtime(runtime)
    if user is None:
        return _json({"plugin_id": "workflow", "scope": scope, "workflows": []})
    try:
        service = await create_workflow_service()
        result = await service.list_workflows(owner_user_id=user.sub)
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        return _json(
            {
                "plugin_id": "workflow",
                "scope": scope,
                "status": "failed",
                "workflows": [],
                "error": f"workflow_tool_unexpected_error:{exc}",
            }
        )
    workflows = [workflow.model_dump(mode="json") for workflow in result.workflows]
    if scope == "published":
        workflows = [workflow for workflow in workflows if workflow.get("status") == "published"]
    workflows = [
        {
            **workflow,
            "interface": _workflow_list_item_interface(workflow),
        }
        for workflow in workflows
    ]
    return _json({"plugin_id": "workflow", "scope": scope, "workflows": workflows})


@tool("workflow_get_schema")
async def workflow_get_schema(
    workflow_id: Annotated[str, "Workflow id whose input schema should be returned."],
    version_id: Annotated[
        str | None, "Optional workflow version id whose schema should be returned."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Return the workflow input/output JSON schemas before collecting run arguments."""
    user = await _workflow_user_from_runtime(runtime)
    if user is None:
        return _json(
            _schema_payload_with_interface(
                {
                    "plugin_id": "workflow",
                    "workflow_id": workflow_id,
                    "input_schema": {},
                    "output_schema": {},
                },
                workflow_id=workflow_id,
                version_id=version_id,
            )
        )
    try:
        service = await create_workflow_service()
        get_io_contract = getattr(service, "get_workflow_io_contract", None)
        if callable(get_io_contract):
            payload = await get_io_contract(
                workflow_id, owner_user_id=user.sub, version_id=version_id
            )
        else:
            payload = await service.get_workflow_input_schema(
                workflow_id,
                owner_user_id=user.sub,
                version_id=version_id,
            )
            payload.setdefault("output_schema", {})
    except LookupError as exc:
        error_payload: dict[str, Any] = {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "error": str(exc),
        }
        if version_id is not None:
            error_payload["version_id"] = version_id
        return _json(
            _schema_payload_with_interface(
                error_payload,
                workflow_id=workflow_id,
                version_id=version_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        error_payload = {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "status": "failed",
            "input_schema": {},
            "output_schema": {},
            "error": f"workflow_tool_unexpected_error:{exc}",
        }
        if version_id is not None:
            error_payload["version_id"] = version_id
        return _json(
            _schema_payload_with_interface(
                error_payload,
                workflow_id=workflow_id,
                version_id=version_id,
            )
        )
    return _json(
        _payload_with_schema_hints(
            _schema_payload_with_interface(
                payload,
                workflow_id=workflow_id,
                version_id=version_id,
            )
        )
    )


@tool("workflow_get_run")
async def workflow_get_run(
    workflow_id: Annotated[str, "Workflow id that owns the run."],
    run_id: Annotated[str, "Workflow run id to inspect."],
    skip: Annotated[int, "Number of debug events to skip."] = 0,
    limit: Annotated[int, "Maximum debug events to return."] = 200,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Inspect a workflow run by run_id, including async/stream status, output, errors, and debug events."""
    user = await _workflow_user_from_runtime(runtime)
    if user is None:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error="No user context available",
            )
        )
    try:
        service = await create_workflow_service()
        run, events = await service.list_run_events(
            workflow_id=workflow_id,
            run_id=run_id,
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )
        io_contract = await _workflow_io_contract_from_service(
            service,
            workflow_id=getattr(run, "workflow_id", workflow_id),
            owner_user_id=user.sub,
            version_id=getattr(run, "version_id", None),
        )
    except LookupError as exc:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error=str(exc),
            )
        )
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error=f"workflow_tool_unexpected_error:{exc}",
            )
        )
    return _json(
        {
            **_run_payload(run, events=events, io_contract=io_contract),
            "skip": skip,
            "limit": limit,
        }
    )


@tool("workflow_resume")
async def workflow_resume(
    workflow_id: Annotated[str, "Workflow id that owns the paused run."],
    run_id: Annotated[str, "Paused workflow run id to resume."],
    approved: Annotated[bool, "Whether the human approval decision approved the run."] = True,
    comment: Annotated[str | None, "Optional approval comment."] = None,
    values: Annotated[
        dict[str, Any] | None, "Optional approval values merged into the approval output."
    ] = None,
    response: Annotated[
        dict[str, Any] | None, "Optional structured approval response payload."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Resume a paused workflow run after a human approval decision."""
    user = await _workflow_user_from_runtime(runtime)
    if user is None:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error="No user context available",
            )
        )
    try:
        service = await create_workflow_service()
        run, events = await service.resume_run(
            workflow_id=workflow_id,
            run_id=run_id,
            approval_response={
                "approved": approved,
                "comment": comment,
                "values": values or {},
                "response": response or {},
            },
            user=user,
        )
        io_contract = await _workflow_io_contract_from_service(
            service,
            workflow_id=getattr(run, "workflow_id", workflow_id),
            owner_user_id=user.sub,
            version_id=getattr(run, "version_id", None),
        )
    except (LookupError, ValueError) as exc:
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error=str(exc),
            )
        )
    except Exception as exc:  # noqa: BLE001 - tool results should not crash agent execution
        return _json(
            _run_error_payload(
                workflow_id=workflow_id,
                version_id=None,
                run_id=run_id,
                mode=None,
                error=f"workflow_tool_unexpected_error:{exc}",
            )
        )
    return _json(_run_payload(run, events=events, io_contract=io_contract))


def get_workflow_tools():
    """Return internal tools contributed by the workflow plugin."""
    return [workflow_run, workflow_list, workflow_get_schema, workflow_get_run, workflow_resume]


__all__ = [
    "get_workflow_tools",
    "workflow_get_run",
    "workflow_resume",
    "infer_workflow_io_contract_payload",
    "infer_workflow_input_schema_payload",
    "infer_workflow_output_schema_payload",
    "workflow_get_schema",
    "workflow_list",
    "workflow_run",
]

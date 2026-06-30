"""Chat/agent integration helpers for selected workflows."""

from __future__ import annotations

import json
import re
from typing import Any

from src.kernel.extensions.plugin_options import plugin_option_from_metadata
from src.kernel.schemas.user import TokenPayload
from src.plugins.workflow.contracts import (
    output_contract_status,
    workflow_next_action,
    workflow_output_contract_value,
    workflow_output_schema_summary,
    workflow_result_interface,
)
from src.plugins.workflow.service import WorkflowPluginService, create_workflow_service
from src.plugins.workflow.user_context import workflow_user_for_user_id

PLUGIN_ID = "workflow"
SESSION_WORKFLOW_OPTION = "SELECTED_WORKFLOW_ID"
SESSION_WORKFLOW_VERSION_OPTION = "SELECTED_WORKFLOW_VERSION_ID"
SESSION_WORKFLOW_INPUT_OPTION = "SELECTED_WORKFLOW_INPUT_JSON"
SCHEDULED_TASK_WORKFLOW_OPTION = "WORKFLOW_ID"
SCHEDULED_TASK_WORKFLOW_VERSION_OPTION = "WORKFLOW_VERSION_ID"
SCHEDULED_TASK_WORKFLOW_INPUT_OPTION = "WORKFLOW_INPUT_JSON"
_SAFE_WORKFLOW_ERROR_PATTERN = re.compile(r"^workflow_[a-z0-9_:-]+$")
_GENERIC_PRE_RUN_ERROR = "workflow_pre_run_failed"
_MAX_WORKFLOW_CONTEXT_VALUE_CHARS = 2000


def selected_workflow_id_from_plugin_options(
    plugin_options: dict[str, dict[str, Any]] | None,
) -> str | None:
    return _first_non_empty_plugin_option(
        plugin_options,
        SESSION_WORKFLOW_OPTION,
        SCHEDULED_TASK_WORKFLOW_OPTION,
    )


def selected_workflow_version_id_from_plugin_options(
    plugin_options: dict[str, dict[str, Any]] | None,
) -> str | None:
    metadata = {"plugin_options": plugin_options or {}}
    session_workflow_id = _non_empty_plugin_option(metadata, SESSION_WORKFLOW_OPTION)
    if session_workflow_id:
        return _non_empty_plugin_option(metadata, SESSION_WORKFLOW_VERSION_OPTION)
    scheduled_task_workflow_id = _non_empty_plugin_option(metadata, SCHEDULED_TASK_WORKFLOW_OPTION)
    if scheduled_task_workflow_id:
        return _non_empty_plugin_option(metadata, SCHEDULED_TASK_WORKFLOW_VERSION_OPTION)
    return _first_non_empty_plugin_option(
        plugin_options,
        SESSION_WORKFLOW_VERSION_OPTION,
        SCHEDULED_TASK_WORKFLOW_VERSION_OPTION,
    )


def _first_non_empty_plugin_option(
    plugin_options: dict[str, dict[str, Any]] | None,
    *keys: str,
) -> str | None:
    metadata = {"plugin_options": plugin_options or {}}
    for key in keys:
        selected = _non_empty_plugin_option(metadata, key)
        if selected:
            return selected
    return None


def _non_empty_plugin_option(metadata: dict[str, Any], key: str) -> str | None:
    selected = plugin_option_from_metadata(metadata, plugin_id=PLUGIN_ID, key=key)
    if isinstance(selected, str) and selected.strip():
        return selected.strip()
    return None


async def run_selected_workflow_for_message(
    *,
    plugin_options: dict[str, dict[str, Any]] | None,
    message: str,
    user_id: str,
) -> dict[str, Any] | None:
    workflow_id = selected_workflow_id_from_plugin_options(plugin_options)
    if not workflow_id:
        return None
    version_id = selected_workflow_version_id_from_plugin_options(plugin_options)
    try:
        user = await workflow_user_for_user_id(user_id)
        service = await create_workflow_service()
        workflow_input = await _workflow_input_for_message(
            service=service,
            workflow_id=workflow_id,
            version_id=version_id,
            message=message,
            user=user,
        )
        workflow_input.update(workflow_input_from_plugin_options(plugin_options))
        run, _events = await service.run_workflow(
            workflow_id=workflow_id,
            version_id=version_id,
            workflow_input=workflow_input,
            mode="sync",
            user=user,
        )
        io_contract = await _workflow_io_contract_for_run(
            service=service,
            workflow_id=workflow_id,
            version_id=getattr(run, "version_id", None) or version_id,
            owner_user_id=user.sub,
        )
    except Exception as exc:
        return {
            "plugin_id": PLUGIN_ID,
            "workflow_id": workflow_id,
            "run_id": None,
            "version_id": version_id,
            "status": "failed",
            "output": {},
            "error": safe_workflow_pre_run_error(exc),
            "interface": workflow_result_interface(
                workflow_id=workflow_id,
                version_id=version_id,
                run_id=None,
            ),
            "next_action": workflow_next_action(status="failed", run_id=None),
        }
    output = run.output if isinstance(run.output, dict) else {}
    result = {
        "plugin_id": PLUGIN_ID,
        "workflow_id": workflow_id,
        "run_id": run.run_id,
        "version_id": run.version_id,
        "status": run.status,
        "output": output,
        "error": run.error,
        "pause": getattr(run, "pause", {}) if isinstance(getattr(run, "pause", {}), dict) else {},
        "interface": workflow_result_interface(
            workflow_id=workflow_id,
            version_id=run.version_id,
            run_id=run.run_id,
        ),
        "next_action": workflow_next_action(
            status=run.status,
            run_id=run.run_id,
            workflow_id=workflow_id,
            pause=getattr(run, "pause", {}) if isinstance(getattr(run, "pause", {}), dict) else {},
        ),
    }
    if io_contract is not None:
        result["io_contract"] = io_contract
        output_contract = output_contract_status(output, io_contract)
        if output_contract is not None:
            result["output_contract"] = output_contract
    return result


async def _workflow_io_contract_for_run(
    *,
    service: WorkflowPluginService,
    workflow_id: str,
    version_id: str | None,
    owner_user_id: str,
) -> dict[str, Any] | None:
    get_io_contract = getattr(service, "get_workflow_io_contract", None)
    if not callable(get_io_contract):
        return None
    try:
        contract = await get_io_contract(
            workflow_id,
            owner_user_id=owner_user_id,
            version_id=version_id,
        )
    except Exception:  # noqa: BLE001 - contract hints must not mask chat results
        return None
    return contract if isinstance(contract, dict) else None


async def _workflow_input_for_message(
    *,
    service: WorkflowPluginService,
    workflow_id: str,
    version_id: str | None,
    message: str,
    user: TokenPayload,
) -> dict[str, Any]:
    workflow_input = _base_message_input(message)
    try:
        schema_payload = await service.get_workflow_input_schema(
            workflow_id,
            owner_user_id=user.sub,
            version_id=version_id,
        )
    except Exception:
        return workflow_input
    schema = schema_payload.get("input_schema") if isinstance(schema_payload, dict) else None
    if not isinstance(schema, dict):
        return workflow_input
    for field, value in _message_input_patch_for_schema(schema, message).items():
        workflow_input.setdefault(field, value)
    return workflow_input


def _message_input_patch_for_schema(schema: dict[str, Any], message: str) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    required = {str(item) for item in schema.get("required") or [] if item}
    patch: dict[str, Any] = {}
    for field, raw_property in properties.items():
        field_name = str(field).strip()
        if not field_name:
            continue
        property_schema = raw_property if isinstance(raw_property, dict) else {}
        value = _message_input_value_for_schema_field(
            field_name=field_name,
            property_schema=property_schema,
            required=required,
            message=message,
        )
        if value is not _MISSING:
            patch[field_name] = value
    return patch


_MISSING = object()


def _message_input_value_for_schema_field(
    *,
    field_name: str,
    property_schema: dict[str, Any],
    required: set[str],
    message: str,
) -> Any:
    if _should_fill_message_field(field_name, property_schema, required):
        return message
    schema_type = str(property_schema.get("type") or "").lower()
    if _is_file_input_schema(property_schema):
        return _MISSING
    if schema_type == "object" or isinstance(property_schema.get("properties"), dict):
        child_patch = _message_input_patch_for_schema(property_schema, message)
        if field_name in required:
            return child_patch
    if schema_type == "array":
        items = property_schema.get("items")
        if not isinstance(items, dict) or field_name not in required:
            return _MISSING
        item_type = str(items.get("type") or "").lower()
        if _is_file_input_schema(items):
            return _MISSING
        if _should_fill_message_field(field_name, items, {field_name}) or item_type in {
            "string",
            "unknown",
            "",
        }:
            return [message]
        if item_type == "object" or isinstance(items.get("properties"), dict):
            child_patch = _message_input_patch_for_schema(items, message)
            if child_patch:
                return [child_patch]
    return _MISSING


def scheduled_workflow_input_from_plugin_options(
    plugin_options: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    return _workflow_input_option_payload(plugin_options, SCHEDULED_TASK_WORKFLOW_INPUT_OPTION)


def session_workflow_input_from_plugin_options(
    plugin_options: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    return _workflow_input_option_payload(plugin_options, SESSION_WORKFLOW_INPUT_OPTION)


def workflow_input_from_plugin_options(
    plugin_options: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    metadata = {"plugin_options": plugin_options or {}}
    if _non_empty_plugin_option(metadata, SESSION_WORKFLOW_OPTION):
        return session_workflow_input_from_plugin_options(plugin_options)
    if _non_empty_plugin_option(metadata, SCHEDULED_TASK_WORKFLOW_OPTION):
        return scheduled_workflow_input_from_plugin_options(plugin_options)
    session_input = session_workflow_input_from_plugin_options(plugin_options)
    return session_input or scheduled_workflow_input_from_plugin_options(plugin_options)


def _workflow_input_option_payload(
    plugin_options: dict[str, dict[str, Any]] | None,
    key: str,
) -> dict[str, Any]:
    raw_value = (plugin_options or {}).get(PLUGIN_ID, {}).get(key)
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _base_message_input(message: str) -> dict[str, Any]:
    return {
        "message": message,
        "input": message,
        "query": message,
        "sys.query": message,
        "sys": {"query": message},
    }


def _should_fill_message_field(
    field_name: str,
    property_schema: dict[str, Any],
    required: set[str],
) -> bool:
    normalized = field_name.lower().replace("-", "_").strip()
    if normalized in {"message", "input", "query"}:
        return False
    schema_type = str(property_schema.get("type") or "string").lower()
    if schema_type not in {"string", "unknown", ""}:
        return False
    input_kind = str(property_schema.get("x-lambchat-input-kind") or "").lower()
    if input_kind in {"file", "files"}:
        return False
    if field_name in required:
        return True
    return normalized in {
        "prompt",
        "question",
        "topic",
        "text",
        "content",
        "name",
        "user_message",
        "user_input",
    }


def _is_file_input_schema(property_schema: dict[str, Any]) -> bool:
    input_kind = str(property_schema.get("x-lambchat-input-kind") or "").lower()
    return input_kind in {"file", "files"}


def safe_workflow_pre_run_error(exc: Exception) -> str:
    message = str(exc).strip()
    if _SAFE_WORKFLOW_ERROR_PATTERN.fullmatch(message):
        return message
    return _GENERIC_PRE_RUN_ERROR


def workflow_result_context(result: dict[str, Any]) -> str:
    raw_output = result.get("output")
    output = raw_output if isinstance(raw_output, dict) else {}
    raw_io_contract = result.get("io_contract")
    io_contract = raw_io_contract if isinstance(raw_io_contract, dict) else {}
    contract_value = workflow_output_contract_value(output, io_contract)
    if contract_value not in (None, ""):
        rendered = _bounded_context_value(contract_value)
    else:
        rendered = _bounded_context_value(output or {})
    lines = [
        "Workflow pre-run result:",
        f"workflow_id: {result.get('workflow_id')}",
        f"run_id: {result.get('run_id')}",
        f"status: {result.get('status')}",
        f"output: {rendered}",
    ]
    error = result.get("error")
    if error not in (None, ""):
        lines.append(f"error: {_bounded_context_value(error)}")
    output_schema_summary = workflow_output_schema_summary(result.get("io_contract"))
    if output_schema_summary:
        lines.append(f"outputs: {output_schema_summary}")
    output_contract = result.get("output_contract")
    if isinstance(output_contract, dict):
        valid = "valid" if output_contract.get("valid") else "invalid"
        lines.append(f"output_contract: {valid}")
        missing_required = output_contract.get("missing_required")
        if isinstance(missing_required, list) and missing_required:
            lines.append(f"missing_required_outputs: {_bounded_context_value(missing_required)}")
        type_mismatches = output_contract.get("type_mismatches")
        if isinstance(type_mismatches, list) and type_mismatches:
            lines.append(f"type_mismatched_outputs: {_bounded_context_value(type_mismatches)}")
    interface = result.get("interface")
    if isinstance(interface, dict):
        entry = interface.get("entry")
        exit_ = interface.get("exit")
        if isinstance(entry, dict) and isinstance(exit_, dict):
            interface_parts = [
                f"entry={entry.get('tool')}.{entry.get('argument')}",
                f"schema={entry.get('schema_tool')}.{entry.get('schema_field')}",
                f"exit={exit_.get('field')}",
            ]
            if exit_.get("schema_tool") and exit_.get("schema_field"):
                interface_parts.append(
                    f"output_schema={exit_.get('schema_tool')}.{exit_.get('schema_field')}"
                )
            lines.append("interface: " + " ".join(interface_parts))
    next_action_lines = workflow_next_action_context_lines(result.get("next_action"))
    lines.extend(next_action_lines)
    if result.get("run_id"):
        lines.append("debug: use workflow_get_run with workflow_id and run_id to inspect events")
    return "\n".join(lines)


def workflow_next_action_context_lines(next_action: Any) -> list[str]:
    if not isinstance(next_action, dict):
        return []
    action_type = _context_text(next_action.get("type"))
    reason = _context_text(next_action.get("reason"))
    if not action_type:
        return []
    parts = [action_type]
    if reason:
        parts.append(f"reason={reason}")
    field = _context_text(next_action.get("field"))
    if field:
        parts.append(f"field={field}")
    tool = _context_text(next_action.get("tool"))
    if tool:
        parts.append(f"tool={tool}")
    lines = ["next_action: " + " ".join(parts)]
    resume = next_action.get("resume")
    if isinstance(resume, dict):
        resume_tool = _context_text(resume.get("tool"))
        arguments = resume.get("arguments")
        if resume_tool and isinstance(arguments, dict):
            workflow_id = _context_text(arguments.get("workflow_id")) or "{workflow_id}"
            run_id = _context_text(arguments.get("run_id")) or "{run_id}"
            lines.append(f"resume: {resume_tool}(workflow_id={workflow_id}, run_id={run_id})")
    elif action_type == "inspect_run" and tool:
        lines.append(f"inspect: {tool}")
    return lines


def _context_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _bounded_context_value(value: Any) -> str:
    text = str(value)
    if len(text) <= _MAX_WORKFLOW_CONTEXT_VALUE_CHARS:
        return text
    omitted = len(text) - _MAX_WORKFLOW_CONTEXT_VALUE_CHARS
    return f"{text[:_MAX_WORKFLOW_CONTEXT_VALUE_CHARS]}... [truncated {omitted} chars]"

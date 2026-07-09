"""Registry for LambChat internal tools exposed through the MCP UI."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from types import SimpleNamespace, UnionType
from typing import Any, Literal, Optional, Union, cast, get_args, get_origin

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from src.infra.mcp.storage import MCPStorage
from src.infra.role.storage import RoleStorage
from src.infra.tool.audio_transcribe_tool import get_audio_transcribe_tool
from src.infra.tool.env_var_tool import get_env_var_tools
from src.infra.tool.image_analysis_tool import get_image_analysis_tool
from src.infra.tool.image_generation_tool import (
    get_image_generation_tool,
    get_reference_image_generation_tool,
)
from src.infra.tool.mcp_client import MCPToolWithRetry
from src.infra.tool.persona_preset_tool import get_persona_preset_tools
from src.infra.tool.scheduled_task import get_scheduled_task_tools
from src.kernel.config import settings
from src.kernel.extensions import PluginRuntime, PluginUnavailableError
from src.kernel.extensions.module_loader import load_plugin_attr
from src.kernel.schemas.mcp import (
    MCPServerResponse,
    MCPToolInfo,
    MCPToolPolicy,
    MCPTransport,
)
from src.kernel.types import Permission
from src.plugins.feedback.tools import get_feedback_tools

INTERNAL_MCP_SERVER_NAME = "lambchat_internal"

_SCHEDULED_TASK_TOOL_PERMISSIONS = {
    "scheduled_task_create": Permission.SCHEDULED_TASK_WRITE.value,
    "scheduled_task_list": Permission.SCHEDULED_TASK_READ.value,
    "scheduled_task_update": Permission.SCHEDULED_TASK_WRITE.value,
    "scheduled_task_delete": Permission.SCHEDULED_TASK_DELETE.value,
}

_plugin_runtime: PluginRuntime | None = None


def _declared_builtin_plugin_tool_names() -> set[str]:
    """Return built-in plugin tool names without requiring an active runtime."""
    from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS

    names: set[str] = set()
    for manifest in BUILTIN_PLUGIN_MANIFESTS:
        for tool in manifest.tools:
            names.add(tool.name)
            names.update(tool.legacy_ids)
    return names


def set_plugin_runtime(runtime: PluginRuntime | None) -> None:
    """Attach the active Plugin Runtime used to guard plugin-owned tools."""
    global _plugin_runtime
    _plugin_runtime = runtime


def _plugin_tool_error(tool_name: str) -> str | None:
    runtime = _plugin_runtime
    if runtime is None:
        if tool_name in _declared_builtin_plugin_tool_names():
            return f"[Plugin Tool Error] {tool_name} unavailable: Plugin Runtime is unavailable"
        return None
    registrations = runtime.tools(enabled_only=False)
    if not any(
        registration.name == tool_name or tool_name in registration.legacy_ids
        for registration in registrations
    ):
        return None
    try:
        runtime.ensure_tool_available(tool_name)
    except PluginUnavailableError as exc:
        return f"[Plugin Tool Error] {tool_name} unavailable: {exc}"
    return None


def _is_plugin_tool_exposed(tool_name: str) -> bool:
    return _plugin_tool_error(tool_name) is None


class PluginRuntimeToolGuard(BaseTool):
    """Guard a plugin-owned internal tool immediately before execution."""

    _original_tool: BaseTool = PrivateAttr()

    def __init__(self, original_tool: BaseTool) -> None:
        super().__init__(
            name=original_tool.name,
            description=original_tool.description,
            args_schema=original_tool.args_schema,
        )
        self._original_tool = original_tool

    def _run(self, *args, **kwargs) -> Any:
        error = _plugin_tool_error(self.name)
        if error is not None:
            return error
        return self._original_tool._run(*args, **kwargs)

    async def _arun(self, *args, config: RunnableConfig, **kwargs) -> Any:
        error = _plugin_tool_error(self.name)
        if error is not None:
            return error
        if _tool_accepts_runtime(self._original_tool) and kwargs.get("runtime") is None:
            runtime = _tool_runtime_from_config(config)
            if runtime is not None:
                kwargs["runtime"] = runtime
        return await self._original_tool._arun(*args, config=config, **kwargs)


def _tool_accepts_runtime(tool: BaseTool) -> bool:
    args_schema = getattr(tool, "args_schema", None)
    model_fields = getattr(args_schema, "model_fields", None)
    if isinstance(model_fields, dict):
        return "runtime" in model_fields
    fields = getattr(args_schema, "__fields__", None)
    if isinstance(fields, dict) and "runtime" in fields:
        return True
    for callable_attr in ("coroutine", "func"):
        candidate = getattr(tool, callable_attr, None)
        if not callable(candidate):
            continue
        try:
            if "runtime" in inspect.signature(candidate).parameters:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _tool_runtime_from_config(config: Optional[RunnableConfig]) -> Any:
    try:
        from langchain.tools import ToolRuntime
    except Exception:
        return None

    runtime_config = cast(RunnableConfig, dict(config or {}))
    configurable = runtime_config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        runtime_config["configurable"] = configurable
    context = configurable.get("context")
    if context is None and configurable.get("user_id"):
        context = SimpleNamespace(user_id=str(configurable.get("user_id")))
        configurable["context"] = context
    if context is None:
        context = SimpleNamespace()

    def _stream_writer(_: Any) -> None:
        return None

    try:
        return ToolRuntime(
            state={},
            context=context,
            config=runtime_config,
            stream_writer=_stream_writer,
            tool_call_id=None,
            store=None,
            tools=[],
        )
    except TypeError:
        return SimpleNamespace(config=runtime_config, context=context)


def _coerce_plugin_tools(value: Any) -> list[BaseTool]:
    if isinstance(value, BaseTool):
        return [value]
    if callable(value):
        return _coerce_plugin_tools(value())
    if isinstance(value, (list, tuple)):
        return [tool for tool in value if isinstance(tool, BaseTool)]
    return []


def _build_plugin_internal_tools() -> list[BaseTool]:
    runtime = _plugin_runtime
    if runtime is None:
        return []

    tools: list[BaseTool] = []
    seen_modules: set[tuple[str, str]] = set()
    seen_tools: set[str] = set()
    for registration in runtime.tools(enabled_only=True):
        state = runtime.get_state(registration.plugin_id)
        manifest = state.manifest if state else None
        if manifest is None:
            continue
        module_key = (registration.plugin_id, registration.module)
        if module_key in seen_modules:
            continue
        seen_modules.add(module_key)
        try:
            plugin_tools = _coerce_plugin_tools(load_plugin_attr(manifest, registration.module))
        except Exception as exc:
            runtime.mark_error(
                registration.plugin_id,
                code="tool_registration_failed",
                message=str(exc) or exc.__class__.__name__,
                phase="tool_registration",
            )
            continue
        for tool in plugin_tools:
            if tool.name in seen_tools:
                continue
            seen_tools.add(tool.name)
            tools.append(tool)
    return tools


def build_internal_tools() -> list[BaseTool]:
    """Build the internal tool set that LambChat exposes to agents."""
    from src.infra.logging import get_logger

    logger = get_logger(__name__)
    tools: list[BaseTool] = []

    tools.append(get_image_generation_tool())
    tools.append(get_reference_image_generation_tool())
    if settings.ENABLE_IMAGE_ANALYSIS:
        tools.append(get_image_analysis_tool())
    tools.append(get_audio_transcribe_tool())

    if settings.ENABLE_SCHEDULED_TASK:
        try:
            scheduled_tools = get_scheduled_task_tools()
            tools.extend(scheduled_tools)
            logger.info(
                "[InternalRegistry] ENABLE_SCHEDULED_TASK=True, added %d scheduled task tools: %s",
                len(scheduled_tools),
                [t.name for t in scheduled_tools],
            )
        except Exception as e:
            logger.error(
                "[InternalRegistry] Failed to load scheduled task tools: %s", e, exc_info=True
            )
    else:
        logger.info("[InternalRegistry] ENABLE_SCHEDULED_TASK=False, skipping scheduled task tools")

    tools.extend(get_env_var_tools())
    tools.extend(get_feedback_tools())
    tools.extend(get_persona_preset_tools())
    tools.extend(_build_plugin_internal_tools())

    logger.info(
        "[InternalRegistry] Total %d internal tools built: %s",
        len(tools),
        [t.name for t in tools],
    )
    return tools


def build_internal_server_response() -> MCPServerResponse:
    """Build the virtual server row for the /mcp UI."""
    return MCPServerResponse(
        name=INTERNAL_MCP_SERVER_NAME,
        transport=MCPTransport.SANDBOX,
        enabled=True,
        url=None,
        headers=None,
        command=None,
        env_keys=None,
        is_system=True,
        is_internal=True,
        can_edit=True,
        allowed_roles=[],
        role_quotas={},
        created_at=None,
        updated_at=None,
    )


def _policy_for_tool(
    policies: Mapping[str, MCPToolPolicy],
    tool_name: str,
) -> MCPToolPolicy | None:
    policy = policies.get(tool_name)
    return policy if policy is not None else None


def _is_tool_allowed(
    *,
    policy: MCPToolPolicy | None,
    user_roles: list[str] | None,
    is_admin: bool,
) -> bool:
    if is_admin:
        return True
    if policy is None:
        return True
    if policy.disabled:
        return False
    if not policy.allowed_roles:
        return True
    return bool(set(user_roles or []).intersection(policy.allowed_roles))


async def _resolve_permissions_for_roles(user_roles: list[str] | None) -> set[str]:
    if not user_roles:
        return set()

    storage = RoleStorage()
    permissions: set[str] = set()
    for role_name in user_roles:
        try:
            role = await storage.get_by_name(role_name)
        except Exception:
            continue
        if not role:
            continue
        for permission in role.permissions:
            permissions.add(permission if isinstance(permission, str) else permission.value)
    return permissions


def _is_tool_allowed_by_business_permission(
    tool_name: str,
    *,
    user_permissions: set[str],
) -> bool:
    required_permission = _SCHEDULED_TASK_TOOL_PERMISSIONS.get(tool_name)
    if required_permission is None:
        return True
    return required_permission in user_permissions


def _schema_type_from_annotation(annotation: Any) -> str:
    origin = get_origin(annotation)
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if origin is Literal:
        return _schema_type_from_annotation(args[0]) if args else "string"
    if str(origin) == "typing.Annotated" and args:
        return _schema_type_from_annotation(args[0])
    if origin in (Union, UnionType) and args:
        return _schema_type_from_annotation(args[0])
    if origin is not None and args:
        if origin in (list, tuple, set):
            return "array"
        if origin in (dict, Mapping):
            return "object"
        return _schema_type_from_annotation(args[0])
    if annotation in (list, tuple, set):
        return "array"
    if annotation in (dict, Mapping):
        return "object"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is dict:
        return "object"
    return "string"


def _schema_from_annotation(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    raw_args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if origin is Literal:
        values = list(raw_args)
        return {"type": _schema_type_from_annotation(values[0] if values else str), "enum": values}
    if str(origin) == "typing.Annotated" and raw_args:
        return _schema_from_annotation(raw_args[0])
    if origin in (Union, UnionType) and raw_args:
        return _schema_from_annotation(raw_args[0])
    schema_type = _schema_type_from_annotation(annotation)
    if schema_type == "array":
        item_annotation = raw_args[0] if raw_args else Any
        return {"type": "array", "items": _schema_from_annotation(item_annotation)}
    if schema_type == "object":
        return {"type": "object"}
    return {"type": schema_type}


def _schema_type_from_json_schema(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    if isinstance(raw_type, list):
        for item in raw_type:
            if isinstance(item, str) and item != "null":
                return item
    for union_key in ("anyOf", "oneOf", "allOf"):
        for candidate in schema.get(union_key) or []:
            if not isinstance(candidate, dict):
                continue
            candidate_type = _schema_type_from_json_schema(candidate)
            if candidate_type and candidate_type != "null":
                return candidate_type
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return "string"


def _extract_tool_parameters(tool: BaseTool) -> list[dict[str, Any]]:
    args_schema = getattr(tool, "args_schema", None)
    if not args_schema:
        return []

    try:
        schema = args_schema if isinstance(args_schema, dict) else args_schema.schema()
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        parameters = []
        for param_name, param_info in properties.items():
            if param_name == "runtime" or not isinstance(param_info, dict):
                continue
            parameters.append(
                {
                    "name": param_name,
                    "type": _schema_type_from_json_schema(param_info),
                    "description": param_info.get("description", ""),
                    "required": param_name in required,
                    "default": param_info.get("default"),
                    "schema": param_info,
                }
            )
        return parameters
    except Exception:
        pass

    model_fields = getattr(args_schema, "model_fields", {})
    parameters = []
    for param_name, field in model_fields.items():
        if param_name == "runtime":
            continue
        default = None if field.is_required() else field.default
        field_schema = getattr(field, "json_schema_extra", None) or _schema_from_annotation(
            field.annotation
        )
        parameters.append(
            {
                "name": param_name,
                "type": _schema_type_from_json_schema(field_schema),
                "description": field.description or "",
                "required": field.is_required(),
                "default": default,
                "schema": field_schema,
            }
        )
    return parameters


async def get_internal_tool_policies() -> dict[str, MCPToolPolicy]:
    """Load explicit tool policies for the internal virtual server."""
    try:
        return await MCPStorage().list_tool_policies(INTERNAL_MCP_SERVER_NAME)
    except Exception:
        return {}


async def get_internal_tools_for_user(
    *,
    user_id: str | None,
    user_roles: list[str] | None,
    is_admin: bool,
) -> list[BaseTool]:
    """Return internal tools filtered and wrapped by per-tool policy."""
    tools = build_internal_tools()
    if not tools:
        return []

    policies = await get_internal_tool_policies()
    user_permissions = await _resolve_permissions_for_roles(user_roles)
    wrapped: list[BaseTool] = []
    for tool in tools:
        if not _is_plugin_tool_exposed(tool.name):
            continue
        policy = _policy_for_tool(policies, tool.name)
        if not _is_tool_allowed(policy=policy, user_roles=user_roles, is_admin=is_admin):
            continue
        if not _is_tool_allowed_by_business_permission(
            tool.name,
            user_permissions=user_permissions,
        ):
            continue

        guarded_tool: BaseTool = PluginRuntimeToolGuard(tool)
        wrapped.append(
            MCPToolWithRetry(
                guarded_tool,
                user_id=user_id,
                server_name=INTERNAL_MCP_SERVER_NAME,
                user_roles=user_roles,
                is_admin=is_admin,
                role_quotas=(policy.role_quotas if policy else None),
                quota_tool_name=tool.name,
            )
        )
    return wrapped


async def get_internal_tool_infos(
    *,
    user_id: str | None,
    user_roles: list[str] | None,
    is_admin: bool,
) -> list[MCPToolInfo]:
    """Return tool metadata for the virtual internal server."""
    del user_id
    policies = await get_internal_tool_policies()
    user_permissions = await _resolve_permissions_for_roles(user_roles)
    infos: list[MCPToolInfo] = []
    for tool in build_internal_tools():
        if not _is_plugin_tool_exposed(tool.name):
            continue
        policy = _policy_for_tool(policies, tool.name)
        if not _is_tool_allowed(policy=policy, user_roles=user_roles, is_admin=is_admin):
            continue
        if not _is_tool_allowed_by_business_permission(
            tool.name,
            user_permissions=user_permissions,
        ):
            continue

        parameters = _extract_tool_parameters(tool)

        infos.append(
            MCPToolInfo(
                name=tool.name,
                description=getattr(tool, "description", ""),
                parameters=parameters,
                system_disabled=bool(policy.disabled) if policy else False,
                user_disabled=False,
                allowed_roles=list(policy.allowed_roles) if policy else [],
                role_quotas=dict(policy.role_quotas) if policy else {},
                policy_configured=policy is not None,
                inline_exposure=bool(policy.inline_exposure) if policy else False,
            )
        )
    return infos

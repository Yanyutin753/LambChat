"""Registry for LambChat internal tools exposed through the MCP UI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, get_args, get_origin

from langchain_core.tools import BaseTool

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
from src.infra.tool.team_tool import get_team_tools
from src.kernel.config import settings
from src.kernel.schemas.mcp import (
    MCPServerResponse,
    MCPToolInfo,
    MCPToolPolicy,
    MCPTransport,
)
from src.kernel.types import Permission

INTERNAL_MCP_SERVER_NAME = "lambchat_internal"

_SCHEDULED_TASK_TOOL_PERMISSIONS = {
    "scheduled_task_create": Permission.SCHEDULED_TASK_WRITE.value,
    "scheduled_task_list": Permission.SCHEDULED_TASK_READ.value,
    "scheduled_task_update": Permission.SCHEDULED_TASK_WRITE.value,
    "scheduled_task_delete": Permission.SCHEDULED_TASK_DELETE.value,
}


def build_internal_tools() -> list[BaseTool]:
    """Build the internal tool set that LambChat exposes to agents."""
    from src.infra.logging import get_logger

    logger = get_logger(__name__)
    tools: list[BaseTool] = []

    if settings.ENABLE_IMAGE_ANALYSIS:
        tools.append(get_image_analysis_tool())

    if settings.ENABLE_IMAGE_GENERATION:
        tools.append(get_image_generation_tool())
        tools.append(get_reference_image_generation_tool())

    if settings.ENABLE_AUDIO_TRANSCRIPTION:
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
    tools.extend(get_persona_preset_tools())
    tools.extend(get_team_tools())

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
    if origin is not None and args:
        if origin in (list, tuple, set):
            return "array"
        return _schema_type_from_annotation(args[0])
    if annotation in (list, tuple, set):
        return "array"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is dict:
        return "object"
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
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", ""),
                    "required": param_name in required,
                    "default": param_info.get("default"),
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
        parameters.append(
            {
                "name": param_name,
                "type": _schema_type_from_annotation(field.annotation),
                "description": field.description or "",
                "required": field.is_required(),
                "default": default,
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
    """Return all authorized internal tools for backward-compatible callers."""
    direct, deferred = await get_internal_tools_by_exposure_for_user(
        user_id=user_id,
        user_roles=user_roles,
        is_admin=is_admin,
    )
    return direct + deferred


async def get_internal_tools_by_exposure_for_user(
    *,
    user_id: str | None,
    user_roles: list[str] | None,
    is_admin: bool,
) -> tuple[list[BaseTool], list[BaseTool]]:
    """Return authorized internal tools split into direct and deferred schema exposure."""
    tools = build_internal_tools()
    if not tools:
        return [], []

    policies = await get_internal_tool_policies()
    user_permissions = await _resolve_permissions_for_roles(user_roles)
    direct: list[BaseTool] = []
    deferred: list[BaseTool] = []
    for tool in tools:
        policy = _policy_for_tool(policies, tool.name)
        if not _is_tool_allowed(policy=policy, user_roles=user_roles, is_admin=is_admin):
            continue
        if not _is_tool_allowed_by_business_permission(
            tool.name,
            user_permissions=user_permissions,
        ):
            continue

        wrapped = MCPToolWithRetry(
            tool,
            user_id=user_id,
            server_name=INTERNAL_MCP_SERVER_NAME,
            user_roles=user_roles,
            is_admin=is_admin,
            role_quotas=(policy.role_quotas if policy else None),
            quota_tool_name=tool.name,
        )
        target = direct if policy is not None and policy.inline_exposure else deferred
        target.append(wrapped)
    return direct, deferred


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

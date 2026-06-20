"""Extension host contribution routes.

This module exposes the host-facing contribution contract separately from the
Plugin Runtime management API. Runtime state still owns whether a plugin is
executable; the extension host consumes only the safe contribution summary.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.api.routes.plugin_runtime import (
    PluginRuntimeContributionStatesResponse,
    _contribution_state_response,
    _get_runtime,
)
from src.kernel.extensions.host_slots import EXTENSION_HOST_SLOTS

router = APIRouter()


class ExtensionScopedOptionResponse(BaseModel):
    id: str
    plugin_id: str
    plugin_enabled: bool
    effective: bool
    plugin_status: str
    key: str
    type: str
    label: str
    description: str
    default_value: Any = None
    group: str
    order: int
    options: list[str] | None = None
    json_schema: dict[str, Any] | None = None
    renderer: str | None = None
    suppresses_core_persona_selector: bool = False
    legacy_payload_keys: list[str] = Field(default_factory=list)
    applies_to_session_key: str | None = None
    visible_when: dict[str, Any] | None = None
    area: Literal["project_option", "session_option", "channel_option", "scheduled_task_option"]


class ExtensionScopedOptionsResponse(BaseModel):
    options: list[ExtensionScopedOptionResponse]
    total: int
    scope: Literal["project", "session", "channel", "scheduled_task"]


class ExtensionHostSlotsResponse(BaseModel):
    slots: list[dict[str, Any]]
    total: int


@router.get("/slots", response_model=ExtensionHostSlotsResponse)
async def list_extension_host_slots() -> ExtensionHostSlotsResponse:
    """Return the host-declared plugin slot contract for folder plugins."""
    return ExtensionHostSlotsResponse(
        slots=[slot.model_dump() for slot in EXTENSION_HOST_SLOTS],
        total=len(EXTENSION_HOST_SLOTS),
    )


@router.get("/contributions", response_model=PluginRuntimeContributionStatesResponse)
async def list_extension_contributions(
    request: Request,
    include_inactive: bool = False,
) -> PluginRuntimeContributionStatesResponse:
    """Return runtime-filterable contributions for frontend host slots."""
    runtime = _get_runtime(request)
    states = [state for state in runtime.states() if include_inactive or state.executable]
    return PluginRuntimeContributionStatesResponse(
        plugins=[_contribution_state_response(state) for state in states],
        total=len(states),
    )


@router.get(
    "/contributions/project-options",
    response_model=ExtensionScopedOptionsResponse,
)
async def list_extension_project_options(
    request: Request,
    include_inactive: bool = False,
) -> ExtensionScopedOptionsResponse:
    """Return plugin-declared project option schemas for host UIs."""
    return _scoped_options_response(
        request,
        scope="project",
        include_inactive=include_inactive,
    )


@router.get(
    "/contributions/session-options",
    response_model=ExtensionScopedOptionsResponse,
)
async def list_extension_session_options(
    request: Request,
    include_inactive: bool = False,
) -> ExtensionScopedOptionsResponse:
    """Return plugin-declared session option schemas for host UIs."""
    return _scoped_options_response(
        request,
        scope="session",
        include_inactive=include_inactive,
    )


@router.get(
    "/contributions/channel-options",
    response_model=ExtensionScopedOptionsResponse,
)
async def list_extension_channel_options(
    request: Request,
    include_inactive: bool = False,
) -> ExtensionScopedOptionsResponse:
    """Return plugin-declared channel option schemas for connector UIs."""
    return _scoped_options_response(
        request,
        scope="channel",
        include_inactive=include_inactive,
    )


@router.get(
    "/contributions/scheduled-task-options",
    response_model=ExtensionScopedOptionsResponse,
)
async def list_extension_scheduled_task_options(
    request: Request,
    include_inactive: bool = False,
) -> ExtensionScopedOptionsResponse:
    """Return plugin-declared scheduled task option schemas for task UIs."""
    return _scoped_options_response(
        request,
        scope="scheduled_task",
        include_inactive=include_inactive,
    )


def _scoped_options_response(
    request: Request,
    *,
    scope: Literal["project", "session", "channel", "scheduled_task"],
    include_inactive: bool,
) -> ExtensionScopedOptionsResponse:
    runtime = _get_runtime(request)
    area_by_scope: dict[
        str, Literal["project_option", "session_option", "channel_option", "scheduled_task_option"]
    ] = {
        "project": "project_option",
        "session": "session_option",
        "channel": "channel_option",
        "scheduled_task": "scheduled_task_option",
    }
    area = area_by_scope[scope]
    options: list[ExtensionScopedOptionResponse] = []
    for state in runtime.states():
        manifest = state.manifest
        if manifest is None:
            continue
        if not include_inactive and not state.executable:
            continue
        if scope == "project":
            declared_options = manifest.frontend.project_options
        elif scope == "session":
            declared_options = manifest.frontend.session_options
        elif scope == "channel":
            declared_options = manifest.frontend.channel_options
        else:
            declared_options = manifest.frontend.scheduled_task_options
        for option in declared_options:
            options.append(
                ExtensionScopedOptionResponse(
                    id=f"{manifest.id}.{option.key}",
                    plugin_id=manifest.id,
                    plugin_enabled=state.enabled,
                    effective=state.executable,
                    plugin_status=state.status.value,
                    key=option.key,
                    type=option.type,
                    label=option.label,
                    description=option.description,
                    default_value=option.default,
                    group=option.group,
                    order=option.order,
                    options=option.options,
                    json_schema=option.json_schema,
                    renderer=option.renderer,
                    suppresses_core_persona_selector=option.suppresses_core_persona_selector,
                    legacy_payload_keys=list(option.legacy_payload_keys),
                    applies_to_session_key=option.applies_to_session_key,
                    visible_when=(
                        option.visible_when.model_dump(mode="json")
                        if option.visible_when is not None
                        else None
                    ),
                    area=area,
                )
            )
    options.sort(key=lambda item: (item.order, item.id))
    return ExtensionScopedOptionsResponse(
        options=options,
        total=len(options),
        scope=scope,
    )

"""LLM-callable tools for searching personas and creating reusable teams."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_blocking_io
from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.role.storage import RoleStorage
from src.infra.team.manager import TeamManager
from src.infra.tool.backend_utils import get_user_id_from_runtime
from src.infra.user.storage import UserStorage
from src.kernel.schemas.team import TeamCreate, TeamMemberCreate, TeamUpdate
from src.kernel.schemas.user import TokenPayload

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False, default=str)


async def _resolve_user(user_id: str) -> TokenPayload | None:
    user = await UserStorage().get_by_id(user_id)
    if not user:
        return None

    role_storage = RoleStorage()
    roles = await role_storage.get_by_names(user.roles or [])

    permissions: set[str] = set()
    for role in roles:
        for permission in role.permissions:
            permissions.add(permission if isinstance(permission, str) else permission.value)

    return TokenPayload(
        sub=user.id,
        username=user.username,
        roles=[r.name for r in roles],
        permissions=sorted(permissions),
    )


def _is_admin(user: TokenPayload) -> bool:
    return "persona_preset:admin" in set(user.permissions or [])


def _can_read_personas(user: TokenPayload) -> bool:
    permissions = set(user.permissions or [])
    return bool(
        permissions.intersection(
            {
                "persona_preset:read",
                "team:read",
                "chat:write",
            }
        )
    )


def _can_create_team(user: TokenPayload) -> bool:
    permissions = set(user.permissions or [])
    return "team:write" in permissions or "chat:write" in permissions


_PLACEHOLDER_PERSONA_IDS = {
    "general-purpose",
    "general_purpose",
    "general purpose",
    "default",
    "none",
    "null",
}


def _invalid_persona_preset_id(persona_preset_id: str) -> str | None:
    value = str(persona_preset_id or "").strip()
    if not value or value.lower() in _PLACEHOLDER_PERSONA_IDS:
        return value or persona_preset_id
    return None


@tool
async def search_persona_presets(
    query: Annotated[
        str | None,
        "Role/capability query; empty lists recent visible personas.",
    ] = None,
    tag: Annotated[
        str | None,
        "Optional exact tag.",
    ] = None,
    limit: Annotated[
        int,
        "Maximum results (1-50).",
    ] = 20,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Use this tool first to search visible personas before create_agent_team. Use
    returned IDs as member persona_preset_id values; search again if roles are missing."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_dumps_result({"error": "No user context available"})

    user = await _resolve_user(user_id)
    if not user or not _can_read_personas(user):
        return await _json_dumps_result(
            {"error": "Permission denied: persona_preset:read required"}
        )

    try:
        presets = await PersonaPresetManager().list_presets(
            user_id=user_id,
            is_admin=_is_admin(user),
            q=query.strip() if query else None,
            tag=tag.strip() if tag else None,
            limit=min(max(limit, 1), 50),
        )
    except Exception as e:
        return await _json_dumps_result({"error": f"Failed to search persona presets: {e}"})

    return await _json_dumps_result(
        {
            "success": True,
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "description": preset.description,
                    "tags": preset.tags,
                    "avatar": preset.avatar,
                    "starter_prompts": [
                        prompt.model_dump(mode="json") for prompt in preset.starter_prompts
                    ],
                }
                for preset in presets
            ],
        }
    )


@tool
async def create_agent_team(
    name: Annotated[
        str,
        "Reusable user-facing team name (max 80 characters).",
    ],
    members: Annotated[
        list[dict[str, Any]],
        "Members from search_persona_presets/save_persona_preset. Each needs "
        "persona_preset_id and role_name; optional agent_id (do not use 'team'), model_id, "
        "role_avatar (emoji or avatar image URL), role_instructions, member_id, position, "
        "enabled. Do not invent persona_preset_id values. Never use placeholder ids such "
        "as 'general-purpose'. Use 2-5 members for complex work or 1 member for a narrow "
        "task; include role_instructions and role_avatar.",
    ],
    team_id: Annotated[
        str | None,
        "Optional existing Team id to update; omit to create.",
    ] = None,
    description: Annotated[
        str,
        "Short task/output description.",
    ] = "",
    avatar: Annotated[
        str | None,
        "Always provide an emoji or avatar image URL.",
    ] = None,
    tags: Annotated[
        list[str] | None,
        "Short searchable tags.",
    ] = None,
    default_member_id: Annotated[
        str | None,
        "Default member_id; must occur in members. Omit to use first.",
    ] = None,
    team_instructions: Annotated[
        str,
        "Routing rules: work split/order, verification, and synthesis, e.g. Researcher "
        "gathers evidence first; Writer drafts; Reviewer checks gaps.",
    ] = "",
    starter_prompts: Annotated[
        list[dict[str, Any]] | None,
        "Optional suggestions, e.g. {'text': {'zh': '帮我分析这三个竞品', "
        "'en': 'Analyze these three competitors'}, 'icon': '🔎'}; icon is a single emoji.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Create or update a persistent Team, like creating or editing a Team in the UI.
    Call search_persona_presets first; use save_persona_preset for a missing role. Leave
    `team_id` empty to create a new team. Pass `team_id` to update an existing team."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return await _json_dumps_result({"error": "No user context available"})

    user = await _resolve_user(user_id)
    if not user or not _can_create_team(user):
        return await _json_dumps_result({"error": "Permission denied: team:write required"})

    if not members:
        return await _json_dumps_result({"error": "At least one team member is required"})

    for item in members:
        invalid_id = _invalid_persona_preset_id(str(item.get("persona_preset_id") or ""))
        if invalid_id is not None:
            return await _json_dumps_result(
                {
                    "error": (
                        f"Invalid persona_preset_id '{invalid_id}'. Search for an existing "
                        "persona or call save_persona_preset first, then use the returned "
                        "preset.id."
                    )
                }
            )

    try:
        team_members = [
            TeamMemberCreate(
                member_id=item.get("member_id") or f"m-{index}",
                persona_preset_id=item["persona_preset_id"],
                agent_id=item.get("agent_id"),
                model_id=item.get("model_id"),
                role_name=item.get("role_name") or "",
                role_avatar=item.get("role_avatar"),
                role_instructions=item.get("role_instructions") or "",
                position=item.get("position", index - 1),
                enabled=item.get("enabled", True),
            )
            for index, item in enumerate(members, start=1)
        ]
    except KeyError:
        return await _json_dumps_result({"error": "Each member must include persona_preset_id"})
    except Exception as e:
        return await _json_dumps_result({"error": f"Invalid team member payload: {e}"})

    try:
        manager = TeamManager()
        payload = {
            "name": name,
            "description": description,
            "avatar": avatar,
            "tags": tags or [],
            "members": team_members,
            "default_member_id": default_member_id,
            "team_instructions": team_instructions,
            "starter_prompts": starter_prompts or [],
        }
        if team_id:
            team = await manager.update_team(
                team_id,
                TeamUpdate(**payload),
                owner_user_id=user_id,
                user=user,
            )
            action = "updated"
        else:
            team = await manager.create_team(
                TeamCreate(
                    **payload,
                ),
                owner_user_id=user_id,
                user=user,
            )
            action = "created"
    except Exception as e:
        operation = "update" if team_id else "create"
        return await _json_dumps_result({"error": f"Failed to {operation} team: {e}"})

    return await _json_dumps_result(
        {
            "success": True,
            "entity_type": "team",
            "action": action,
            "created": action == "created",
            "updated": action == "updated",
            "team_id": team.id,
            "team": team.model_dump(mode="json"),
            "message": f"Team '{team.name}' {action} and saved.",
        }
    )


def get_team_tools() -> list[BaseTool]:
    """Return team-building tools for the current user."""
    return [search_persona_presets, create_agent_team]

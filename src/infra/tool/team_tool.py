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
        "Search text for persona presets. Use this before creating a team. "
        "Search by role/capability words from the user's task, such as 'research', "
        "'writer', 'reviewer', 'designer', 'coding', '数据分析', or '竞品'. "
        "Use a broad query first if you are unsure. Pass null or an empty string to list "
        "recent visible personas when you need general candidates.",
    ] = None,
    tag: Annotated[
        str | None,
        "Optional exact tag filter. Use only when the user asks for a specific domain "
        "or when a prior search result showed a useful tag.",
    ] = None,
    limit: Annotated[
        int,
        "Maximum personas to return, from 1 to 50. Use 10-20 for exploration; use a "
        "smaller number when you already know the capability you need.",
    ] = 20,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Search visible persona presets that can become members of a Team.

    Use this tool first when you need to assemble a Team. The returned `id` values are
    the only valid `persona_preset_id` values to pass into `create_agent_team`.
    Search several times with different capability words if the first result set does
    not cover all roles needed by the user's task.
    """
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
        "User-facing team name, max 80 characters. Required for both create and update. "
        "Choose a reusable name that reflects the goal and the main roles, e.g. "
        "'竞品分析团队 · Research/Writer' or 'Code Review Team · Engineer/Reviewer'.",
    ],
    members: Annotated[
        list[dict[str, Any]],
        "Members chosen by the LLM after calling search_persona_presets. Each item is an "
        "object with: persona_preset_id (required, must be an id returned by "
        "search_persona_presets or the preset.id returned by save_persona_preset), "
        "model_id (optional model configuration id for this member; omit or null to "
        "follow the conversation model), "
        "role_name (required, concise display name for this team such as 'Market Research "
        "Lead'), role_avatar (required when creating a role for a team; use an emoji or "
        "avatar image URL such as '🔎' or 'https://example.com/researcher.png'), "
        "role_instructions (recommended, specific responsibility in this team), "
        "member_id (optional stable id like 'm-research'), position (optional zero-based "
        "order), enabled (optional, default true). Create 2-5 members for complex work, "
        "or 1 member for narrow tasks. Do not invent persona_preset_id values. Never use "
        "placeholder ids such as 'general-purpose'; if no existing persona fits the role, "
        "call save_persona_preset first and use the returned preset.id.",
    ],
    team_id: Annotated[
        str | None,
        "Optional existing Team id to update. Leave null to create a new Team. Pass this "
        "when the user asks to adjust, expand, rename, or improve an existing team, or when "
        "the current conversation/session already has a team_id you should modify.",
    ] = None,
    description: Annotated[
        str,
        "Short user-facing description of what this team is good at. Mention the task "
        "type and expected output, not internal implementation details.",
    ] = "",
    avatar: Annotated[
        str | None,
        "Always provide an emoji or avatar image URL for this team when creating or "
        "updating it. Use a single emoji such as '🧭' or an image URL such as "
        "'https://example.com/team.png'.",
    ] = None,
    tags: Annotated[
        list[str] | None,
        "Short searchable tags, e.g. ['auto-built', 'research', 'writing']. Keep tags "
        "lowercase and useful for later filtering.",
    ] = None,
    default_member_id: Annotated[
        str | None,
        "member_id of the default role for ambiguous subtasks. Usually choose the planner, "
        "lead researcher, or generalist member. Must match one member_id in members. Leave "
        "null to use the first member.",
    ] = None,
    team_instructions: Annotated[
        str,
        "Collaboration rules for the team router. Include how to split work, which role "
        "goes first, how to verify or review, and how to synthesize final output. Example: "
        "'Researcher gathers evidence first; Writer drafts; Reviewer checks gaps and "
        "risks; final answer must synthesize, not concatenate.'",
    ] = "",
    run_in_sandbox: Annotated[
        bool,
        "Whether this Team should run inside the isolated sandbox backend. Use true for "
        "tasks that need filesystem/code/tool execution isolation; use false for normal "
        "coordination and writing teams.",
    ] = False,
    starter_prompts: Annotated[
        list[dict[str, Any]] | None,
        "Optional prompt suggestions shown after selecting this team. Use the same shape "
        "as persona starter prompts: each item is an object with 'text' (a plain string "
        "or a multi-language dict like {'zh': '帮我分析这三个竞品', 'en': 'Analyze these "
        "three competitors'}) and optional 'icon' (a single emoji, e.g. '🔎', '📝', "
        "'✅'). Example: [{'icon': '🔎', 'text': {'zh': '调研这个市场并输出竞品表', "
        "'en': 'Research this market and produce a competitor table'}}, {'icon': '📝', "
        "'text': 'Turn the research into an executive brief'}]. Keep examples practical "
        "for reusing this exact team.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Create or update a reusable Team from an LLM-authored team form.

    Call `search_persona_presets` first, inspect the returned personas, then call this
    tool with a complete team design. If the search results do not include a suitable
    persona for a role, call `save_persona_preset` first to create that role, then use
    the returned `preset.id` in `members`. Leave `team_id` empty to create a new team;
    Pass `team_id` to update an existing team. This tool is equivalent to the user
    manually creating or editing a Team in the UI: it persists the Team for the current
    user and returns `team_id` for immediate use in the conversation.
    """
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
                agent_id=None,
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
            "run_in_sandbox": run_in_sandbox,
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

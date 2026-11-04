"""Assistant groups are a live Team projection, with their own conversation and memory."""

from src.infra.assistant.store import AssistantStore
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot
from src.kernel.schemas.team import TeamMemberResponse, TeamResponse


async def group_members(user, group, *, store=None):
    store = store or AssistantStore()
    members = []
    for identity in group.member_ids:
        member = await store.get(user.sub, identity)
        if member is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if member.status != "active" or member.kind == "group" or member.team_id:
            raise AppError(ErrorCode.CONFLICT)
        members.append(member)
    return members


async def runtime_group_team(user, group, *, store=None):
    from src.infra.assistant.service import AssistantService

    members = await group_members(user, group, store=store)
    for member in members:
        await AssistantService().validate_configuration(user, member)
    leader = next(member for member in members if member.id == group.leader_id)
    return TeamResponse(
        id=f"assistant-group:{group.id}",
        owner_user_id=user.sub,
        name=group.name,
        default_member_id=group.leader_id,
        team_instructions=(
            f"This is a persistent group chat coordinated by {leader.name}. "
            "Answer simple coordination messages yourself. For substantive work, use the "
            "named members' persistent subagent sessions; reuse a member's session on follow-up. "
            "When the user @mentions a member by name or @[id], dispatch to that member; "
            "do not impersonate them. Show who contributed and their actual findings. "
            "Members share only this group conversation and group memory, never private chats "
            "or private memories. All members work in the group's configured environment. "
            "A completed reply needs no acceptance ceremony: offer the result and continue naturally.\n"
            + group.instructions
        ),
        members=[
            TeamMemberResponse(
                member_id=member.id,
                persona_preset_id=member.persona_preset_id or "",
                role_name=member.name,
                model_id=member.model_id,
                agent_id="search",
                position=index,
            )
            for index, member in enumerate(members)
        ],
    )


async def resolve_group_for_session(user_id, session_id, *, user_input=""):
    from src.infra.assistant.service import conversation_assistant
    from src.infra.auth.tool_authority import resolve_tool_user
    from src.infra.task.background_task_store import BackgroundTaskStore

    group = await conversation_assistant(user_id, session_id)
    if group is None:
        record = await BackgroundTaskStore().collection.find_one(
            {"user_id": user_id, "session_id": session_id}
        )
        if record and record.get("assistant_id"):
            group = await AssistantStore().get(user_id, record["assistant_id"])
    if group is None or group.kind != "group":
        return None
    user = await resolve_tool_user(user_id)
    if not user or "chat:write" not in user.permissions or group.status != "active":
        raise AppError(ErrorCode.FORBIDDEN)
    team = await runtime_group_team(user, group)
    return route_group_mentions(team, user_input)


async def group_member_snapshot(team, member, user_id):
    from src.infra.persona_preset.manager import get_persona_preset_manager

    if not team.id.startswith("assistant-group:"):
        return await get_persona_preset_manager().use_preset(
            member.persona_preset_id, user_id=user_id, is_admin=False
        )
    bot = await AssistantStore().get(user_id, member.member_id)
    if bot is None or bot.status != "active" or bot.kind == "group":
        raise AppError(ErrorCode.FORBIDDEN)
    snapshot = (
        await get_persona_preset_manager().use_preset(
            bot.persona_preset_id, user_id=user_id, is_admin=False
        )
        if bot.persona_preset_id
        else PersonaPresetSnapshot(preset_id=bot.id, name=bot.name, system_prompt="")
    )
    return snapshot.model_copy(
        update={
            "system_prompt": "\n\n".join(filter(None, [snapshot.system_prompt, bot.instructions]))
        }
    )


def assistant_instructions(assistant):
    if assistant.kind != "chief":
        return assistant.instructions
    return (
        "You are Chief, the user's personal assistant coordinator. Help through normal conversation. "
        "When asked to create or manage assistants or group chats, discover and use "
        "list_assistants, create_assistant, update_assistant. List existing identities first; "
        "reuse suitable assistants rather than duplicating them. Use actual returned IDs and revisions. "
        "For a group, choose at least two members and a coordinator from those members. "
        "Only make the changes the user requested. Do not grant yourself capabilities, alter security "
        "settings, or copy private chat contents into group instructions. Return a short result with "
        "a clickable Markdown link to the returned assistant URL. Do not ask the user to accept completed work.\n"
        + assistant.instructions
    )


def route_group_mentions(team, message):
    import re

    explicit = re.findall(r"@\[[^\]]*\]\(assistant:([^)]*)\)", message)
    members = {member.member_id: member for member in team.members}
    if any(identity not in members for identity in explicit):
        raise AppError(ErrorCode.VALIDATION_ERROR)
    selected = set(explicit)
    if not explicit:
        selected = {
            member.member_id
            for member in team.members
            if re.search(r"(?<!\w)@" + re.escape(member.role_name) + r"(?=\s|$|[,:，：])", message)
        }
    if selected:
        values = [member for member in team.members if member.member_id in selected]
        return team.model_copy(update={"members": values, "default_member_id": values[0].member_id})
    return team


async def team_member_snapshots(team, user_id):
    from src.infra.persona_preset.manager import get_persona_preset_manager

    if team.id.startswith("assistant-group:"):
        return [
            await group_member_snapshot(team, member, user_id) for member in team.active_members
        ]
    return await get_persona_preset_manager().use_presets(
        [member.persona_preset_id for member in team.active_members],
        user_id=user_id,
        is_admin=False,
    )

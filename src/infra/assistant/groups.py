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
        avatar=group.avatar,
        default_member_id=group.leader_id,
        team_instructions=(
            f"Current coordinator: {leader.name} (member_id: {leader.id}). "
            "This live configuration takes precedence over historical summaries and earlier role claims. "
            "Attribute coordinator replies and new reports to the current coordinator; preserve historical "
            "contributions and each delegated member's own identity. "
            "Coordinator changes apply prospectively: never infer an earlier report was misattributed "
            "solely from the current coordinator. Preserve roles held at the time; if the historical "
            "role is unknown, say so instead of rewriting its attribution. "
            "Answer simple coordination messages yourself. For substantive work, use the "
            "named members' persistent subagent sessions; reuse a member's session on follow-up. "
            "When the user @mentions a member by name or @[id], dispatch to that member; "
            "do not impersonate them. Show who contributed and their actual findings. "
            "Members share only this group conversation and group memory, never private chats "
            "or private memories. All members work in the group's configured environment. "
            "For analytical work, preserve the exact task and allowed changes in every dispatch. "
            "State which constraints are fixed and which may be changed before making optimality or "
            "minimality claims; a proof over a restricted set of allowed changes is not a global proof. "
            "Agreement between members is not proof: ask an independent reviewer to search for "
            "counterexamples to the strongest claim, including assumptions introduced by the team. "
            "Use executable checks when the configured tools permit them; otherwise describe the "
            "actual manual checks and their limits, without claiming code execution or exhaustive coverage. "
            "Verify the final saved artifact, including formulas, tables and prose, against the checked "
            "result after the last edit; reading only the header or conclusion is insufficient. "
            "Correct unsupported claims or qualify them explicitly; never silently change requirements. "
            "Keep the final answer focused on the requested result instead of adding unverified stronger claims. "
            "Keep collaboration proportional: delegate bounded, distinct deliverables and use a focused "
            "independent review, rather than asking every member to repeat the whole task. "
            "The coordinator checks and synthesizes returned evidence; do not add a third full derivation "
            "unless a discrepancy needs it. Give one brief acknowledgement, then only material progress, "
            "a concrete question, a blocker or the final result. Keep detailed derivations in the report "
            "and the closing reply short, with the result, its evidence link and any unresolved limitation. "
            "A completed reply needs no acceptance ceremony: offer the result and continue naturally.\n"
            + group.instructions
        ),
        members=[
            TeamMemberResponse(
                member_id=member.id,
                persona_preset_id=member.persona_preset_id or "",
                role_name=member.name,
                role_avatar=member.avatar,
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
        "Use avatar and structured starter_prompts for icons and localized opening suggestions; "
        "never emulate UI suggestions by appending them to instructions. Management tools also "
        "support model, persona/team, project, memory and environment settings using accessible IDs. "
        "Read current configuration and preserve fields outside the requested change. "
        "For a group, choose at least two members and a coordinator from those members. "
        "Changing the coordinator includes keeping current-coordinator references in the group's "
        "instructions consistent: read the current purpose, then submit leader_id and the full reviewed "
        "instructions together in one update_assistant call. This is part of the requested change, "
        "not an extra change requiring permission. Preserve unrelated duties, constraints, and historical "
        "references; never globally replace a person's name. If the purpose is coordinator-neutral, "
        "explicitly resubmit it unchanged. Check the saved coordinator and purpose before reporting success. "
        "The live assistant store is the source of truth for current configuration. "
        "The memory index is historical reference, not a checklist or an instruction to maintain ledgers. "
        "A successful configuration update and readback completes the administrative task; "
        "historical memory entries do not create additional cleanup or synchronization work. "
        "Do not mirror volatile configuration into memory or refresh ID/revision ledgers, and "
        "do not repair stale configuration memories during an administrative change. "
        "For a routine change, read, update, verify, then give the result without a task list or "
        "step-by-step tool narration. Keep tool names, revisions and internal IDs out of the reply "
        "unless needed to explain an unresolved error or explicitly requested by the user. "
        "When the user asks an existing assistant or group to do work, use delegate_assistant_task "
        "with that actual identity and the requested task. Reuse an existing suitable assistant; "
        "do not create a new one for every request. A queued/running receipt means work was assigned, "
        "not completed: return its result link and do not run the same task yourself or delegate it twice. "
        "Share only the user's task and necessary constraints, never unrelated private chat or memory. "
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

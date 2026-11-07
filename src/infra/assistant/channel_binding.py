"""Bind existing channel delivery to an isolated assistant discussion."""

from src.infra.assistant.discussions import (
    DiscussionStore,
    discussion_session_id,
    is_discussion_session,
)
from src.infra.channel.inbox_worker import current_delivery
from src.kernel.errors import AppError, ErrorCode


def channel_assistant_id(config: dict | None) -> str | None:
    return ((config or {}).get("runtime_config") or {}).get("assistant_id")


def channel_discussion_session(source_session: str, config: dict | None, user_id: str) -> str:
    assistant_id = channel_assistant_id(config)
    context = current_delivery.get()
    if context and context.checkpoint.get("run_id"):
        if context.checkpoint.get("assistant_id") != assistant_id:
            raise AppError(ErrorCode.CONFLICT)
        return str(context.checkpoint["session_id"])
    return (
        discussion_session_id(user_id, assistant_id, source_session)
        if assistant_id
        else source_session
    )


async def prepare_channel_assistant(delivery: dict, values: dict) -> dict:
    from src.api.routes.chat_request_config import resolve_persona_request
    from src.infra.agent.access import validate_user_agent_access
    from src.infra.assistant.execution import ASSISTANT_EXECUTOR_KEY, execute_assistant_stream
    from src.infra.assistant.service import assistant_agent, prepare_assistant_request
    from src.infra.channel.channel_storage import ChannelStorage
    from src.infra.task.background_tasks import _load_user
    from src.kernel.schemas.agent import AgentRequest
    from src.kernel.schemas.channel import ChannelType

    instance_id = delivery.get("channel_instance_id")
    if not instance_id:
        return values
    config = await ChannelStorage().get_config(
        values["user_id"], ChannelType(delivery["channel_type"]), instance_id
    )
    assistant_id = channel_assistant_id(config)
    if not assistant_id:
        if is_discussion_session(values["session_id"]):
            raise AppError(ErrorCode.FORBIDDEN)
        return values
    if not is_discussion_session(values["session_id"]):
        raise AppError(ErrorCode.CONFLICT)
    await DiscussionStore().register(
        values["user_id"], assistant_id, values["session_id"], delivery
    )
    user = await _load_user(values["user_id"])
    request = AgentRequest(
        message=values["message"],
        session_id=values["session_id"],
        disabled_tools=values.get("disabled_tools"),
    )
    assistant = await prepare_assistant_request(
        request, user, {"assistant_discussion_id": values["session_id"]}
    )
    if assistant is None:
        raise AppError(ErrorCode.FORBIDDEN)
    agent_id = assistant_agent(assistant)
    await validate_user_agent_access(agent_id, user)
    await resolve_persona_request(request, user)
    request.persona_system_prompt = (
        "\n\n".join(
            part for part in (request.persona_system_prompt, assistant.instructions) if part
        )
        or None
    )
    request.agent_options = request.agent_options or {}
    # Channel language and environment variables remain explicit channel choices.
    for key in ("enable_thinking", "response_language", "channel_runtime"):
        if key in (values.get("agent_options") or {}):
            request.agent_options[key] = values["agent_options"][key]
    fields = {
        key: getattr(request, key)
        for key in (
            "agent_options",
            "project_id",
            "team_id",
            "persona_system_prompt",
            "disabled_tools",
            "disabled_skills",
            "enabled_skills",
            "disabled_mcp_tools",
            "enabled_mcp_servers",
        )
    }
    metadata = {
        **(values.get("session_metadata") or {}),
        **fields,
        "assistant_id": assistant.id,
        "assistant_discussion_id": values["session_id"],
        "agent_id": agent_id,
        "executor_key": ASSISTANT_EXECUTOR_KEY,
        "persona_preset_id": assistant.persona_preset_id,
        "auto_mode": False,
    }
    context = current_delivery.get()
    if context:
        await context.save(assistant_id=assistant.id)
    return {
        **values,
        **fields,
        "agent_id": agent_id,
        "executor": execute_assistant_stream,
        "session_metadata": metadata,
        "auto_mode": False,
    }

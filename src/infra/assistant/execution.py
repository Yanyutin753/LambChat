"""Coordinator admission is checked again when queued or recovered work starts."""

from src.infra.assistant.service import (
    AssistantService,
    assistant_agent,
    assistant_scope_session,
    conversation_assistant,
)
from src.infra.task.concurrency import register_executor
from src.kernel.errors import AppError, ErrorCode

ASSISTANT_EXECUTOR_KEY = "assistant_stream"


async def execute_assistant_stream(session_id, agent_id, message, user_id, **kwargs):
    from src.api.deps import _load_user_payload
    from src.api.routes.chat_agent_execution import _execute_agent_stream
    from src.infra.task.background_tasks import validate_background_execution

    assistant = await conversation_assistant(user_id, session_id)
    if assistant is None or agent_id != assistant_agent(assistant):
        raise AppError(ErrorCode.FORBIDDEN)
    if assistant.status != "active":
        raise AppError(ErrorCode.CONFLICT)
    user = await _load_user_payload(user_id)
    await AssistantService().validate_configuration(user, assistant)
    from src.infra.session.memory_scope import invalidate_memory_scope_caches

    invalidate_memory_scope_caches(user_id=user_id, session_id=session_id)
    # Preserve the admitted environment and revalidate its model and tool scope.
    request = await validate_background_execution(
        session_id, agent_id, user_id, kwargs.get("agent_options") or {}
    )
    from src.infra.assistant.discussions import (
        DISCUSSION_ROUTING_GUIDANCE,
        is_discussion_session,
        restrict_discussion_request,
    )

    discussion = is_discussion_session(await assistant_scope_session(user_id, session_id))
    if assistant.kind == "group" or discussion:
        restrict_discussion_request(request)
    if discussion:
        request.persona_system_prompt = "\n\n".join(
            filter(None, [request.persona_system_prompt, DISCUSSION_ROUTING_GUIDANCE])
        )
    from src.infra.assistant.groups import assistant_instructions

    request.persona_system_prompt = (
        "\n\n".join(
            part
            for part in (request.persona_system_prompt, assistant_instructions(assistant))
            if part
        )
        or None
    )
    for key in (
        "agent_options",
        "persona_system_prompt",
        "disabled_tools",
        "disabled_skills",
        "enabled_skills",
        "disabled_mcp_tools",
        "enabled_mcp_servers",
        "team_id",
    ):
        kwargs[key] = getattr(request, key)
    async for event in _execute_agent_stream(session_id, agent_id, message, user_id, **kwargs):
        yield event


register_executor(ASSISTANT_EXECUTOR_KEY, execute_assistant_stream)

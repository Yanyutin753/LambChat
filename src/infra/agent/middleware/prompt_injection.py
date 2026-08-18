"""System prompt injection middleware — memory, env vars, and static sections."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import HumanMessage

from src.infra.agent.middleware._helpers import (
    _append_human_context,
    _append_system_text_block,
    _normalize_prompt_text,
)

logger = logging.getLogger(__name__)


class SectionPromptMiddleware(AgentMiddleware):
    """Append normalized prompt sections as one system text block."""

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._prompt = "\n\n".join(
            normalized for section in sections if (normalized := _normalize_prompt_text(section))
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._prompt:
            return await handler(request)

        system_message = _append_system_text_block(request.system_message, self._prompt)
        request = request.override(system_message=system_message)
        return await handler(request)


class TurnContextPromptMiddleware(AgentMiddleware):
    """Append per-turn sections to the current user message instead of system.

    Keeping run-scoped content (goal, auto mode, ...) out of the system prompt
    preserves the byte-stable system prefix required for provider prompt/KV
    caching. The injection is request-only and never persisted to history.
    """

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._prompt = "\n\n".join(
            normalized for section in sections if (normalized := _normalize_prompt_text(section))
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._prompt:
            return await handler(request)

        messages = request.messages
        last_human = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if isinstance(messages[index], HumanMessage)
            ),
            None,
        )
        if last_human is None:
            # No user turn to annotate; fall back to the system prompt.
            system_message = _append_system_text_block(request.system_message, self._prompt)
            request = request.override(system_message=system_message)
            return await handler(request)

        messages = list(messages)
        messages[last_human] = _append_human_context(
            messages[last_human], self._prompt, "turn_context"
        )
        request = request.override(messages=messages)
        return await handler(request)


class MemoryIndexMiddleware(AgentMiddleware):
    """Adds the native memory index as request-only trailing reference context.

    The reference is appended to the *current* user message content rather than
    inserted as a separate ephemeral message: a separate message that is not
    persisted would fork the message sequence between consecutive turns and
    invalidate the provider prompt cache from the previous user turn onwards.
    The injection is applied only to this model request and is not persisted as
    conversation history by the middleware itself.
    """

    def __init__(self, *, user_id: str | None) -> None:
        super().__init__()
        self._user_id = user_id

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._user_id:
            return await handler(request)

        index_str = await _build_memory_index_for_user(self._user_id)
        if not index_str:
            return await handler(request)

        reference = index_str
        # Append to the current user turn (stable across tool loops: AI/Tool
        # messages are appended after it, so the last HumanMessage stays fixed
        # within a turn). This keeps earlier history byte-identical across
        # turns, preserving the provider prompt-cache prefix.
        messages = request.messages
        last_human = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if isinstance(messages[index], HumanMessage)
            ),
            None,
        )
        if last_human is None:
            # No user turn to annotate; skip rather than break the prefix.
            return await handler(request)
        messages = list(messages)
        messages[last_human] = _append_human_context(
            messages[last_human], reference, "memory_index_context"
        )
        request = request.override(messages=messages)
        return await handler(request)


async def _build_memory_index_for_user(user_id: str) -> str:
    """Build memory index string for a user. Returns empty string on any failure."""
    try:
        from src.infra.memory.tools import _get_backend

        backend = await _get_backend()
        if backend is None or backend.name != "native":
            return ""

        from src.infra.memory.client.native import NativeMemoryBackend

        if not isinstance(backend, NativeMemoryBackend):
            return ""
        index = await backend.build_memory_index(user_id)
        return index if index else ""
    except Exception:
        logger.warning("[Memory] Failed to build memory index for user %s", user_id, exc_info=True)
        return ""


class EnvVarPromptMiddleware(AgentMiddleware):
    """Inject configured environment variable keys into the system prompt.

    Only key names are included. Values are never read as plaintext here.
    """

    def __init__(self, *, user_id: str) -> None:
        super().__init__()
        self._user_id = user_id

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        from src.infra.tool.env_var_prompt import build_env_var_prompt

        prompt = await build_env_var_prompt(self._user_id)
        if prompt:
            new_system_message = _append_system_text_block(request.system_message, prompt)
            request = request.override(system_message=new_system_message)
        return await handler(request)

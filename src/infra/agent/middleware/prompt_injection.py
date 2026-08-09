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
from langchain_core.messages import SystemMessage

from src.infra.agent.middleware._helpers import (
    _append_system_text_block,
    _append_system_text_blocks,
    _normalize_prompt_text,
    _system_message_to_blocks,
)

logger = logging.getLogger(__name__)


class SectionPromptMiddleware(AgentMiddleware):
    """Append one or more deterministic prompt sections as separate system blocks.

    Each section becomes its own content block in the system message, enabling
    fine-grained KV cache breakpoints.  Sections are normalized (trailing
    whitespace stripped) at construction time and batch-appended in a single
    pass to avoid O(n²) block-list rebuilding.
    """

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._sections = tuple(
            _normalize_prompt_text(section) for section in sections if section.strip()
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._sections:
            return await handler(request)

        # Batch-append all sections in one pass (avoids repeated _system_message_to_blocks)
        blocks = _system_message_to_blocks(request.system_message)
        blocks.extend({"type": "text", "text": section} for section in self._sections)
        request = request.override(system_message=SystemMessage(content=blocks))
        return await handler(request)


class VolatileSectionPromptMiddleware(AgentMiddleware):
    """Append run-varying goal and execution-mode sections after stable context."""

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._sections = tuple(
            _normalize_prompt_text(section) for section in sections if section.strip()
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._sections:
            return await handler(request)

        blocks = _system_message_to_blocks(request.system_message)
        blocks.extend({"type": "text", "text": section} for section in self._sections)
        request = request.override(system_message=SystemMessage(content=blocks))
        return await handler(request)


class MemoryIndexMiddleware(AgentMiddleware):
    """Injects the native memory index into the system prompt at request time.

    Uses ``NativeMemoryBackend.build_memory_index(user_id)`` which has its own
    5-minute per-user cache, so repeated calls are essentially free after the first.
    Only active when the native backend is selected and the index feature is enabled.
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

        new_system_message = _append_system_text_block(request.system_message, index_str)
        request = request.override(system_message=new_system_message)
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
        from src.infra.tool.env_var_prompt import build_env_var_prompt_sections

        prompt_sections = await build_env_var_prompt_sections(self._user_id)
        if prompt_sections:
            new_system_message = _append_system_text_blocks(request.system_message, prompt_sections)
            request = request.override(system_message=new_system_message)
        return await handler(request)

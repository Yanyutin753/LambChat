"""Provider-aware prompt caching over deterministic system and tool prefixes."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware._helpers import _system_message_to_blocks
from src.infra.llm.client import _is_gpt_56_or_later
from src.kernel.config import settings

_MAX_ANTHROPIC_CACHE_BREAKPOINTS = 4
_PROMPT_CACHE_VOLATILE_TOOL_EXTRA = "_lambchat_prompt_cache_volatile"

logger = logging.getLogger(__name__)


class PromptCachingMiddleware(AgentMiddleware):
    """Apply documented cache controls after every prompt/tool injection step."""

    _CACHE_CONTROL = {"type": "ephemeral"}
    _AUTOMATIC_CACHE_CONTROL = {"type": "ephemeral", "ttl": "5m"}

    def __init__(self) -> None:
        super().__init__()
        self._max_cached_system_blocks = max(
            int(getattr(settings, "PROMPT_CACHE_MAX_SYSTEM_BLOCKS", 8) or 0), 0
        )
        self._max_cached_tools = max(int(getattr(settings, "PROMPT_CACHE_MAX_TOOLS", 8) or 0), 0)

    @staticmethod
    def _model_chain(model: Any) -> list[Any]:
        """Return a wrapper-safe model chain without following string model names."""
        chain: list[Any] = []
        seen: set[int] = set()
        current = model
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append(current)
            next_model = getattr(current, "bound", None)
            if next_model is None:
                next_model = getattr(current, "_bound", None)
            if next_model is None:
                candidate = getattr(current, "model", None)
                next_model = candidate if not isinstance(candidate, str) else None
            current = next_model
        return chain

    @classmethod
    def _runtime_provider(cls, model: Any) -> str | None:
        for current in cls._model_chain(model):
            metadata = getattr(current, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("lambchat_provider"):
                return str(metadata["lambchat_provider"])
        return None

    @classmethod
    def _runtime_model_name(cls, model: Any) -> str:
        for current in cls._model_chain(model):
            for attr in ("model_name", "model"):
                value = getattr(current, attr, None)
                if isinstance(value, str) and value:
                    return value
        return ""

    @staticmethod
    def _is_anthropic_model(model: Any) -> bool:
        """Return True when request.model is backed by langchain-anthropic."""
        for current in PromptCachingMiddleware._model_chain(model):
            cls = type(current)
            if cls.__module__.startswith("langchain_anthropic"):
                return True
        return False

    @staticmethod
    def _supports_minimax_explicit_cache(model_name: str) -> bool:
        """Return whether MiniMax documents Anthropic-style explicit caching."""
        name = model_name.strip().lower()
        return name == "minimax-m2" or name.startswith(("minimax-m2.", "minimax-m2-"))

    # ---- system message ---------------------------------------------------

    @staticmethod
    def _block_text(block: Any) -> str:
        if isinstance(block, dict):
            return str(block.get("text", ""))
        return str(block)

    @classmethod
    def _is_volatile_system_block(cls, block: Any) -> bool:
        """Return True for system blocks that are expected to change often."""
        text = cls._block_text(block).strip().lower()
        volatile_prefixes = (
            "<memory_index>",
            "## mcp tools (deferred)",
            "## user runtime context",
            "## active goal",
            "### auto mode",
        )
        return any(text.startswith(prefix) for prefix in volatile_prefixes)

    @classmethod
    def _cacheable_system_block_count(cls, system_message: Any) -> int:
        """Count the stable prefix before the first volatile system block."""
        blocks = _system_message_to_blocks(system_message)
        for i, block in enumerate(blocks):
            if cls._is_volatile_system_block(block):
                return i
        return len(blocks)

    @staticmethod
    def _cache_indices_for_stable_prefix(cacheable_count: int, max_cached_blocks: int) -> list[int]:
        """Use one cumulative breakpoint at the end of the stable prefix."""
        if cacheable_count <= 0 or max_cached_blocks <= 0:
            return []
        return [cacheable_count - 1]

    @staticmethod
    def _strip_block_cache_tags(block: Any) -> Any:
        if not isinstance(block, dict):
            return block
        cleaned = {key: value for key, value in block.items() if key != "cache_control"}
        extras = cleaned.get("extras")
        if isinstance(extras, dict) and "prompt_cache_breakpoint" in extras:
            cleaned_extras = {
                key: value for key, value in extras.items() if key != "prompt_cache_breakpoint"
            }
            if cleaned_extras:
                cleaned["extras"] = cleaned_extras
            else:
                cleaned.pop("extras", None)
        return cleaned

    @staticmethod
    def _replace_system_content(system_message: Any, blocks: list[Any]) -> Any:
        if isinstance(system_message, SystemMessage):
            return system_message.model_copy(update={"content": blocks})
        return SystemMessage(content=blocks)

    @staticmethod
    def _retag_system_message(
        system_message: Any, cache_control: dict, *, max_cached_blocks: int = 4
    ) -> Any:
        """Strip stale cache_control and tag the stable prefix before volatile blocks."""
        if system_message is None:
            return system_message

        blocks = _system_message_to_blocks(system_message)
        if not blocks:
            return system_message

        blocks = [PromptCachingMiddleware._strip_block_cache_tags(block) for block in blocks]

        if max_cached_blocks <= 0:
            return PromptCachingMiddleware._replace_system_content(system_message, blocks)

        cacheable_count = PromptCachingMiddleware._cacheable_system_block_count(
            SystemMessage(content=blocks)
        )
        if cacheable_count <= 0:
            return PromptCachingMiddleware._replace_system_content(system_message, blocks)

        for i in PromptCachingMiddleware._cache_indices_for_stable_prefix(
            cacheable_count, max_cached_blocks
        ):
            block = blocks[i]
            base = block if isinstance(block, dict) else {"type": "text", "text": str(block)}
            blocks[i] = {**base, "cache_control": cache_control}

        return PromptCachingMiddleware._replace_system_content(system_message, blocks)

    @staticmethod
    def _retag_openai_system_message(system_message: Any) -> Any:
        if system_message is None:
            return system_message
        blocks = [
            PromptCachingMiddleware._strip_block_cache_tags(block)
            for block in _system_message_to_blocks(system_message)
        ]
        cacheable_count = PromptCachingMiddleware._cacheable_system_block_count(
            PromptCachingMiddleware._replace_system_content(system_message, blocks)
        )
        if cacheable_count > 0:
            index = cacheable_count - 1
            block = blocks[index]
            base = block if isinstance(block, dict) else {"type": "text", "text": str(block)}
            raw_extras = base.get("extras")
            extras = dict(raw_extras) if isinstance(raw_extras, dict) else {}
            extras["prompt_cache_breakpoint"] = {"mode": "explicit"}
            blocks[index] = {**base, "extras": extras}
        return PromptCachingMiddleware._replace_system_content(system_message, blocks)

    # ---- tools ------------------------------------------------------------

    @staticmethod
    def _is_cacheable_tool(tool: Any) -> bool:
        if not isinstance(tool, BaseTool):
            return False
        extras = tool.extras or {}
        return not bool(extras.get(_PROMPT_CACHE_VOLATILE_TOOL_EXTRA))

    @classmethod
    def _cacheable_tool_count(cls, tools: list[Any] | None) -> int:
        return sum(1 for tool in tools or [] if cls._is_cacheable_tool(tool))

    @staticmethod
    def _retag_tools(
        tools: list[Any] | None, cache_control: dict, *, max_cached_tools: int = 4
    ) -> list[Any] | None:
        """Keep a stable tool prefix, then a sorted volatile session tail."""
        if not tools:
            return tools

        # Partition into volatile and stable, clean stale cache_control
        volatile_tools: list[Any] = []
        stable_tools: list[Any] = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                extras = tool.extras or {}
                if "cache_control" in extras:
                    tool = tool.model_copy(
                        update={"extras": {k: v for k, v in extras.items() if k != "cache_control"}}
                    )
                if PromptCachingMiddleware._is_cacheable_tool(tool):
                    stable_tools.append(tool)
                else:
                    volatile_tools.append(tool)
            else:
                volatile_tools.append(tool)

        volatile_tools.sort(key=lambda tool: str(getattr(tool, "name", "")))
        if max_cached_tools > 0:
            for segment in (stable_tools, volatile_tools):
                if segment and isinstance(segment[-1], BaseTool):
                    tool = segment[-1]
                    new_extras = {**(tool.extras or {}), "cache_control": cache_control}
                    segment[-1] = tool.model_copy(update={"extras": new_extras})

        return stable_tools + volatile_tools

    @staticmethod
    def _retag_latest_message(
        messages: list[BaseMessage] | tuple[BaseMessage, ...], cache_control: dict
    ) -> list[BaseMessage]:
        """Tag the last eligible text block for MiniMax explicit caching."""
        updated = list(messages)
        for index in range(len(updated) - 1, -1, -1):
            message = updated[index]
            content = message.content
            if isinstance(content, str):
                if not content:
                    continue
                blocks = [{"type": "text", "text": content, "cache_control": cache_control}]
                updated[index] = message.model_copy(update={"content": blocks})
                return updated
            if not isinstance(content, list):
                continue
            blocks = [PromptCachingMiddleware._strip_block_cache_tags(block) for block in content]
            for block_index in range(len(blocks) - 1, -1, -1):
                block = blocks[block_index]
                if isinstance(block, str) and block:
                    blocks[block_index] = {
                        "type": "text",
                        "text": block,
                        "cache_control": cache_control,
                    }
                    updated[index] = message.model_copy(update={"content": blocks})
                    return updated
                if isinstance(block, dict) and block.get("type") == "text":
                    blocks[block_index] = {**block, "cache_control": cache_control}
                    updated[index] = message.model_copy(update={"content": blocks})
                    return updated
        return updated

    # ---- main entry -------------------------------------------------------

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        model = getattr(request, "model", None)
        provider = self._runtime_provider(model)
        model_name = self._runtime_model_name(model)

        if provider == "openai" and _is_gpt_56_or_later(model_name):
            new_system = self._retag_openai_system_message(request.system_message)
            return await handler(request.override(system_message=new_system))

        is_anthropic = self._is_anthropic_model(model)
        if provider == "minimax" and not self._supports_minimax_explicit_cache(model_name):
            return await handler(request)
        if provider in {"anthropic", "minimax"}:
            effective_provider = provider
        elif provider is None and is_anthropic:
            effective_provider = "anthropic"
        else:
            return await handler(request)

        overrides: dict[str, Any] = {}
        system_enabled = self._max_cached_system_blocks > 0
        tools_enabled = self._max_cached_tools > 0

        if effective_provider == "anthropic":
            overrides["model_settings"] = {
                **(getattr(request, "model_settings", {}) or {}),
                "cache_control": self._AUTOMATIC_CACHE_CONTROL,
            }

        new_system = self._retag_system_message(
            request.system_message,
            self._CACHE_CONTROL,
            max_cached_blocks=int(system_enabled),
        )
        if new_system is not request.system_message:
            overrides["system_message"] = new_system

        new_tools = self._retag_tools(
            request.tools,
            self._CACHE_CONTROL,
            max_cached_tools=int(tools_enabled),
        )
        if new_tools is not request.tools:
            overrides["tools"] = new_tools

        if effective_provider == "minimax":
            messages = getattr(request, "messages", ()) or ()
            new_messages = self._retag_latest_message(messages, self._CACHE_CONTROL)
            if list(messages) != new_messages:
                overrides["messages"] = new_messages

        explicit_breakpoints = (
            int(system_enabled and self._cacheable_system_block_count(request.system_message) > 0)
            + int(tools_enabled and self._cacheable_tool_count(request.tools) > 0)
            + int(
                tools_enabled
                and any(not self._is_cacheable_tool(tool) for tool in request.tools or [])
            )
            + int(effective_provider == "minimax" and bool(getattr(request, "messages", ())))
        )
        total_breakpoints = explicit_breakpoints + int(effective_provider == "anthropic")
        if total_breakpoints > _MAX_ANTHROPIC_CACHE_BREAKPOINTS:
            raise RuntimeError("prompt_cache_breakpoint_budget_exceeded")
        logger.debug(
            "[PromptCache] provider=%s explicit=%d total=%d",
            effective_provider,
            explicit_breakpoints,
            total_breakpoints,
        )

        if overrides:
            request = request.override(**overrides)

        return await handler(request)

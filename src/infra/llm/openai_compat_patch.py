"""Compatibility patches for OpenAI-compatible chat providers."""

from __future__ import annotations

import json
from typing import Any


def apply_openai_compatible_patches() -> None:
    """Normalize non-standard OpenAI-compatible chat completion responses."""
    import langchain_openai.chat_models.base as _base

    target_cls = getattr(_base, "BaseChatOpenAI", None)
    if target_cls is None:
        return

    current = target_cls._create_chat_result
    if getattr(current, "_lambchat_openai_compat_patch_applied", False):
        return

    original = current

    def _patched_create_chat_result(
        self,
        response: Any,
        generation_info: dict | None = None,
    ):
        if isinstance(response, str):
            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return original(self, parsed, generation_info)

            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(content=response),
                        generation_info=generation_info,
                    )
                ]
            )

        return original(self, response, generation_info)

    _patched_create_chat_result._lambchat_openai_compat_patch_applied = True  # type: ignore[attr-defined]
    target_cls._create_chat_result = _patched_create_chat_result

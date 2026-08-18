"""Shared private helpers for middleware modules."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage


def _normalize_prompt_text(text: str) -> str:
    """Normalize injected prompt sections so equivalent content has the same shape."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def _system_message_to_blocks(system_message: Any) -> list[Any]:
    """Convert a system message payload into mutable content blocks."""
    if system_message is None:
        return []

    content = getattr(system_message, "content", None)
    if content is None:
        return []

    if isinstance(content, str):
        normalized = _normalize_prompt_text(content)
        return [{"type": "text", "text": normalized}] if normalized else []

    if isinstance(content, list):
        return list(content)

    return []


def _append_system_text_block(system_message: Any, text: str) -> SystemMessage:
    """Append a deterministic text block to the system message."""
    normalized = _normalize_prompt_text(text)
    blocks = _system_message_to_blocks(system_message)
    if normalized:
        blocks.append({"type": "text", "text": normalized})
    return SystemMessage(content=blocks)

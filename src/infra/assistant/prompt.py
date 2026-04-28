"""Assistant prompt helpers."""

from __future__ import annotations

from typing import Any


def build_assistant_prompt_sections(
    assistant_prompt: str = "",
    skills_prompt: str = "",
    memory_guide: str = "",
) -> tuple[str, ...]:
    """Build deterministic tail prompt sections."""
    return tuple(section for section in (assistant_prompt, skills_prompt, memory_guide) if section)


def build_system_prompt_with_assistant(
    base_system_prompt: str,
    assistant_prompt: str = "",
) -> str:
    """Merge assistant preset into the base system prompt for better cache locality."""
    if not assistant_prompt:
        return base_system_prompt
    return f"{base_system_prompt.rstrip()}\n\n{assistant_prompt.strip()}"


def build_runtime_assistant_prompt_summary(
    assistant_name: str = "",
    assistant_prompt: str = "",
    source: str = "none",
) -> str:
    """Build a compact debug summary for assistant prompt injection."""
    effective_name = assistant_name.strip() or "none"
    return f"assistant={effective_name} source={source} prompt_chars={len(assistant_prompt)}"


def resolve_runtime_assistant_prompt(
    assistant_prompt: str = "",
    agent_options: dict[str, Any] | None = None,
) -> str:
    """Resolve assistant prompt from explicit config or agent_options snapshot."""
    if assistant_prompt:
        return assistant_prompt

    option_prompt = (agent_options or {}).get("_assistant_prompt")
    return option_prompt if isinstance(option_prompt, str) else ""

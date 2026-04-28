"""Assistant prompt helpers."""

from __future__ import annotations


def build_assistant_prompt_sections(
    assistant_prompt: str = "",
    skills_prompt: str = "",
    memory_guide: str = "",
) -> tuple[str, ...]:
    """Build prompt sections in assistant -> skills -> memory order."""
    return tuple(section for section in (assistant_prompt, skills_prompt, memory_guide) if section)

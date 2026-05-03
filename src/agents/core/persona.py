"""Persona prompt helpers."""


def build_persona_prompt_section(system_prompt: str | None) -> str:
    """Build the persona preset section injected into the system prompt."""
    prompt = (system_prompt or "").strip()
    if not prompt:
        return ""
    return f"## Persona Preset\n\n{prompt}"

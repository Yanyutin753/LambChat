from typing import Any

SUPPORTED_THINKING_LEVELS = frozenset({"low", "medium", "high", "max"})


def normalize_thinking_level(value: Any) -> str:
    """Normalize legacy and current thinking option values."""
    if isinstance(value, bool):
        return "medium" if value else "off"

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in SUPPORTED_THINKING_LEVELS or normalized == "off":
            return normalized
        if normalized in {"enabled", "enable", "on", "true"}:
            return "medium"
        if normalized in {"disabled", "disable", "false", "none"}:
            return "off"

    return "off"


def build_thinking_config(agent_options: dict[str, Any] | None) -> dict[str, str] | None:
    """Build provider thinking config from agent options."""
    level = normalize_thinking_level((agent_options or {}).get("enable_thinking"))
    if level == "off":
        return None

    return {"type": "enabled", "level": level}

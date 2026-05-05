from typing import Any

SUPPORTED_THINKING_LEVELS = frozenset({"low", "medium", "high", "max"})

# budget_tokens 映射表 (用于 Anthropic 协议)
BUDGET_TOKENS_MAP: dict[str, int] = {
    "low": 1024,
    "medium": 8192,
    "high": 32768,
    "max": 65536,
}


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


def build_thinking_config(agent_options: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build provider thinking config from agent options.

    Returns a dict with:
      - "level": normalized level string (for Google protocol)
      - "budget_tokens": mapped token budget (for Anthropic protocol)
    """
    level = normalize_thinking_level((agent_options or {}).get("enable_thinking"))
    if level == "off":
        return None

    return {
        "type": "enabled",
        "level": level,
        "budget_tokens": BUDGET_TOKENS_MAP.get(level, 8192),
    }

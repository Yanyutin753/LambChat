"""Shared types and constants for LangChain agent stream events."""

from typing import Any, TypeAlias

from langchain_core.runnables.schema import CustomStreamEvent, StandardStreamEvent

StreamEvent: TypeAlias = StandardStreamEvent | CustomStreamEvent

TOOL_TASK = "task"

TOOL_ERROR_INDICATORS = frozenset(
    (
        "error:",
        "validationerror",
        "[mcp tool error]",
        "failed",
        "command failed",
        "exception",
        "traceback",
    )
)


def get_value(obj: Any, key: str, default: Any = 0) -> Any:
    """Read a value from either a dict-like object or an attribute object."""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

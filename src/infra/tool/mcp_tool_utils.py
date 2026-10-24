"""Pure argument normalization and retry classification for MCP tool calls."""

import json
from typing import Any


def _schema_allows_array(value_schema: Any) -> bool:
    """Return whether a JSON-schema fragment accepts an array value."""
    if not isinstance(value_schema, dict):
        return False
    schema_type = value_schema.get("type")
    if schema_type == "array" or (isinstance(schema_type, list) and "array" in schema_type):
        return True
    return any(
        _schema_allows_array(option)
        for keyword in ("anyOf", "oneOf")
        for option in value_schema.get(keyword, [])
    )


def _normalize_json_array_args(kwargs: dict[str, Any], args_schema: Any = None) -> dict[str, Any]:
    """Coerce JSON-array-string arguments back to real lists.

    Some callers/LLMs serialize list arguments as a JSON array literal string
    (e.g. ``urls='["https://..."]'``), which remote MCP servers reject as an
    invalid value. Parse such values back to a list (issue #198).
    """
    schema = args_schema
    if schema is not None and not isinstance(schema, dict):
        to_json_schema = getattr(schema, "model_json_schema", None)
        schema = to_json_schema() if callable(to_json_schema) else None
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

    normalized: dict[str, Any] = {}
    for key, value in kwargs.items():
        if (
            _schema_allows_array(properties.get(key))
            and isinstance(value, str)
            and value.lstrip().startswith("[")
        ):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                value = parsed
        normalized[key] = value
    return normalized


def _is_retryable_tool_error(error: Exception) -> bool:
    """判断错误是否可重试"""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # 可重试的错误模式
    retryable_patterns = [
        "429",  # rate limit
        "503",  # service unavailable
        "502",  # bad gateway
        "timeout",
        "connection",
        "network",
        "reset",
        "refused",
        "unavailable",
        # MCP streamable-http transport failures: the SSE GET stream drops
        # mid-run and the subsequent tool POST fails. Retry so the client
        # re-establishes the session (issue #198).
        "streamable http",
        "posting to endpoint",
        "stream disconnected",
    ]

    # 可重试的异常类型
    retryable_types = [
        "timeouterror",
        "connectionerror",
        "connectionreseterror",
        "brokenpipeerror",
    ]

    # 检查错误消息
    if any(pattern in error_str for pattern in retryable_patterns):
        return True

    # 检查异常类型
    if any(rt in error_type for rt in retryable_types):
        return True

    # 空错误消息可能是临时问题，也重试
    if not error_str or error_str == "(empty error message)":
        return True

    return False

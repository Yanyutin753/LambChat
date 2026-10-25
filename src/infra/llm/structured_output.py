"""Negotiate structured output per model instance, without model-name allowlists."""

from __future__ import annotations

import weakref
from collections import OrderedDict
from typing import Any

from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

_preferred_methods: OrderedDict[
    tuple[int, type[BaseModel]], tuple[weakref.ReferenceType[Any], str]
] = OrderedDict()
_MAX_PREFERRED_METHODS = 128


def structured_output_methods(model: Any, schema: type[BaseModel]) -> tuple[str, ...]:
    """Only the wire protocol limits candidates; a successful request sets preference."""
    protocol = str(getattr(model, "_llm_type", ""))
    methods = (
        ("json_schema", "function_calling")
        if "anthropic" in protocol
        else ("json_schema", "json_mode", "function_calling")
    )
    key = (id(model), schema)
    cached = _preferred_methods.get(key)
    if cached is not None:
        if cached[0]() is model and cached[1] in methods:
            _preferred_methods.move_to_end(key)
            return (cached[1], *(method for method in methods if method != cached[1]))
        _preferred_methods.pop(key, None)
    return methods


def remember_structured_output_method(model: Any, schema: type[BaseModel], method: str) -> None:
    # Instances change with channel/config changes; neither names nor account data form the key.
    try:
        reference = weakref.ref(model)
    except TypeError:
        return
    key = (id(model), schema)
    _preferred_methods[key] = (reference, method)
    _preferred_methods.move_to_end(key)
    while len(_preferred_methods) > _MAX_PREFERRED_METHODS:
        _preferred_methods.popitem(last=False)


def bind_structured_output(model: Any, schema: type[BaseModel], method: str) -> Any:
    if method == "json_mode" and "google" in str(getattr(model, "_llm_type", "")):
        # Google's SDK aliases json_mode to json_schema; MIME-only JSON needs an explicit binding.
        return model.bind(response_mime_type="application/json") | RunnableLambda(
            lambda raw: {"raw": raw, "parsed": None}
        )
    return model.with_structured_output(schema, method=method, include_raw=True)


def is_unsupported_structured_output(exc: Exception) -> bool:
    """Do not confuse credentials, quotas, network faults or unrelated bad input with capability."""
    status = (
        getattr(exc, "status_code", None)
        or getattr(getattr(exc, "response", None), "status_code", None)
        or getattr(exc, "code", None)
    )
    if status is not None and status not in (400, 422):
        return False
    if isinstance(exc, NotImplementedError):
        return True
    if status is None and not isinstance(exc, (ValueError, TypeError)):
        return False
    message = str(exc).lower()
    parameters = (
        "response_format",
        "json_schema",
        "json_mode",
        "json_object",
        "structured output",
        "output_config",
        "output_format",
        "response_json_schema",
        "response_mime_type",
        "responsemimetype",
        "responseformat",
        "tool_choice",
        "tool choice",
        "toolchoice",
        "function_calling",
        "function calling",
        "tools",
        "schema",
    )
    rejections = (
        "unsupported",
        "not support",
        "not implemented",
        "not allowed",
        "not permitted",
        "unknown",
        "unrecognized",
        "unexpected",
        "invalid",
        "incompatible",
        "only",
        "must",
        "not enabled",
        "不支持",
        "不允许",
    )
    return any(parameter in message for parameter in parameters) and any(
        rejection in message for rejection in rejections
    )


def is_terminal_structured_response(raw: Any) -> bool:
    """Changing the output format cannot repair a refusal or an exhausted output budget."""
    metadata = getattr(raw, "response_metadata", {}) or {}
    incomplete = metadata.get("incomplete_details") or {}
    extra = getattr(raw, "additional_kwargs", {}) or {}
    return bool(
        extra.get("refusal")
        or metadata.get("stop_reason") in ("max_tokens", "refusal")
        or metadata.get("finish_reason") in ("length", "content_filter", "SAFETY", "MAX_TOKENS")
        or isinstance(incomplete, dict)
        and incomplete.get("reason") == "max_output_tokens"
    )

"""Monkey-patch langchain-openai to preserve provider reasoning content safely.

Some OpenAI-compatible providers return ``reasoning_content`` in streaming
deltas, but ``langchain-openai`` does not preserve this field by default.
These patches bridge the gap by:

1. **Inbound** — copying ``reasoning_content`` from the raw delta dict into
   ``AIMessageChunk.additional_kwargs`` so that ``langchain_core`` can surface
   it via ``content_blocks``.
2. **Outbound** — only re-sending ``reasoning_content`` when continuing a
   DeepSeek tool-call turn, which matches the provider contract without leaking
   the field into ordinary assistant turns or other OpenAI-compatible backends.
"""


def is_deepseek_thinking_model(name: str) -> bool:
    return name.lower().startswith(("deepseek-flash", "deepseek-v4"))


def _is_deepseek_message(message) -> bool:
    response_metadata = getattr(message, "response_metadata", {})
    if not isinstance(response_metadata, dict):
        return False

    model_name = str(
        response_metadata.get("model_name") or response_metadata.get("model") or ""
    ).lower()
    return model_name.startswith("deepseek")


def _has_tool_continuation(message) -> bool:
    if getattr(message, "tool_calls", None) or getattr(message, "invalid_tool_calls", None):
        return True

    additional_kwargs = getattr(message, "additional_kwargs", {})
    return bool(additional_kwargs.get("tool_calls") or additional_kwargs.get("function_call"))


def apply_reasoning_patches() -> None:
    import langchain_openai.chat_models.base as _base

    if getattr(_base, "_lambchat_reasoning_patch_applied", False):
        return

    _orig_convert_delta = _base._convert_delta_to_message_chunk
    _orig_convert_msg = _base._convert_message_to_dict
    _orig_convert_dict = _base._convert_dict_to_message

    def _patched_convert_delta(_dict, default_class):
        result = _orig_convert_delta(_dict, default_class)
        rc = _dict.get("reasoning_content") if isinstance(_dict, dict) else None
        if rc:
            result.additional_kwargs["reasoning_content"] = rc
        return result

    def _patched_convert_dict(data):
        result = _orig_convert_dict(data)
        if data.get("role") == "assistant" and data.get("reasoning_content"):
            result.additional_kwargs["reasoning_content"] = data["reasoning_content"]
        return result

    def _patched_convert_msg(message, api="chat/completions"):
        from langchain_core.messages import AIMessage

        result = _orig_convert_msg(message, api=api)
        if isinstance(message, AIMessage):
            rc = message.additional_kwargs.get("reasoning_content")
            if rc and _is_deepseek_message(message) and _has_tool_continuation(message):
                result["reasoning_content"] = rc
        return result

    _base._convert_delta_to_message_chunk = _patched_convert_delta
    _base._convert_message_to_dict = _patched_convert_msg
    _base._convert_dict_to_message = _patched_convert_dict
    setattr(_base, "_lambchat_reasoning_patch_applied", True)  # type: ignore[attr-defined]

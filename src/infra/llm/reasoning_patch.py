"""Monkey-patch langchain-openai to preserve provider reasoning content safely.

Some OpenAI-compatible providers return ``reasoning_content`` in streaming
deltas, but ``langchain-openai`` does not preserve this field by default.
These patches bridge the gap by:

1. **Inbound** — copying ``reasoning_content`` from the raw delta dict into
   ``AIMessageChunk.additional_kwargs`` so that ``langchain_core`` can surface
   it via ``content_blocks``.
2. **Outbound** — re-sending ``reasoning_content`` in assistant history:
   - GLM-4.5+/GLM-5 thinking models on every turn: their thinking mode
     rejects the next request with 400 "The `reasoning_text` in the thinking
     mode must be passed back to the API" once history carries an assistant
     message without it (production 2026-10-10).
   - DeepSeek only when continuing a tool-call turn, matching that
     provider's documented contract, so the field does not leak into
     ordinary assistant turns or other OpenAI-compatible backends.
"""

from src.infra.llm.providers import is_zhipu_thinking_model


def is_deepseek_thinking_model(name: str) -> bool:
    return name.lower().startswith(("deepseek-flash", "deepseek-v4"))


def reasoning_text_from_message(message) -> str:
    if text := message.additional_kwargs.get("reasoning_content"):
        return text
    if not isinstance(message.content, list):
        return ""
    parts = []
    for block in message.content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "thinking":
            parts.append(block.get("thinking", ""))
        elif block.get("type") == "reasoning":
            parts.append(
                block.get("reasoning")
                or "".join(
                    part.get("text", "")
                    for part in block.get("content", [])
                    if isinstance(part, dict) and part.get("type") == "reasoning_text"
                )
            )
    return "".join(parts)


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


def _model_name_of(message) -> str:
    response_metadata = getattr(message, "response_metadata", {})
    if not isinstance(response_metadata, dict):
        return ""
    return str(response_metadata.get("model_name") or response_metadata.get("model") or "").lower()


def _should_replay_reasoning_content(message) -> bool:
    if is_zhipu_thinking_model(_model_name_of(message)):
        # GLM 思考系（glm-4.5+/glm-5）思考模式下历史 assistant 消息必须
        # 回传 reasoning_content，普通轮即触发，与工具续轮无关。
        return True
    return _is_deepseek_message(message) and _has_tool_continuation(message)


def apply_reasoning_patches() -> None:
    import langchain_openai.chat_models.base as _base

    if getattr(_base, "_lambchat_reasoning_patch_applied", False):
        return

    _orig_convert_delta = _base._convert_delta_to_message_chunk
    _orig_convert_msg = _base._convert_message_to_dict
    _orig_convert_dict = _base._convert_dict_to_message
    _orig_responses_chunk = _base._convert_responses_chunk_to_generation_chunk
    _orig_responses_result = _base._construct_lc_result_from_responses_api

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
            if rc and _should_replay_reasoning_content(message):
                result["reasoning_content"] = rc
        return result

    def _patched_responses_chunk(chunk, *args, **kwargs):
        if chunk.type != "response.reasoning_text.delta":
            return _orig_responses_chunk(chunk, *args, **kwargs)
        from types import SimpleNamespace

        converted = SimpleNamespace(
            type="response.reasoning_summary_text.delta",
            output_index=chunk.output_index,
            summary_index=chunk.content_index,
            delta=chunk.delta,
        )
        result = _orig_responses_chunk(converted, *args, **kwargs)
        if result[3] is not None:
            for block in result[3].message.content:
                if isinstance(block, dict):
                    block.pop("summary", None)
                    block["reasoning"] = chunk.delta
        return result

    def _patched_responses_result(response, *args, **kwargs):
        result = _orig_responses_result(response, *args, **kwargs)
        for generation in result.generations:
            message = generation.message
            if isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, dict) and block.get("type") == "reasoning":
                        text = "".join(
                            part.get("text", "")
                            for part in block.get("content", [])
                            if isinstance(part, dict) and part.get("type") == "reasoning_text"
                        )
                        if text:
                            block["reasoning"] = text
        return result

    _base._convert_responses_chunk_to_generation_chunk = _patched_responses_chunk
    _base._construct_lc_result_from_responses_api = _patched_responses_result
    _base._convert_delta_to_message_chunk = _patched_convert_delta
    _base._convert_message_to_dict = _patched_convert_msg
    _base._convert_dict_to_message = _patched_convert_dict
    setattr(_base, "_lambchat_reasoning_patch_applied", True)  # type: ignore[attr-defined]

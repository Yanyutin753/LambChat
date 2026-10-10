from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.messages.tool import tool_call

from src.infra.llm.reasoning_patch import apply_reasoning_patches


def test_reasoning_content_is_not_sent_back_for_plain_deepseek_turn() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="final answer",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "deepseek-reasoner"},
    )

    payload = openai_base._convert_message_to_dict(message)

    assert "reasoning_content" not in payload


def test_reasoning_content_is_sent_for_deepseek_tool_continuations() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "deepseek-reasoner"},
        tool_calls=[tool_call(name="search", args={}, id="call-1")],
    )

    payload = openai_base._convert_message_to_dict(message)

    assert payload["reasoning_content"] == "thinking"


def test_reasoning_content_is_not_sent_to_non_deepseek_models() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "gpt-4o-mini"},
        tool_calls=[tool_call(name="search", args={}, id="call-1")],
    )

    payload = openai_base._convert_message_to_dict(message)

    assert "reasoning_content" not in payload


def test_non_streaming_reasoning_is_preserved_for_history():
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = openai_base._convert_dict_to_message(
        {"role": "assistant", "content": "2", "reasoning_content": "actual reasoning"}
    )
    assert message.additional_kwargs["reasoning_content"] == "actual reasoning"

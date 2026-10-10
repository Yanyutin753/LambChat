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


def test_responses_plain_reasoning_delta_is_streamed():
    from types import SimpleNamespace

    import langchain_openai.chat_models.base as base

    apply_reasoning_patches()
    event = SimpleNamespace(
        type="response.reasoning_text.delta",
        output_index=0,
        content_index=0,
        delta="actual thought",
    )
    result = base._convert_responses_chunk_to_generation_chunk(event, -1, -1, -1)
    assert result[3] is not None
    assert result[3].message.content[0]["reasoning"] == "actual thought"


def test_responses_nonstreaming_plain_reasoning_is_preserved():
    import langchain_openai.chat_models.base as base
    from openai.types.responses import Response, ResponseReasoningItem

    apply_reasoning_patches()
    item = ResponseReasoningItem.model_construct(
        id="rs_1",
        type="reasoning",
        summary=[],
        content=[{"type": "reasoning_text", "text": "actual thought"}],
    )
    response = Response.model_construct(
        id="resp_1",
        model="deepseek-flash",
        output=[item],
        error=None,
        usage=None,
        service_tier=None,
        text=None,
    )
    message = base._construct_lc_result_from_responses_api(response).generations[0].message
    assert message.content[0]["reasoning"] == "actual thought"
# ── GLM 思考系回传（生产 2026-10-10）────────────────────────────────────────
# GLM-4.5+/GLM-5 系在 OpenAI 协议线格式（含任意中转）开思考模式后，历史
# assistant 消息必须回传 reasoning_content，第二轮起 400：
# "The `reasoning_text` in the thinking mode must be passed back to the API"。
# 与 DeepSeek 不同，普通轮（无工具续轮）同样要求回传。


def test_reasoning_content_is_sent_back_for_zhipu_thinking_plain_turn() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="final answer",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "glm-5.3-flash"},
    )

    payload = openai_base._convert_message_to_dict(message)

    assert payload["reasoning_content"] == "thinking"


def test_reasoning_content_is_sent_back_for_zhipu_thinking_tool_turn() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "glm-4.6"},
        tool_calls=[tool_call(name="search", args={}, id="call-1")],
    )

    payload = openai_base._convert_message_to_dict(message)

    assert payload["reasoning_content"] == "thinking"


def test_reasoning_content_not_sent_for_legacy_non_thinking_glm() -> None:
    import langchain_openai.chat_models.base as openai_base

    apply_reasoning_patches()
    message = AIMessage(
        content="hi",
        additional_kwargs={"reasoning_content": "thinking"},
        response_metadata={"model_name": "glm-4-plus"},
    )

    payload = openai_base._convert_message_to_dict(message)

    assert "reasoning_content" not in payload

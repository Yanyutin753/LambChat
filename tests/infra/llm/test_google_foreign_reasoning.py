"""Foreign-provider reasoning must survive switches onto the Gemini lane.

langchain_google_genai drops reasoning blocks whose ``model_provider`` is
foreign ("Dropping reasoning block from provider ..."), so a session that
produced thinking on the anthropic/openai lanes loses its multi-turn
reasoning context once a later turn lands on the Gemini lane. The lane is
expected to downgrade foreign reasoning to plain text parts instead.
"""

import logging
from copy import deepcopy

from langchain_core.messages import AIMessage, HumanMessage

from src.infra.llm.client import LLMClient
from src.infra.llm.google_chat import _downgrade_foreign_reasoning


def google_model():
    return LLMClient._create_model("google", "gemini-4-argon", api_key="test")


def model_part_texts(request):
    return [
        part.text
        for content in request["contents"]
        if content.role == "model"
        for part in content.parts or []
        if getattr(part, "text", None)
    ]


def test_anthropic_thinking_replays_as_text_on_google_lane(caplog):
    model = google_model()
    message = AIMessage(
        content=[
            {"type": "thinking", "thinking": "step one, then step two", "signature": "sig"},
            {"type": "text", "text": "The answer is 2"},
        ],
        response_metadata={"model_provider": "anthropic"},
    )
    messages = [HumanMessage(content="1+1"), message, HumanMessage(content="go on")]
    original = deepcopy(messages)
    with caplog.at_level(logging.WARNING, logger="langchain_google_genai.chat_models"):
        request = model._prepare_request(messages)
    texts = model_part_texts(request)
    assert "step one, then step two" in texts
    assert "The answer is 2" in texts
    assert "Dropping reasoning block" not in caplog.text
    assert messages == original


def test_openai_reasoning_content_replays_as_text_on_google_lane():
    model = google_model()
    message = AIMessage(
        content="The answer is 2",
        additional_kwargs={"reasoning_content": "glm chain of thought"},
        response_metadata={"model_provider": "openai"},
    )
    request = model._prepare_request(
        [HumanMessage(content="1+1"), message, HumanMessage(content="go on")]
    )
    texts = model_part_texts(request)
    assert "glm chain of thought" in texts
    assert "The answer is 2" in texts


def test_native_gemini_thinking_is_not_downgraded():
    model = google_model()
    message = AIMessage(
        content=[
            {"type": "thinking", "thinking": "native thought"},
            {"type": "text", "text": "2"},
        ],
        response_metadata={"model_provider": "google_genai"},
    )
    request = model._prepare_request(
        [HumanMessage(content="1+1"), message, HumanMessage(content="go on")]
    )
    parts = [
        part
        for content in request["contents"]
        if content.role == "model"
        for part in content.parts or []
    ]
    assert [part.text for part in parts if part.thought] == ["native thought"]
    assert [part.text for part in parts if not part.thought] == ["2"]


def test_plain_history_passes_through_unchanged():
    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="hello", response_metadata={"model_provider": "anthropic"}),
        HumanMessage(content="bye"),
    ]
    assert _downgrade_foreign_reasoning(messages) == messages


def test_empty_foreign_thinking_is_dropped_without_placeholder():
    message = AIMessage(
        content=[
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "2"},
        ],
        response_metadata={"model_provider": "anthropic"},
    )
    normalized = _downgrade_foreign_reasoning([message])[0]
    assert normalized.content == [{"type": "text", "text": "2"}]

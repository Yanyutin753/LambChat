"""OpenAI-protocol Responses API wire-format switch.

Per-model `api_format` ("chat_completions" | "responses") with a global
default setting (LLM_OPENAI_API_FORMAT). Only OpenAI-protocol providers can
switch, and chat-completions-only body fields (zhipu `thinking`) must never
leak into a /v1/responses payload.
"""

import pytest

from src.infra.llm.client import LLMClient
from src.kernel.config import settings

ENABLED = {"type": "enabled", "level": "high", "budget_tokens": 8192}


def _openai_model(
    provider: str,
    model_name: str,
    *,
    thinking: dict | None = None,
    api_format: str | None = None,
):
    return LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
        thinking=thinking,
        api_format=api_format,
    )


@pytest.fixture(autouse=True)
def _isolate_model_cache():
    LLMClient._model_cache.clear()
    yield
    LLMClient._model_cache.clear()


# ── wire-format assembly ──────────────────────────────────────────────────


def test_per_model_responses_format_enables_responses_api() -> None:
    model = _openai_model("openai", "gpt-5.2", api_format="responses")
    assert model.use_responses_api is True


def test_chat_completions_remains_the_default_format() -> None:
    model = _openai_model("openai", "gpt-5.2")
    assert model.use_responses_api is False


def test_explicit_chat_completions_overrides_responses_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_OPENAI_API_FORMAT", "responses", raising=False)
    model = _openai_model("openai", "gpt-5.2", api_format="chat_completions")
    assert model.use_responses_api is False


def test_settings_default_responses_applies_when_model_format_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_OPENAI_API_FORMAT", "responses", raising=False)
    model = _openai_model("openai", "gpt-5.2")
    assert model.use_responses_api is True


def test_invalid_format_value_falls_back_to_chat_completions(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_OPENAI_API_FORMAT", "bogus", raising=False)
    model = _openai_model("openai", "gpt-5.2")
    assert model.use_responses_api is False


def test_non_openai_protocols_ignore_responses_format() -> None:
    anthropic = _openai_model("anthropic", "claude-sonnet-4-5", api_format="responses")
    assert getattr(anthropic, "use_responses_api", False) is False

    google = _openai_model("google", "gemini-2.5-pro", api_format="responses")
    assert getattr(google, "use_responses_api", False) is False


def test_zhipu_thinking_body_skipped_in_responses_mode() -> None:
    responses_model = _openai_model("zhipu", "glm-4.6", thinking=ENABLED, api_format="responses")
    assert responses_model.use_responses_api is True
    assert "thinking" not in responses_model.model_kwargs

    chat_model = _openai_model("zhipu", "glm-4.6", thinking=ENABLED)
    assert chat_model.model_kwargs.get("thinking") == {"type": "enabled"}


def test_reasoning_effort_survives_in_responses_mode() -> None:
    # langchain-openai maps reasoning_effort → reasoning.effort on /v1/responses
    model = _openai_model("openai", "gpt-5.2", thinking=ENABLED, api_format="responses")
    assert model.reasoning_effort == "high"


# ── get_model resolution ───────────────────────────────────────────────────


async def test_get_model_reads_api_format_from_model_config() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "openai/gpt-5.2",
            "label": "GPT",
            "provider": "openai",
            "api_key": "sk-test",
            "api_format": "responses",
        },
        use_model_config=False,
    )
    assert model.use_responses_api is True


async def test_get_model_caches_formats_separately() -> None:
    chat = await LLMClient.get_model(
        model="openai/gpt-5.2", api_key="sk-test", use_model_config=False
    )
    responses = await LLMClient.get_model(
        model="openai/gpt-5.2",
        api_key="sk-test",
        use_model_config=False,
        api_format="responses",
    )
    assert chat is not responses
    assert chat.use_responses_api is False
    assert responses.use_responses_api is True

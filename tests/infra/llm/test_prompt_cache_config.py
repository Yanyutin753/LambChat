import pytest

from src.infra.llm.client import LLMClient


def test_openai_gpt_54_uses_legacy_cache_hints_and_provider_metadata() -> None:
    model = LLMClient._create_model(
        "openai",
        "gpt-5.4",
        temperature=0.7,
        api_key="sk-test",
    )

    assert model.model_kwargs["prompt_cache_key"] == "lambchat:openai:gpt-5.4"
    assert model.model_kwargs["prompt_cache_retention"] == "24h"
    assert model.metadata["lambchat_provider"] == "openai"


@pytest.mark.parametrize("model_name", ["gpt-5.6", "gpt-5.6-codex", "gpt-6"])
def test_openai_gpt_56_and_future_gpt_families_use_explicit_cache_mode(
    model_name: str,
) -> None:
    model = LLMClient._create_model(
        "openai",
        model_name,
        temperature=0.7,
        api_key="sk-test",
    )

    assert model.model_kwargs["prompt_cache_key"] == f"lambchat:openai:{model_name}"
    assert model.prompt_cache_options == {"mode": "explicit"}
    assert "prompt_cache_retention" not in model.model_kwargs


@pytest.mark.parametrize(
    ("provider", "model_name"),
    [
        ("deepseek", "deepseek-chat"),
        ("qwen", "qwen-max"),
        ("moonshot", "moonshot-v1"),
    ],
)
def test_openai_compatible_providers_do_not_receive_openai_cache_extensions(
    provider: str,
    model_name: str,
) -> None:
    model = LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
        metadata={"request_scope": "test"},
    )

    assert "prompt_cache_key" not in model.model_kwargs
    assert "prompt_cache_retention" not in model.model_kwargs
    assert model.prompt_cache_options is None
    assert model.metadata["request_scope"] == "test"
    assert model.metadata["lambchat_provider"] == provider


def test_unknown_openai_model_uses_key_without_speculative_retention() -> None:
    model = LLMClient._create_model(
        "openai",
        "o4-mini",
        temperature=0.7,
        api_key="sk-test",
    )

    assert model.model_kwargs["prompt_cache_key"] == "lambchat:openai:o4-mini"
    assert "prompt_cache_retention" not in model.model_kwargs

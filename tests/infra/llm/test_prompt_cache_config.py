import pytest

from src.infra.llm.client import LLMClient


@pytest.mark.parametrize(
    ("provider", "model_name"),
    [
        ("openai", "gpt-5.4"),
        ("openai", "gpt-5.6"),
        ("openai", "o4-mini"),
        ("deepseek", "deepseek-chat"),
    ],
)
def test_model_construction_does_not_add_lambchat_prompt_cache_policy(
    provider: str,
    model_name: str,
) -> None:
    model = LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
    )

    assert "prompt_cache_key" not in model.model_kwargs
    assert "prompt_cache_retention" not in model.model_kwargs
    assert getattr(model, "prompt_cache_options", None) is None
    assert "lambchat_provider" not in (model.metadata or {})


def test_model_construction_preserves_caller_metadata_without_cache_routing_metadata() -> None:
    caller_metadata = {"request_scope": "test"}
    model = LLMClient._create_model(
        "openai",
        "gpt-5.4",
        temperature=0.7,
        api_key="sk-test",
        metadata=caller_metadata,
    )

    assert {key: model.metadata[key] for key in caller_metadata} == caller_metadata
    assert "lambchat_provider" not in (model.metadata or {})

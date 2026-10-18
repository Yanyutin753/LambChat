"""GLM output defaults must leave enhanced reasoning room to call tools."""

import pytest
from langchain_core.messages import HumanMessage

from src.agents.core.thinking import build_thinking_config
from src.infra.llm.client import LLMClient


def _model(name="glm-5.3", level=None, **kwargs):
    return LLMClient._create_model(
        "anthropic",
        name,
        api_key="test-only",
        thinking=build_thinking_config(
            {} if level is None else {"enable_thinking": level}, default_level="medium"
        ),
        **kwargs,
    )


@pytest.mark.parametrize("name", ["glm-5.3", "glm-5.3-flash", "glm-5.3-flash[1m]"])
@pytest.mark.parametrize("level", [None, "medium", "high", "max"])
def test_enhanced_glm_default_budget_reaches_final_protocol(name, level):
    payload = _model(name, level)._get_request_payload([HumanMessage(content="Construct only")])
    assert payload["max_tokens"] == 65536
    assert payload["output_config"]["effort"] == ("max" if level == "max" else "high")


@pytest.mark.parametrize("limit", [4096, 16384, 32768, 65536])
def test_explicit_output_limit_is_preserved(limit):
    assert _model(max_tokens=limit).max_tokens == limit


@pytest.mark.parametrize("name", ["claude-sonnet-4-5", "glm-5.2", "glm-5.30"])
def test_other_model_defaults_remain_unchanged(name):
    assert _model(name).max_tokens == 32768


def test_low_and_unconfigured_thinking_keep_existing_output_budget():
    assert _model(level="low").max_tokens == 32768
    assert LLMClient._create_model("anthropic", "glm-5.3", api_key="test-only").max_tokens == 32768


@pytest.mark.parametrize("limit", [64000, 80000])
def test_small_declared_input_window_keeps_existing_reserve(limit):
    assert _model(profile={"max_input_tokens": limit}).max_tokens == 32768


def test_summary_reserves_enlarged_output_from_actual_model_profile():
    from types import SimpleNamespace

    from deepagents.backends import StateBackend
    from deepagents.middleware.summarization import SummarizationMiddleware

    model = _model(profile={"max_input_tokens": 200000})
    middleware = SummarizationMiddleware(model=model, backend=StateBackend)
    request = SimpleNamespace(model=model, model_settings={})
    assert middleware._input_budget(request) == 124464


async def test_stored_model_and_client_cache_preserve_thinking_specific_defaults():
    from src.kernel.schemas.model import ModelConfig

    config = ModelConfig(value="zai/glm-5.3", label="budget-only", api_key="test-only")
    LLMClient._model_cache.clear()
    try:
        medium = await LLMClient.get_model(
            model_config=config, thinking=build_thinking_config({}, default_level="medium")
        )
        low = await LLMClient.get_model(
            model_config=config, thinking=build_thinking_config({"enable_thinking": "low"})
        )
        explicit = await LLMClient.get_model(
            model_config=config.model_copy(update={"max_tokens": 16384}),
            thinking=build_thinking_config({}, default_level="medium"),
        )
        assert medium.max_tokens == 65536
        assert low.max_tokens == 32768
        assert explicit.max_tokens == 16384
    finally:
        LLMClient._model_cache.clear()

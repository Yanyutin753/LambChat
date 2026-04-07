from src.infra.llm import client as llm_client
from src.infra.llm.client import LLMClient
from src.infra.llm.providers.registry import ProviderRegistry
from src.kernel.config import settings


def test_find_provider_for_prefixed_and_unprefixed_model(monkeypatch):
    monkeypatch.setattr(
        llm_client,
        "_provider_config_cache",
        [
            {
                "provider": "zai",
                "api_key": "zai-key",
                "base_url": "https://open.bigmodel.cn/api/anthropic",
                "temperature": 0.7,
                "max_tokens": 1234,
                "max_retries": 3,
                "models": [{"value": "glm-5.1", "enabled": True}],
            }
        ],
    )

    prefixed = llm_client._find_provider_for_model("zai/glm-5.1")
    unprefixed = llm_client._find_provider_for_model("glm-5.1")

    assert prefixed is not None
    assert unprefixed is not None
    assert prefixed["provider"] == "zai"
    assert unprefixed["provider"] == "zai"


def test_default_model_prefers_enabled_provider_config(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODEL", "anthropic/claude-3-5-sonnet-20241022", raising=False)
    monkeypatch.setattr(
        llm_client,
        "_provider_config_cache",
        [
            {
                "provider": "zai",
                "api_key": "zai-key",
                "base_url": "https://open.bigmodel.cn/api/anthropic",
                "temperature": 0.55,
                "max_tokens": 9000,
                "max_retries": 5,
                "models": [{"value": "glm-5.1", "enabled": True}],
            }
        ],
    )
    monkeypatch.setattr(
        LLMClient,
        "_create_model",
        staticmethod(lambda provider, model_name, **kwargs: (provider, model_name, kwargs)),
    )
    LLMClient._model_cache.clear()

    provider, model_name, kwargs = LLMClient.get_model()

    assert provider == "zai"
    assert model_name == "glm-5.1"
    assert kwargs["api_key"] == "zai-key"
    assert kwargs["api_base"] == "https://open.bigmodel.cn/api/anthropic"
    assert kwargs["max_tokens"] == 9000


def test_registry_recognizes_glm_models():
    registry = ProviderRegistry.get_instance()
    provider = registry.get_provider_for_model("glm-5.1")

    assert provider is not None
    assert provider.config.name == "zai"

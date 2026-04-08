from src.infra.llm import client as llm_client
from src.infra.llm.providers.registry import ProviderRegistry


def test_parse_provider_extracts_prefix_and_model():
    provider, model_name = llm_client._parse_provider("zai/glm-5.1")
    assert provider == "zai"
    assert model_name == "glm-5.1"


def test_parse_provider_defaults_for_unprefixed_model():
    provider, model_name = llm_client._parse_provider("glm-5.1")
    assert provider == "openai"
    assert model_name == "glm-5.1"


def test_parse_provider_recognizes_claude():
    provider, model_name = llm_client._parse_provider("claude-3-5-sonnet-20241022")
    assert provider == "anthropic"
    assert model_name == "claude-3-5-sonnet-20241022"


def test_parse_provider_recognizes_gemini():
    provider, model_name = llm_client._parse_provider("gemini-pro")
    assert provider == "gemini"
    assert model_name == "gemini-pro"


def test_registry_recognizes_glm_models():
    registry = ProviderRegistry.get_instance()
    provider = registry.get_provider_for_model("glm-5.1")

    assert provider is not None
    assert provider.config.name == "zai"

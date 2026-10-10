"""Provider 注册表扩充与官方默认端点。

新增 OpenAI 兼容渠道（聚合器/国际/国产）一律只注册 slug + 默认 api_base，
协议复用 openai；Azure OpenAI 走独立 azure 协议分支（endpoint/deployment/
api-version 语义与 openai base_url 不同）。默认端点仅在用户未填 api_base
时兜底，显式配置优先；自定义中转（未注册 slug）不受影响。
"""

import pytest

from src.infra.llm.client import LLMClient
from src.infra.llm.providers import (
    PROVIDER_DEFAULTS,
    PROVIDER_REGISTRY,
    _parse_provider,
    _resolve_default_api_base,
    _resolve_protocol,
)
from src.kernel.exceptions import AppError

# ── 新增 OpenAI 兼容渠道：slug → 官方默认端点 ──────────────────────────────

NEW_OPENAI_PROVIDERS: dict[str, str] = {
    # 国际聚合 / 推理托管
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "novita": "https://api.novita.ai/v3/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "nebius": "https://api.studio.nebius.ai/v1",
    "hyperbolic": "https://api.hyperbolic.xyz/v1",
    "lambda": "https://api.lambda.ai/v1",
    "github": "https://models.github.ai/inference",
    # 国内
    "siliconflow": "https://api.siliconflow.cn/v1",
    "baidu": "https://qianfan.baidubce.com/v2",
    "modelscope": "https://api-inference.modelscope.cn/v1",
    "gitee": "https://ai.gitee.com/v1",
}

# 存量渠道补默认端点（抽检）
EXISTING_PROVIDER_DEFAULTS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "ollama": "http://127.0.0.1:11434/v1",
    # Anthropic 协议渠道
    "zai": "https://api.z.ai/api/anthropic",
    "kimi": "https://api.moonshot.ai/anthropic",
}


@pytest.fixture(autouse=True)
def _isolate_model_cache():
    LLMClient._model_cache.clear()
    yield
    LLMClient._model_cache.clear()


# ── 注册表结构 ──────────────────────────────────────────────────────────────


def test_new_openai_compatible_providers_registered() -> None:
    for slug in NEW_OPENAI_PROVIDERS:
        assert slug in PROVIDER_REGISTRY, f"provider '{slug}' 未注册"
        assert _resolve_protocol(slug) == "openai"


def test_azure_provider_registered_with_azure_protocol() -> None:
    assert _resolve_protocol("azure") == "azure"


def test_registry_protocols_are_known() -> None:
    for slug, (protocol, _) in PROVIDER_REGISTRY.items():
        assert protocol in {"openai", "anthropic", "google", "azure"}, (
            f"provider '{slug}' 使用未知协议 '{protocol}'"
        )


def test_default_base_table_only_references_registered_providers() -> None:
    for slug in PROVIDER_DEFAULTS:
        assert slug in PROVIDER_REGISTRY, f"PROVIDER_DEFAULTS 中的 '{slug}' 不在 PROVIDER_REGISTRY"


# ── 默认端点解析 ────────────────────────────────────────────────────────────


def test_default_api_base_for_new_providers() -> None:
    for slug, base in NEW_OPENAI_PROVIDERS.items():
        assert _resolve_default_api_base(slug) == base


def test_default_api_base_for_existing_providers() -> None:
    for slug, base in EXISTING_PROVIDER_DEFAULTS.items():
        assert _resolve_default_api_base(slug) == base


def test_unknown_provider_and_google_have_no_default_base() -> None:
    # 自定义中转/未注册 slug 不能臆造端点；Google 协议 base_url 语义特殊，不设默认
    assert _resolve_default_api_base("my-custom-relay") is None
    assert _resolve_default_api_base("google") is None
    assert _resolve_default_api_base("gemini") is None


def test_azure_has_no_universal_default_base() -> None:
    # Azure 端点是每账号资源 URL，无统一默认值
    assert _resolve_default_api_base("azure") is None


# ── provider/model 解析 ─────────────────────────────────────────────────────


def test_parse_provider_splits_multi_segment_values_on_first_slash() -> None:
    provider, model_name = _parse_provider("openrouter/anthropic/claude-sonnet-4-5")
    assert provider == "openrouter"
    assert model_name == "anthropic/claude-sonnet-4-5"


def test_parse_provider_baidu_ernie_prefix() -> None:
    provider, model_name = _parse_provider("ernie-4.5-turbo-128k")
    assert provider == "baidu"
    assert model_name == "ernie-4.5-turbo-128k"


def test_parse_provider_unknown_first_segment_falls_back_openai() -> None:
    provider, _ = _parse_provider("some-vendor/model-x")
    assert provider == "some-vendor"
    assert _resolve_protocol(provider) == "openai"


# ── get_model 默认端点兜底 ──────────────────────────────────────────────────


async def test_get_model_applies_default_base_when_unset() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "deepseek-chat",
            "label": "DeepSeek",
            "provider": "deepseek",
            "api_key": "sk-test",
        },
        use_model_config=False,
    )
    assert str(model.openai_api_base) == "https://api.deepseek.com/v1"


async def test_get_model_explicit_api_base_wins_over_default() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "deepseek-chat",
            "label": "DeepSeek",
            "provider": "deepseek",
            "api_key": "sk-test",
            "api_base": "https://relay.example.com/v1",
        },
        use_model_config=False,
    )
    assert str(model.openai_api_base) == "https://relay.example.com/v1"


async def test_get_model_custom_relay_keeps_empty_base() -> None:
    # 未注册 slug（自定义中转）不填 api_base 时保持 None（SDK 环境变量语义）
    model = await LLMClient.get_model(
        model_config={
            "value": "my-relay/model-x",
            "label": "Relay",
            "provider": "my-relay",
            "api_key": "sk-test",
        },
        use_model_config=False,
    )
    assert model.openai_api_base is None


async def test_get_model_anthropic_protocol_default_base() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "kimi/kimi-k2",
            "label": "Kimi",
            "provider": "kimi",
            "api_key": "sk-test",
        },
        use_model_config=False,
    )
    assert str(model.anthropic_api_url) == "https://api.moonshot.ai/anthropic"


async def test_get_model_new_provider_without_base_uses_default() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "openrouter/anthropic/claude-sonnet-4-5",
            "label": "OR Claude",
            "provider": "openrouter",
            "api_key": "sk-or-test",
        },
        use_model_config=False,
    )
    assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"


# ── Azure 协议分支 ──────────────────────────────────────────────────────────


async def test_get_model_azure_builds_azure_chat_model() -> None:
    from langchain_openai import AzureChatOpenAI

    model = await LLMClient.get_model(
        model_config={
            "value": "azure/gpt-5-deploy",
            "label": "Azure GPT",
            "provider": "azure",
            "api_key": "az-key",
            "api_base": "https://lambchat-res.openai.azure.com",
        },
        use_model_config=False,
    )
    assert isinstance(model, AzureChatOpenAI)
    assert model.deployment_name == "gpt-5-deploy"
    assert str(model.azure_endpoint) == "https://lambchat-res.openai.azure.com"
    assert model.openai_api_version


async def test_azure_api_version_parsed_from_endpoint_query() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "azure/gpt-5-deploy",
            "label": "Azure GPT",
            "provider": "azure",
            "api_key": "az-key",
            "api_base": "https://res.openai.azure.com/?api-version=2025-04-01-preview",
        },
        use_model_config=False,
    )
    assert str(model.azure_endpoint) == "https://res.openai.azure.com"
    assert model.openai_api_version == "2025-04-01-preview"


async def test_azure_missing_endpoint_raises_config_incomplete() -> None:
    with pytest.raises(AppError) as exc_info:
        await LLMClient.get_model(
            model_config={
                "value": "azure/gpt-5-deploy",
                "label": "Azure GPT",
                "provider": "azure",
                "api_key": "az-key",
            },
            use_model_config=False,
        )
    assert exc_info.value.error_code.code == "model_config_incomplete"


async def test_azure_uses_pooled_http_client() -> None:
    model = await LLMClient.get_model(
        model_config={
            "value": "azure/gpt-5-deploy",
            "label": "Azure GPT",
            "provider": "azure",
            "api_key": "az-key",
            "api_base": "https://res.openai.azure.com",
        },
        use_model_config=False,
    )
    assert model.http_async_client is not None


# ── providers/list 路由 ─────────────────────────────────────────────────────


async def test_providers_list_route_exposes_default_base() -> None:
    from src.api.routes.agent.model import list_providers

    providers = await list_providers()
    by_slug = {p["value"]: p for p in providers}
    assert by_slug["openrouter"]["defaultBaseUrl"] == "https://openrouter.ai/api/v1"
    assert by_slug["deepseek"]["defaultBaseUrl"] == "https://api.deepseek.com/v1"
    # 未注册默认端点的渠道（如 google）显式返回 None，前端可区分
    assert by_slug["google"]["defaultBaseUrl"] is None


# ── Provider slug 大小写归一 ────────────────────────────────────────────────
# 生产 2026-10-10：GLM 模型配置的 provider 存成大写 "ZAI"，注册表按小写键
# 查不到，_resolve_protocol 兜底成 openai 线格式，思考模式历史回传缺
# reasoning 直接 400。slug 归一后大小写/空白变体必须解析到同一协议。


@pytest.mark.parametrize(
    "raw",
    ["zai", "ZAI", "Zai", " zai ", "anthropic", "Anthropic", "DeepSeek"],
)
def test_resolve_protocol_normalizes_provider_case(raw: str) -> None:
    expected = {"zai": "anthropic", "anthropic": "anthropic", "deepseek": "openai"}[
        raw.strip().lower()
    ]
    assert _resolve_protocol(raw) == expected


def test_model_config_normalizes_provider_slug() -> None:
    from src.kernel.schemas.model import ModelConfig

    cfg = ModelConfig(value="glm-5.3-flash", provider="ZAI", label="GLM 5.3 Flash")
    assert cfg.provider == "zai"


def test_model_supports_thinking_normalized_provider() -> None:
    from src.infra.llm.client import model_supports_thinking

    assert model_supports_thinking("ZAI", "glm-5.3-flash") is True

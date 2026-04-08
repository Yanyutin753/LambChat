"""
Azure OpenAI provider.
"""

from typing import Any, Optional

from src.infra.llm.providers.registry import (
    PROVIDER_BRAND_COLORS,
    BaseLLMProvider,
    ProviderConfig,
    ProviderModelInfo,
    ProviderUIMeta,
)
from src.kernel.config import settings


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI - GPT models via Azure OpenAI Service."""

    name = "azure"
    display_name = "Azure OpenAI"
    category = "azure_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    ui_meta = ProviderUIMeta(
        icon="azure",
        color=PROVIDER_BRAND_COLORS["azure"],
        website="https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        description="Microsoft Azure-hosted OpenAI models - enterprise ready",
    )

    default_models = [
        ProviderModelInfo(
            model_id="gpt-4o",
            aliases=["gpt-4o-20241120"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-4o-mini",
            aliases=["gpt-4o-mini"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-4-turbo",
            aliases=["gpt-4-turbo", "gpt-4-turbo-20240409"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-35-turbo",
            aliases=["gpt-3.5-turbo", "gpt-3.5-turbo-16k"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # Azure-specific: extract deployment name from extra config
        self._deployment_name = config.extra.get("deployment_name", "")

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        # Models can be prefixed with "azure/" or contain azure indicators
        return model_id.startswith("azure/")

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "azure" in base_url.lower() or "cognitive" in base_url.lower()

    def _build_langchain_kwargs(
        self,
        model_name: str,
        *,
        temperature: float,
        max_tokens: Optional[int],
        thinking: Optional[dict],
        profile: Optional[dict],
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Azure uses deployment_name in extra config or model_name maps to deployment
        deployment_name = self._deployment_name or model_name

        # Azure-specific kwargs
        azure_kwargs = {
            "model_name": deployment_name,  # Azure uses deployment name
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "streaming": True,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "api_version": self._extra.get("api_version", "2024-02-01"),
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

        # Remove azure-specific from kwargs before passing
        kwargs.pop("api_version", None)

        return azure_kwargs

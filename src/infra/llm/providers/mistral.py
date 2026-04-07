"""
Mistral AI provider.
"""

from typing import Any, Optional

from src.infra.llm.providers.registry import (
    BaseLLMProvider,
    ProviderConfig,
    ProviderModelInfo,
    PROVIDER_BRAND_COLORS,
    ProviderUIMeta,
)
from src.kernel.config import settings


class MistralProvider(BaseLLMProvider):
    """Mistral AI - Mistral, Mixtral, Codestral via Mistral API."""

    name = "mistral"
    display_name = "Mistral AI"
    category = "openai_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    DEFAULT_BASE_URL = "https://api.mistral.ai/v1"
    ui_meta = ProviderUIMeta(
        icon="mistral",
        color=PROVIDER_BRAND_COLORS["mistral"],
        website="https://mistral.ai",
        description="Mistral and Mixtral - efficient open models",
    )

    default_models = [
        ProviderModelInfo(
            model_id="mistral-large-2411",
            aliases=["mistral-large", "mistral-large-latest"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="mistral-small-2409",
            aliases=["mistral-small", "mistral-small-latest"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="mistral-medium-2312",
            aliases=["mistral-medium"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="open-mixtral-8x22b",
            aliases=["mixtral-8x22b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="open-mixtral-8x7b",
            aliases=["mixtral-8x7b", "mixtral"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="open-codestral-2405",
            aliases=["codestral", "codestral-2405"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return (
            model_id.startswith("mistral")
            or model_id.startswith("open-mixtral")
            or model_id.startswith("open-codestral")
        )

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "mistral" in base_url.lower()

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
        return {
            "model_name": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "streaming": True,
            "api_key": self.api_key or "INVALID_API_KEY",
            "base_url": self.base_url or self.DEFAULT_BASE_URL,
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

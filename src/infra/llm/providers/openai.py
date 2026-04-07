"""
OpenAI provider (GPT models via OpenAI API).
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


class ChatOpenAIProvider(BaseLLMProvider):
    """OpenAI - GPT models via OpenAI API (or compatible endpoints)."""

    name = "openai"
    display_name = "OpenAI"
    category = "openai_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    ui_meta = ProviderUIMeta(
        icon="openai",
        color=PROVIDER_BRAND_COLORS["openai"],
        website="https://openai.com",
        description="GPT models - industry standard for general purpose",
    )

    default_models = [
        ProviderModelInfo(
            model_id="gpt-4o",
            aliases=["gpt-4o-20241120", "gpt-4o-20250513"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-4o-mini",
            aliases=["gpt-4o-mini-20250718"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-4-turbo",
            aliases=["gpt-4-turbo-20240409", "gpt-4-turbo"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-4",
            aliases=["gpt-4-0613"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gpt-3.5-turbo",
            aliases=["gpt-3.5-turbo-16k", "gpt-3.5-turbo-0613"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="o1-preview",
            aliases=["o1-preview-20240917"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="o1-mini",
            aliases=["o1-mini-20240917"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="o3",
            aliases=["o3-20250619"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="o3-mini",
            aliases=["o3-mini-20250131"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return (
            model_id.startswith("gpt-")
            or model_id.startswith("o1-")
            or model_id.startswith("o3-")
            or model_id == "o1"
            or model_id == "o1-mini"
        )

    def matches_url(self, base_url: str) -> bool:
        """Check if URL matches openai.com or known openai-compatible endpoints."""
        if not base_url:
            return False
        parsed = base_url.lower()
        return (
            "openai.com" in parsed
            or "api.openai.com" in parsed
            or parsed.startswith("https://api.openai.com")
            or
            # Azure has different URL pattern - handled in Azure provider
            "azure" in parsed
        )

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
            "api_key": self.api_key or "sk-placeholder",
            "base_url": self.base_url,
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

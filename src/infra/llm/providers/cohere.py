"""
Cohere provider.
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


class CohereProvider(BaseLLMProvider):
    """Cohere - Command R, Command R+ via Cohere API."""

    name = "cohere"
    display_name = "Cohere"
    category = "cohere_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    DEFAULT_BASE_URL = "https://api.cohere.ai/v2"
    ui_meta = ProviderUIMeta(
        icon="cohere",
        color=PROVIDER_BRAND_COLORS["cohere"],
        website="https://cohere.com",
        description="Command R series - optimized for RAG and tool use",
    )

    default_models = [
        ProviderModelInfo(
            model_id="command-r-plus-08-2024",
            aliases=["command-r-plus", "c47d9780-9297-41c5-8b4d-8e20扣2192"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="command-r-08-2024",
            aliases=["command-r", "command"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="command-r-plus-4-2025-04",
            aliases=["c99p"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="command-r-4-2025-04",
            aliases=["c44"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return model_id.startswith("command-r") or model_id.startswith("command")

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "cohere" in base_url.lower()

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

"""
DeepSeek provider.
"""

from typing import Any, Optional

from src.infra.llm.providers.registry import (
    BaseLLMProvider,
    ProviderConfig,
    ProviderModelInfo,
    ProviderUIMeta,
)
from src.kernel.config import settings


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek - DeepSeek V3, Coder models via DeepSeek API."""

    name = "deepseek"
    display_name = "DeepSeek"
    category = "openai_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    ui_meta = ProviderUIMeta(
        icon="deepseek",
        color="#0055FF",
        website="https://deepseek.com",
        description="DeepSeek V3 & Coder - powerful and cost-effective",
    )

    default_models = [
        ProviderModelInfo(
            model_id="deepseek-chat",
            aliases=["deepseek-v3", "deepseek-v3-chat"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="deepseek-coder",
            aliases=["deepseek-coder-33b", "deepseek-coder-33b-instruct"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return model_id.startswith("deepseek")

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "deepseek" in base_url.lower()

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
            "max_retries": getattr(settings, "LLM_MAX_RETRIES", 3),
        }

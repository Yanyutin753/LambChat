"""
Groq provider (fast inference for Llama, Mixtral, etc.).
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


class GroqProvider(BaseLLMProvider):
    """Groq - Fast inference for open models (Llama, Mixtral, Gemma)."""

    name = "groq"
    display_name = "Groq"
    category = "openai_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    ui_meta = ProviderUIMeta(
        icon="groq",
        color=PROVIDER_BRAND_COLORS["groq"],
        website="https://console.groq.com",
        description="Fast inference - Llama, Mixtral, Gemma at lightning speed",
    )

    default_models = [
        ProviderModelInfo(
            model_id="llama-3.3-70b-versatile",
            aliases=["llama-3.3-70b", "llama-3-3-70b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="llama-3.1-8b-instant",
            aliases=["llama-3.1-8b", "llama-3-1-8b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="mixtral-8x7b-32768",
            aliases=["mixtral-8x7b"],
            supports_thinking=False,
            max_tokens=32768,
        ),
        ProviderModelInfo(
            model_id="gemma2-9b-it",
            aliases=["gemma2-9b", "gemma-2-9b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="gemma-7b-it",
            aliases=["gemma-7b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        models = cls.get_all_model_ids()
        return model_id in models

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "groq.com" in base_url.lower()

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

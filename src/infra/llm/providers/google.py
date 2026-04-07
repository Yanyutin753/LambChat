"""
Google Generative AI provider (Gemini models).
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


class GoogleGenerativeProvider(BaseLLMProvider):
    """Google - Gemini models via Google AI API."""

    name = "google"
    display_name = "Google AI"
    category = "google_compatible"
    langchain_class_path = "langchain_google_genai.ChatGoogleGenerativeAI"
    ui_meta = ProviderUIMeta(
        icon="google",
        color=PROVIDER_BRAND_COLORS["google"],
        website="https://ai.google.dev",
        description="Gemini models - Google's most capable AI model",
    )

    default_models = [
        ProviderModelInfo(
            model_id="gemini-2.5-pro-preview-06-05",
            aliases=["gemini-2.5-pro"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="gemini-2.0-flash",
            aliases=["gemini-2.0-flash", "gemini-2-flash"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="gemini-1.5-pro",
            aliases=["gemini-1.5-pro", "gemini-pro"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="gemini-1.5-flash",
            aliases=["gemini-1.5-flash", "gemini-flash"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="gemini-1.5-flash-8b",
            aliases=["gemini-flash-8b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return model_id.startswith("gemini")

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
        from pydantic import SecretStr

        # Google uses "thinking_level" instead of "thinking" dict
        thinking_level = None
        if thinking and thinking.get("type") == "enabled":
            thinking_level = thinking.get("level", "medium")

        return {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "google_api_key": SecretStr(self.api_key) if self.api_key else None,
            "base_url": self.base_url,
            "thinking_level": thinking_level,
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

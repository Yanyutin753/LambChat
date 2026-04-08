"""
Anthropic provider (Claude models).
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


class AnthropicProvider(BaseLLMProvider):
    """Anthropic - Claude models via Anthropic API."""

    name = "anthropic"
    display_name = "Anthropic"
    category = "anthropic_compatible"
    langchain_class_path = "langchain_anthropic.ChatAnthropic"
    ui_meta = ProviderUIMeta(
        icon="anthropic",
        color=PROVIDER_BRAND_COLORS["anthropic"],
        website="https://anthropic.com",
        description="Claude models - best for reasoning, analysis, and creative tasks",
    )

    default_models = [
        ProviderModelInfo(
            model_id="claude-3-5-sonnet-20241022",
            aliases=["claude-3-5-sonnet", "claude-sonnet-4-20250514"],
            supports_thinking=True,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="claude-3-5-haiku-20241022",
            aliases=["claude-3-5-haiku", "claude-haiku-4-20250514"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="claude-3-opus-20240229",
            aliases=["claude-3-opus"],
            supports_thinking=True,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="claude-3-sonnet-20240229",
            aliases=["claude-3-sonnet"],
            supports_thinking=True,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="claude-3-haiku-20240307",
            aliases=["claude-3-haiku"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @staticmethod
    def _resolve_base_url(base_url: Optional[str]) -> Optional[str]:
        """Ignore incompatible global fallbacks such as OpenAI's base URL."""
        normalized = (base_url or "").strip()
        if not normalized:
            return None

        lowered = normalized.lower()
        if "api.openai.com" in lowered:
            return None

        return normalized

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        return model_id.startswith("claude")

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

        thinking_param = None
        if thinking and thinking.get("type") == "enabled":
            thinking_param = thinking

        init_kwargs = {
            "model_name": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "base_url": self._resolve_base_url(self.base_url),
            "thinking": thinking_param,
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

        if self.api_key:
            init_kwargs["api_key"] = SecretStr(self.api_key)

        return init_kwargs

"""
ZAI provider (ChatGLM models via Zhipu / BigModel).
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


class ZAIProvider(BaseLLMProvider):
    """ChatGLM models via Zhipu's Anthropic-compatible endpoint."""

    name = "zai"
    display_name = "ChatGLM"
    category = "anthropic_compatible"
    langchain_class_path = "langchain_anthropic.ChatAnthropic"
    ui_meta = ProviderUIMeta(
        icon="zhipu",
        color=PROVIDER_BRAND_COLORS["zai"],
        website="https://open.bigmodel.cn",
        description="ChatGLM models - GLM family models from Zhipu AI",
    )

    default_models = [
        ProviderModelInfo(
            model_id="glm-5.1",
            aliases=["glm-5", "glm-4.5", "glm-4.5-air", "glm-4-flash"],
            supports_thinking=True,
            max_tokens=8192,
        )
    ]

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"

    @classmethod
    def _resolve_base_url(cls, base_url: Optional[str]) -> str:
        """Ignore incompatible global fallbacks such as OpenAI's base URL."""
        normalized = (base_url or "").strip()
        if not normalized:
            return cls.DEFAULT_BASE_URL

        lowered = normalized.lower()
        if "api.openai.com" in lowered:
            return cls.DEFAULT_BASE_URL

        return normalized

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        normalized = model_id.split("/", 1)[-1].lower()
        return normalized.startswith("glm-") or normalized.startswith("chatglm")

    def matches_url(self, base_url: str) -> bool:
        parsed = (base_url or "").lower()
        return "bigmodel.cn" in parsed or "open.bigmodel.cn" in parsed

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

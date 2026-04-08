"""
Ollama provider (local LLM inference).
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


class OllamaProvider(BaseLLMProvider):
    """Ollama - Local LLM inference with Ollama."""

    name = "ollama"
    display_name = "Ollama (Local)"
    category = "openai_compatible"
    langchain_class_path = "langchain_openai.ChatOpenAI"
    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    ui_meta = ProviderUIMeta(
        icon="ollama",
        color=PROVIDER_BRAND_COLORS["ollama"],
        website="https://ollama.com",
        description="Local LLM inference - run models on your own hardware",
    )

    # Common Ollama models (user can run any model they have pulled)
    default_models = [
        ProviderModelInfo(
            model_id="llama3.3",
            aliases=["llama-3.3", "llama3"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="llama3.2",
            aliases=["llama-3.2", "llama3.1"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="codellama",
            aliases=["codellama-34b", "codellama-13b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="mistral",
            aliases=["mistral-7b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="mixtral",
            aliases=["mixtral-8x7b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="phi3",
            aliases=["phi3-medium", "phi3-mini"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="qwen2.5",
            aliases=["qwen2", "qwen"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="deepseek-v2",
            aliases=["deepseek-v2-chat"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="gemma2",
            aliases=["gemma2-27b", "gemma2-9b"],
            supports_thinking=False,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="nomic-embed-text",
            aliases=["nomic-embed"],
            supports_thinking=False,
            max_tokens=8192,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        # Ollama can run any model name, but we check for common prefixes
        # Since Ollama models are user-defined, this is a best-effort match
        common_prefixes = [
            "llama",
            "mistral",
            "mixtral",
            "codellama",
            "phi",
            "qwen",
            "gemma",
            "deepseek",
            "nomic",
        ]
        return any(model_id.startswith(p) for p in common_prefixes)

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "ollama" in base_url.lower() or "11434" in base_url

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
        # Ollama is OpenAI-compatible, uses /v1/chat/completions
        return {
            "model_name": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "streaming": True,
            # Ollama typically doesn't need API key for local, but can be set
            "api_key": self.api_key or "ollama",
            "base_url": self.base_url or self.DEFAULT_BASE_URL,
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

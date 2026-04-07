"""
Provider Registry - Central registry for LLM providers.

Architecture:
- Each provider implements the Provider interface
- Providers auto-register via decorator or config
- Provider config can come from env vars or database (MongoDB)
- LLMClient uses registry to resolve provider for any model
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from src.infra.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProviderModelInfo:
    """Information about a model supported by a provider."""

    model_id: str  # e.g., "gpt-4o", "claude-3-5-sonnet-20241022"
    # Optional known alias (some providers use different IDs internally)
    aliases: list[str] = field(default_factory=list)
    # Supports thinking/reasoning (Anthropic extended thinking, etc.)
    supports_thinking: bool = False
    # Supports streaming
    supports_streaming: bool = True
    # Max context tokens (if known)
    max_tokens: Optional[int] = None


@dataclass
class ProviderUIMeta:
    """UI metadata for a provider (icon, color, website, description)."""

    icon: str = ""
    color: str = "#888888"
    website: str = ""
    description: str = ""


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""

    name: str  # "openai", "anthropic", "azure", etc.
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    # Provider-specific settings (e.g., Azure has api_version, deployment_name)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Base class for all LLM providers."""

    # Class-level provider identity
    name: str = ""  # Override in subclass
    display_name: str = ""  # Human-readable name
    category: str = "generic"  # "openai_compatible", "anthropic_compatible", etc.

    # UI metadata (icon, color, website, description)
    ui_meta: ProviderUIMeta = ProviderUIMeta()

    # Default models this provider supports
    default_models: list[ProviderModelInfo] = []

    # Which LangChain chat model class to use
    # Override in subclass to point to correct LangChain class
    langchain_class_path: str = ""  # e.g., "langchain_openai.ChatOpenAI"

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._api_key = config.api_key
        self._base_url = config.base_url
        self._extra = config.extra

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @property
    def base_url(self) -> Optional[str]:
        return self._base_url

    def get_env_prefix(self) -> str:
        """Get the environment variable prefix for this provider."""
        return f"LLM_PROVIDER_{self.name.upper()}"

    def get_langchain_model(
        self,
        model_name: str,
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """Create and return a LangChain model instance."""

        cls_path = self.langchain_class_path
        if not cls_path:
            raise ValueError(f"Provider {self.name} has no langchain_class_path")

        # Dynamically import the class
        module_path, class_name = cls_path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)

        # Build kwargs for this provider type
        init_kwargs = self._build_langchain_kwargs(
            model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking,
            profile=profile,
            **kwargs,
        )

        return cls(**init_kwargs)

    @abstractmethod
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
        """Build kwargs for LangChain model constructor. Must be implemented by subclass."""
        pass

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        """Check if this provider handles the given model ID.

        Override in subclass for custom matching logic.
        Default: check if model_id starts with provider name or known aliases.
        """
        return False

    def matches_url(self, base_url: str) -> bool:
        """Check if this provider matches the given base URL.

        Override in subclass if URL-based matching is needed.
        """
        return False

    @classmethod
    def get_all_model_ids(cls) -> list[str]:
        """Get all model IDs supported by this provider."""
        ids = []
        for m in cls.default_models:
            ids.append(m.model_id)
            ids.extend(m.aliases)
        return ids

    def get_model_info(self, model_id: str) -> Optional[ProviderModelInfo]:
        """Get info about a specific model."""
        for m in self.default_models:
            if model_id == m.model_id or model_id in m.aliases:
                return m
        return None

    def get_ui_meta(self) -> ProviderUIMeta:
        """Get UI metadata for this provider."""
        return self.ui_meta


# ============================================
# Provider Registry
# ============================================


class ProviderRegistry:
    """
    Central registry for all LLM providers.

    Usage:
        registry = ProviderRegistry()
        registry.register_provider(AzureOpenAIProvider)
        registry.register_provider(AnthropicProvider)

        provider = registry.get_provider_for_model("gpt-4o")
        provider = registry.get_provider_for_model("anthropic/claude-3-5-sonnet")
    """

    _instance: Optional["ProviderRegistry"] = None

    def __init__(self):
        self._providers: dict[str, Type[BaseLLMProvider]] = {}
        self._provider_instances: dict[str, BaseLLMProvider] = {}
        # URL pattern -> provider name mapping (for URL-based detection)
        self._url_patterns: list[tuple[re.Pattern, str]] = []

    @classmethod
    def get_instance(cls) -> "ProviderRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._auto_register_builtin_providers()
        return cls._instance

    def _auto_register_builtin_providers(self):
        """Register all built-in providers."""
        from src.infra.llm.providers import (
            AnthropicProvider,
            AWSBedrockProvider,
            AzureOpenAIProvider,
            ChatOpenAIProvider,
            CohereProvider,
            DeepSeekProvider,
            GoogleGenerativeProvider,
            GroqProvider,
            MistralProvider,
            OllamaProvider,
        )

        self.register_provider(AnthropicProvider)
        self.register_provider(GoogleGenerativeProvider)
        self.register_provider(ChatOpenAIProvider)
        self.register_provider(AzureOpenAIProvider)
        self.register_provider(AWSBedrockProvider)
        self.register_provider(GroqProvider)
        self.register_provider(DeepSeekProvider)
        self.register_provider(MistralProvider)
        self.register_provider(CohereProvider)
        self.register_provider(OllamaProvider)

    def register_provider(self, provider_class: Type[BaseLLMProvider]) -> None:
        """Register a provider class."""
        if not issubclass(provider_class, BaseLLMProvider):
            raise TypeError(f"{provider_class} must inherit from BaseLLMProvider")
        if not provider_class.name:
            raise ValueError(f"Provider class {provider_class.__name__} must define 'name'")
        self._providers[provider_class.name] = provider_class
        logger.debug(f"Registered provider: {provider_class.name}")

    def get_provider(
        self, name: str, config: Optional[ProviderConfig] = None
    ) -> Optional[BaseLLMProvider]:
        """Get a provider instance by name."""
        provider_class = self._providers.get(name)
        if not provider_class:
            return None

        # Return cached instance if exists and no custom config
        if name in self._provider_instances and config is None:
            return self._provider_instances[name]

        instance = provider_class(config or ProviderConfig(name=name))
        if config is None:
            self._provider_instances[name] = instance
        return instance

    def get_provider_for_model(self, model_value: str) -> Optional[BaseLLMProvider]:
        """
        Find the provider that should handle a given model.

        Resolution order:
        1. If model contains "/", prefix is provider name
        2. Match against registered providers' matches_model()
        3. URL-based matching via matches_url()
        """
        # Case 1: explicit provider prefix (e.g., "anthropic/claude-3-5-sonnet")
        if "/" in model_value:
            provider_name, _ = model_value.split("/", 1)
            if provider_name in self._providers:
                return self.get_provider(provider_name)

        # Case 2: check each provider's matches_model
        for name, provider_class in self._providers.items():
            if provider_class.matches_model(model_value):
                return self.get_provider(name)

        # Case 3: URL pattern matching
        # (URL patterns are registered by individual providers)

        # Default fallback
        return self.get_provider("openai")

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def get_all_provider_ui_metas(self) -> list[ProviderUIMeta]:
        """Get UI metadata for all registered providers."""
        metas = []
        for name in self._providers:
            instance = self.get_provider(name)
            if instance:
                meta = instance.get_ui_meta()
                metas.append(
                    ProviderUIMeta(
                        icon=meta.icon or name,
                        color=meta.color or "#888888",
                        website=meta.website,
                        description=meta.description or f"{instance.display_name} provider",
                    )
                )
        return metas

    def get_all_provider_names_with_config(self) -> list[tuple[str, str]]:
        """List all providers that have configuration set via environment variables.

        Returns list of (provider_name, display_name) tuples.
        """
        result = []
        for name, provider_class in self._providers.items():
            config = self._load_config_from_env(provider_class)
            if config and config.api_key:
                result.append((name, provider_class.display_name or name))
        return result


# ============================================
# Environment Variable Helpers
# ============================================


def get_provider_config_from_env(provider_name: str) -> Optional[ProviderConfig]:
    """
    Load provider configuration from environment variables.

    Expected env vars for provider "xyz":
    - LLM_PROVIDER_XYZ_ENABLED: bool (optional, default true if api_key present)
    - LLM_PROVIDER_XYZ_API_KEY: str
    - LLM_PROVIDER_XYZ_BASE_URL: str (optional)
    - LLM_PROVIDER_XYZ_EXTRA_* : Additional provider-specific settings
    """
    prefix = f"LLM_PROVIDER_{provider_name.upper()}"

    enabled = os.environ.get(f"{prefix}_ENABLED", "").lower()
    api_key = os.environ.get(f"{prefix}_API_KEY", "")
    base_url = os.environ.get(f"{prefix}_BASE_URL", "")

    # If not explicitly enabled and no api_key, skip
    if enabled in ("false", "0", "no"):
        return None
    if not api_key and enabled not in ("true", "1", "yes"):
        return None

    # Collect extra settings
    extra = {}
    for key, value in os.environ.items():
        if key.startswith(f"{prefix}_EXTRA_"):
            extra_key = key[len(f"{prefix}_EXTRA_") :].lower()
            extra[extra_key] = value

    return ProviderConfig(
        name=provider_name,
        api_key=api_key or None,
        base_url=base_url or None,
        extra=extra,
    )


def load_all_provider_configs_from_env() -> dict[str, ProviderConfig]:
    """Load configs for all providers that have env var configuration."""
    registry = ProviderRegistry.get_instance()
    configs = {}
    for name in registry.list_providers():
        config = get_provider_config_from_env(name)
        if config and config.api_key:
            configs[name] = config
    return configs


# Factory function for backward compatibility
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry.get_instance()

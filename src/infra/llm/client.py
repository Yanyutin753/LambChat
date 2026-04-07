"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
支持通过 Provider Registry 动态发现和使用多种 LLM provider。
"""

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

_INVALID_API_KEY_PLACEHOLDERS = {
    "your_openai_api_key_here",
}

# Cache for raw settings from database (loaded once)
_setting_cache: dict[str, Any] = {}
_setting_cache_lock = threading.Lock()

# Cache for provider config from MongoDB
_provider_config_cache: Optional[list[dict]] = None
_provider_cache_lock = threading.Lock()

# Thread pool for async-to-sync bridge
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm_loader")

# Lazy import for provider registry (avoids circular imports)
_registry = None


def _get_registry():
    """Get or initialize the provider registry."""
    global _registry
    if _registry is None:
        from src.infra.llm.providers.registry import ProviderRegistry

        _registry = ProviderRegistry.get_instance()
    return _registry


def _load_raw_settings():
    """Load raw sensitive settings from database (sync, for startup use only)"""
    global _setting_cache
    if _setting_cache:
        return _setting_cache

    with _setting_cache_lock:
        if _setting_cache:
            return _setting_cache

        try:
            from src.infra.settings.service import get_settings_service
            from src.kernel.config import SENSITIVE_SETTINGS

            service = get_settings_service()
            if service:
                for key in SENSITIVE_SETTINGS:
                    try:
                        try:
                            asyncio.get_running_loop()
                            continue
                        except RuntimeError:
                            pass

                        value = asyncio.run(service.get_raw(key))
                        if value:
                            _setting_cache[key] = value
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Could not load raw settings from database: {e}")

    return _setting_cache


def get_api_key(key: str) -> Optional[str]:
    """Get API key with priority: database > env > settings"""
    def _normalize(candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        normalized = candidate.strip()
        if not normalized or normalized in _INVALID_API_KEY_PLACEHOLDERS:
            return None
        return normalized

    _load_raw_settings()
    if key in _setting_cache:
        cached = _normalize(_setting_cache[key])
        if cached:
            return cached

    env_value = _normalize(os.environ.get(key))
    if env_value:
        return env_value

    if hasattr(settings, key):
        return _normalize(getattr(settings, key))

    return None


def _load_provider_config_sync() -> list[dict]:
    """Load provider config from MongoDB synchronously (blocking, for thread pool use)."""
    try:
        from src.infra.model.config_storage import get_model_config_storage

        storage = get_model_config_storage()
        # Use asyncio.run - this is fine because it's called in a thread
        return asyncio.run(storage.get_provider_config_raw())
    except Exception as e:
        logger.debug(f"Could not load provider config from MongoDB: {e}")
        return []


def _load_provider_config() -> list[dict]:
    """Load provider config, trying async bridge first, then thread pool."""
    global _provider_config_cache

    # Fast path: already loaded
    if _provider_config_cache is not None:
        return _provider_config_cache

    with _provider_cache_lock:
        if _provider_config_cache is not None:
            return _provider_config_cache

        try:
            asyncio.get_running_loop()
            # In async context - use thread pool
            future = _executor.submit(_load_provider_config_sync)
            _provider_config_cache = future.result(timeout=5.0)
        except RuntimeError:
            # No running loop - use asyncio.run directly
            _provider_config_cache = asyncio.run(_get_provider_config_async_cached())
        except Exception as e:
            logger.debug(f"Could not load provider config: {e}")
            _provider_config_cache = []

    return _provider_config_cache or []


async def _get_provider_config_async_cached() -> list[dict]:
    """Async version that properly loads and caches provider config."""
    global _provider_config_cache
    if _provider_config_cache is not None:
        return _provider_config_cache

    from src.infra.model.config_storage import get_model_config_storage

    storage = get_model_config_storage()
    _provider_config_cache = await storage.get_provider_config_raw()
    return _provider_config_cache or []


def refresh_provider_config_cache() -> list[dict]:
    """Force refresh the provider config cache. Called after PUT /providers."""
    global _provider_config_cache

    with _provider_cache_lock:
        _provider_config_cache = None

    try:
        asyncio.get_running_loop()
        # In async context - schedule refresh in thread pool
        future = _executor.submit(_load_provider_config_sync)
        _provider_config_cache = future.result(timeout=5.0)
    except RuntimeError:
        _provider_config_cache = asyncio.run(_get_provider_config_async_cached())
    except Exception as e:
        logger.debug(f"Could not refresh provider config: {e}")
        _provider_config_cache = []

    return _provider_config_cache or []


def _models_compatible(model_a: str, model_b: str) -> bool:
    """Compatibility match between provider-prefixed and legacy model IDs."""
    if not model_a or not model_b:
        return False
    if model_a == model_b:
        return True
    if "/" in model_a and "/" not in model_b:
        return model_a.endswith(f"/{model_b}")
    if "/" in model_b and "/" not in model_a:
        return model_b.endswith(f"/{model_a}")
    return False


def _find_provider_for_model(model_value: str) -> Optional[dict]:
    """Find the provider config for a given model value."""
    providers = _load_provider_config()
    for p in providers:
        for m in p.get("models", []):
            if _models_compatible(m.get("value", ""), model_value):
                return p
    return None


def _find_configured_model_value(model_value: str) -> Optional[str]:
    """Find the stored configured model value compatible with the requested one."""
    providers = _load_provider_config()
    for provider in providers:
        for model in provider.get("models", []):
            candidate = model.get("value", "")
            if _models_compatible(candidate, model_value):
                return candidate
    return None


def _get_first_configured_model_value(enabled_only: bool = True) -> Optional[str]:
    """Return the first configured model value, preferring enabled entries."""
    providers = _load_provider_config()
    fallback = None
    for provider in providers:
        for model in provider.get("models", []):
            value = model.get("value")
            if not value:
                continue
            if fallback is None:
                fallback = value
            if not enabled_only or model.get("enabled", True):
                return value
    return fallback


def _resolve_default_model_value() -> str:
    """Resolve the runtime default model, preferring configured provider models."""
    configured_default = getattr(settings, "LLM_MODEL", None) or ""
    configured_match = (
        _find_configured_model_value(configured_default) if configured_default else None
    )
    if configured_match:
        return configured_match

    first_enabled = _get_first_configured_model_value(enabled_only=True)
    if first_enabled:
        return first_enabled

    first_configured = _get_first_configured_model_value(enabled_only=False)
    if first_configured:
        return first_configured

    if configured_default:
        return configured_default

    return "anthropic/claude-3-5-sonnet-20241022"


def _parse_provider(model: str) -> tuple[str, str]:
    """从模型标识解析 provider 和 model_name。

    Returns:
        (provider, model_name)，如 ("anthropic", "claude-3-5-sonnet-20241022")
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        model_name = model
        # Use provider registry to determine provider
        registry = _get_registry()
        provider_instance = registry.get_provider_for_model(model_name)
        if provider_instance:
            provider = provider_instance.config.name
        else:
            provider = "openai"  # fallback
    return provider, model_name


def _get_provider_config_env(provider_name: str) -> dict[str, Any]:
    """Get provider config from environment variables.

    Returns dict with api_key, base_url, extra settings from LLM_PROVIDER_{NAME}_* env vars.
    """
    prefix = f"LLM_PROVIDER_{provider_name.upper()}"
    config = {}

    api_key = os.environ.get(f"{prefix}_API_KEY", "")
    base_url = os.environ.get(f"{prefix}_BASE_URL", "")
    enabled = os.environ.get(f"{prefix}_ENABLED", "")

    # Only include if enabled or has api_key
    if enabled.lower() in ("true", "1", "yes") or api_key:
        config["api_key"] = api_key or None
        config["base_url"] = base_url or None

        # Collect extra settings
        extra = {}
        for key, value in os.environ.items():
            if key.startswith(f"{prefix}_EXTRA_"):
                extra_key = key[len(f"{prefix}_EXTRA_") :].lower()
                extra[extra_key] = value
        if extra:
            config["extra"] = extra

    return config


def _make_cache_key(
    provider: str,
    model_name: str,
    temperature: float,
    max_tokens: Optional[int],
    api_key: Optional[str],
    api_base: Optional[str],
    thinking: Optional[dict],
    profile: Optional[dict],
    max_retries: int,
) -> tuple:
    thinking_key = tuple(sorted(thinking.items())) if thinking else None
    profile_key = tuple(sorted(profile.items())) if profile else None
    return (
        provider,
        model_name,
        temperature,
        max_tokens,
        api_key,
        api_base,
        thinking_key,
        profile_key,
        max_retries,
    )


class LLMClient:
    """LLM 客户端工厂，支持实例缓存和 fallback。"""

    _model_cache: dict[tuple, Any] = {}

    @staticmethod
    def _get_max_cache_size() -> int:
        """获取最大缓存大小（可配置）"""
        return getattr(settings, "LLM_MODEL_CACHE_SIZE", 50)

    @staticmethod
    def _create_model(
        provider: str,
        model_name: str,
        *,
        temperature: float,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        extra: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """根据 provider 创建对应的 LangChain 模型。

        使用 Provider Registry 动态发现 provider 并创建 LangChain 模型实例。
        """
        registry = _get_registry()

        # Get provider config from env (provider-specific LLM_PROVIDER_* vars)
        env_config = _get_provider_config_env(provider)

        # Merge: env config takes precedence over passed-in config
        effective_api_key = get_api_key("LLM_API_KEY")
        if api_key:
            effective_api_key = api_key
        if env_config.get("api_key"):
            effective_api_key = env_config.get("api_key")
        effective_base_url = (
            env_config.get("base_url")
            or api_base
            or os.environ.get("LLM_API_BASE")
            or getattr(settings, "LLM_API_BASE", None)
        )
        effective_extra = {**(extra or {}), **(env_config.get("extra", {}))}

        # Get provider instance from registry
        from src.infra.llm.providers.registry import ProviderConfig

        provider_config = ProviderConfig(
            name=provider,
            api_key=effective_api_key,
            base_url=effective_base_url,
            extra=effective_extra,
        )

        provider_instance = registry.get_provider(provider, provider_config)
        if not provider_instance:
            # Fallback to direct LangChain creation
            logger.warning(f"Provider {provider} not found in registry, using ChatOpenAI fallback")
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=effective_api_key or "sk-placeholder",
                base_url=effective_base_url or None,
                max_retries=max_retries,
            )

        try:
            return provider_instance.get_langchain_model(
                model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking=thinking,
                profile=profile,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Failed to create model via provider {provider}: {e}")
            # Fallback
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=effective_api_key or "sk-placeholder",
                base_url=effective_base_url or None,
                max_retries=max_retries,
            )

    @staticmethod
    def get_model(
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """获取 LangChain 聊天模型（带缓存）。

        Resolution order for provider:
        1. Explicit prefix in model string (e.g., "anthropic/claude-3-5-sonnet")
        2. MongoDB provider config (database-stored credentials)
        3. Provider registry (matches model by provider's matches_model())
        4. Global default from LLM_MODEL or LLM_PROVIDER_DEFAULT
        """
        model = model or _resolve_default_model_value()
        model_name_only = model.split("/")[-1] if "/" in model else model

        # 尝试从 provider 配置中获取凭证 (MongoDB)
        provider_config = _find_provider_for_model(model)
        if not provider_config:
            # Provider config may have changed after process startup; refresh once before falling back.
            refresh_provider_config_cache()
            provider_config = _find_provider_for_model(model)
        if provider_config:
            # 使用 provider 配置的凭证和 provider 类型
            effective_api_key = get_api_key("LLM_API_KEY")
            if api_key:
                effective_api_key = api_key
            if provider_config.get("api_key"):
                effective_api_key = provider_config.get("api_key")
            effective_base_url = (
                provider_config.get("base_url")
                or api_base
                or os.environ.get("LLM_API_BASE")
                or getattr(settings, "LLM_API_BASE", None)
            )
            provider = provider_config["provider"]
            # Per-provider defaults (request param overrides provider config)
            effective_temperature = (
                temperature if temperature != 0.7 else provider_config.get("temperature", 0.7)
            )
            effective_max_tokens = max_tokens or provider_config.get("max_tokens", 4096)
            effective_max_retries = provider_config.get("max_retries", settings.LLM_MAX_RETRIES)
        else:
            # Fallback: 使用 Provider Registry 推断 provider
            effective_api_key = get_api_key("LLM_API_KEY")
            if api_key:
                effective_api_key = api_key
            effective_base_url = (
                api_base
                or os.environ.get("LLM_API_BASE")
                or getattr(settings, "LLM_API_BASE", None)
            )
            registry = _get_registry()
            provider_instance = registry.get_provider_for_model(model)
            if provider_instance:
                provider = provider_instance.config.name
            else:
                # 最终 fallback: 使用全局默认 provider
                default_provider = getattr(settings, "LLM_PROVIDER_DEFAULT", None)
                if default_provider:
                    provider = default_provider
                else:
                    provider, _ = _parse_provider(model)
            effective_temperature = temperature
            effective_max_tokens = max_tokens or 4096
            effective_max_retries = settings.LLM_MAX_RETRIES

        # max_input_tokens can be set per-request or via provider config

        cache_key = _make_cache_key(
            provider,
            model_name_only,
            effective_temperature,
            effective_max_tokens,
            effective_api_key,
            effective_base_url,
            thinking,
            profile,
            effective_max_retries,
        )

        if cache_key in LLMClient._model_cache:
            return LLMClient._model_cache[cache_key]

        # LRU 淘汰：如果缓存满了，删除最旧的
        max_cache_size = LLMClient._get_max_cache_size()
        if len(LLMClient._model_cache) >= max_cache_size:
            # 删除第一个（最旧的）
            oldest_key = next(iter(LLMClient._model_cache))
            oldest_model = LLMClient._model_cache.pop(oldest_key)

            # 尝试关闭 HTTP 客户端连接池，防止连接泄漏
            try:
                # ChatAnthropic 和 ChatOpenAI 使用 httpx.AsyncClient
                if hasattr(oldest_model, "async_client"):
                    client = oldest_model.async_client
                    if hasattr(client, "aclose"):
                        task = asyncio.create_task(client.aclose())
                        task.add_done_callback(lambda t: None)  # prevent GC
                elif hasattr(oldest_model, "client"):
                    client = oldest_model.client
                    if hasattr(client, "aclose"):
                        task = asyncio.create_task(client.aclose())
                        task.add_done_callback(lambda t: None)  # prevent GC
            except Exception as e:
                logger.debug(f"Failed to close LLM client connections: {e}")

            logger.info(f"LLM cache full ({max_cache_size}), evicted oldest model")

        logger.info(f"Creating {provider} model: {model_name_only}")
        instance = LLMClient._create_model(
            provider,
            model_name_only,
            temperature=effective_temperature,
            max_tokens=effective_max_tokens,
            api_key=effective_api_key,
            api_base=effective_base_url,
            thinking=thinking,
            profile=profile,
            max_retries=effective_max_retries,
            **kwargs,
        )
        LLMClient._model_cache[cache_key] = instance
        return instance

    @staticmethod
    def get_langgraph_model(
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """获取 LangGraph 配置的模型。"""
        return LLMClient.get_model(model=model, **kwargs)

    @staticmethod
    def clear_cache_by_model(model_pattern: Optional[str] = None) -> int:
        """清除匹配的模型缓存条目。

        Args:
            model_pattern: 模型名匹配模式（支持子串匹配），None 表示清除所有

        Returns:
            清除的条目数量
        """
        if model_pattern is None:
            count = len(LLMClient._model_cache)
            LLMClient._model_cache.clear()
            return count

        to_delete = []
        for key in LLMClient._model_cache:
            _, model_name, *_ = key
            if model_pattern in model_name:
                to_delete.append(key)

        for key in to_delete:
            del LLMClient._model_cache[key]
        return len(to_delete)


@lru_cache
def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例（单例）"""
    return LLMClient()

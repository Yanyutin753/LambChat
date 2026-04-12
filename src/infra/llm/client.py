"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import asyncio
from functools import lru_cache
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# 使用 Anthropic 兼容接口的 provider
_ANTHROPIC_PROVIDERS = {"anthropic", "minimax", "zai"}

# 使用 Google Gemini 兼容接口的 provider
_GOOGLE_PROVIDERS = {"google", "gemini"}


def _parse_provider(model: str) -> tuple[str, str]:
    """从模型标识解析 provider 和 model_name。

    Returns:
        (provider, model_name)，如 ("anthropic", "claude-3-5-sonnet-20241022")
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        model_name = model
        if model_name.startswith("claude"):
            provider = "anthropic"
        elif model_name.startswith("gemini"):
            provider = "gemini"
        else:
            provider = "openai"
    return provider, model_name


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


def _safe_close_client(model_instance: BaseChatModel) -> None:
    """Safely close HTTP client with error logging."""
    try:
        _client = getattr(model_instance, "async_client", None) or getattr(
            model_instance, "client", None
        )
        if _client and hasattr(_client, "aclose"):

            def _on_close_done(t: asyncio.Task) -> None:
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.debug(f"Failed to close LLM client connections: {exc}")

            task = asyncio.create_task(_client.aclose())
            task.add_done_callback(_on_close_done)
    except Exception as e:
        logger.debug(f"Failed to close LLM client connections: {e}")


class LLMClient:
    """LLM 客户端工厂，支持实例缓存和 fallback。"""

    _model_cache: dict[tuple, BaseChatModel] = {}

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
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """根据 provider 创建对应的 LangChain 模型。"""

        kwargs.pop("max_retries", None)

        if provider in _ANTHROPIC_PROVIDERS:
            anthropic_kwargs: dict[str, Any] = {
                "model_name": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,  # type: ignore[arg-type]
                "thinking": thinking,
                "base_url": api_base or None,
                "max_retries": settings.LLM_MAX_RETRIES,
            }
            if api_key:
                anthropic_kwargs["api_key"] = SecretStr(api_key)
            if profile:
                anthropic_kwargs["profile"] = profile
            return ChatAnthropic(**anthropic_kwargs, **kwargs)
        if provider in _GOOGLE_PROVIDERS:
            if thinking and thinking.get("type") == "enabled":
                thinking_level = thinking.get("level", "medium")
            else:
                thinking_level = None
            google_kwargs: dict[str, Any] = {
                "model": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,  # type: ignore[arg-type]
                "base_url": api_base or None,
                "thinking_level": thinking_level,
                "max_retries": settings.LLM_MAX_RETRIES,
            }
            if api_key:
                google_kwargs["google_api_key"] = SecretStr(api_key)
            if profile:
                google_kwargs["profile"] = profile
            return ChatGoogleGenerativeAI(**google_kwargs, **kwargs)

        openai_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "streaming": True,
            "api_key": api_key or "sk-placeholder",
            "base_url": api_base or None,
            "max_retries": settings.LLM_MAX_RETRIES,
        }
        if profile:
            openai_kwargs["profile"] = profile
        return ChatOpenAI(**openai_kwargs, **kwargs)

    @staticmethod
    async def get_model(
        model: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        use_model_config: bool = True,
        **kwargs: Any,
    ) -> BaseChatModel:
        """获取 LangChain 聊天模型（带缓存）。

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet")
            model_id: Model config ID (UUID). When provided, looks up the model
                config directly by ID, which resolves to a specific channel/provider.
                This takes priority over the `model` parameter.
            temperature: Sampling temperature. If use_model_config=True and model config
                has temperature set, this parameter is ignored.
            max_tokens: Maximum tokens to generate. If use_model_config=True and model config
                has max_tokens set, this parameter is ignored.
            api_key: API key for the provider. If use_model_config=True and model config
                has api_key set, this parameter is ignored.
            api_base: Base URL for the API. If use_model_config=True and model config
                has api_base set, this parameter is ignored.
            thinking: Thinking mode configuration.
            profile: Per-model configuration (e.g., max_input_tokens).
            use_model_config: If True, look up model config from endpoint/static list
                and apply per-model overrides. Default True.
        """
        # ── model_id 优先：直接从 DB 按 ID 查找完整配置 ──
        if model_id:
            try:
                from src.infra.agent.model_storage import get_model_storage

                db_model = await get_model_storage().get(model_id)
                if db_model:
                    model = db_model.value
                    # 直接从 DB 配置获取所有覆盖参数
                    if not api_key and db_model.api_key:
                        api_key = db_model.api_key
                    if not api_base and db_model.api_base:
                        api_base = db_model.api_base
                    if db_model.temperature is not None:
                        temperature = db_model.temperature
                    if max_tokens is None and db_model.max_tokens is not None:
                        max_tokens = db_model.max_tokens
                    if profile is None and db_model.profile:
                        profile = (
                            db_model.profile.model_dump()
                            if hasattr(db_model.profile, "model_dump")
                            else db_model.profile
                        )
                    # 已从 DB 获取完整配置，跳过缓存查找
                    use_model_config = False
                    logger.debug(f"[LLMClient] Resolved model_id={model_id} -> value={model}")
            except Exception as e:
                logger.warning(f"[LLMClient] Failed to resolve model_id={model_id}: {e}")

        # Only resolve default model when actually needed
        resolved_default: Optional[str] = None

        if not model:
            from src.infra.llm.models_service import get_default_model

            resolved_default = await get_default_model()
            model = resolved_default
        provider, model_name = _parse_provider(model)

        # 当模型没有显式 provider 前缀（无 '/'）且与默认模型不同时，
        # 使用默认模型的 provider，确保 API 格式一致性。
        # 例如：代理服务(one-api/litellm)统一用 OpenAI 格式，
        # 切换到 claude-xxx 模型不应自动切换为 Anthropic 格式。
        if "/" not in model:
            from src.infra.llm.models_service import get_default_model

            resolved_default = resolved_default or await get_default_model()
            if resolved_default and model != resolved_default:
                default_provider, _ = _parse_provider(resolved_default)
                provider = default_provider

        # Look up per-model config for overrides
        if use_model_config:
            from src.infra.llm.models_service import get_available_models

            available_models = await get_available_models()
            # Build dict for O(1) lookup instead of O(n) scan
            model_map = {m.get("value"): m for m in available_models}
            model_cfg = model_map.get(model)
            if model_cfg:
                # Apply per-model overrides (explicit params still take priority)
                if not api_key and model_cfg.get("api_key"):
                    api_key = model_cfg["api_key"]
                if not api_base and model_cfg.get("api_base"):
                    api_base = model_cfg["api_base"]
                if model_cfg.get("temperature") is not None:
                    temperature = model_cfg["temperature"]
                if max_tokens is None and model_cfg.get("max_tokens") is not None:
                    max_tokens = model_cfg["max_tokens"]
                if profile is None and model_cfg.get("profile"):
                    profile = model_cfg["profile"]

            # Cache may not contain api_key (stripped for security).
            # Fall back to DB for the api_key.
            if not api_key and use_model_config:
                try:
                    from src.infra.agent.model_storage import get_model_storage

                    db_model = await get_model_storage().get_by_value(model)
                    if db_model and db_model.api_key:
                        api_key = db_model.api_key
                except Exception as e:
                    logger.debug(f"Failed to fetch api_key from DB for model {model}: {e}")

        cache_key = _make_cache_key(
            provider,
            model_name,
            temperature,
            max_tokens,
            api_key,
            api_base,
            thinking,
            profile,
            settings.LLM_MAX_RETRIES,
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
            _safe_close_client(oldest_model)

            logger.info(f"LLM cache full ({max_cache_size}), evicted oldest model")

        logger.info(f"Creating {provider} model: {model_name}")
        instance = LLMClient._create_model(
            provider,
            model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            api_base=api_base,
            thinking=thinking,
            profile=profile,
            **kwargs,
        )
        LLMClient._model_cache[cache_key] = instance
        return instance

    @staticmethod
    async def get_langgraph_model(
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """获取 LangGraph 配置的模型。"""
        return await LLMClient.get_model(model=model, **kwargs)

    @staticmethod
    def clear_cache_by_model(model_pattern: Optional[str] = None) -> int:
        """清除匹配的模型缓存条目。

        Args:
            model_pattern: 模型名匹配模式（支持子串匹配），None 表示清除所有

        Returns:
            清除的条目数量
        """
        if model_pattern is None:
            to_delete = list(LLMClient._model_cache.keys())
        else:
            to_delete = []
            for key in LLMClient._model_cache:
                _, model_name, *_ = key
                if model_pattern in model_name:
                    to_delete.append(key)

        for key in to_delete:
            evicted = LLMClient._model_cache.pop(key, None)
            if evicted:
                _safe_close_client(evicted)

        return len(to_delete)


@lru_cache
def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例（单例）"""
    return LLMClient()

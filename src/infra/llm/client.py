"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import asyncio
import os
from functools import lru_cache
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# Cache for raw settings from database (loaded once)
_setting_cache: dict[str, Any] = {}

# 使用 Anthropic 兼容接口的 provider
_ANTHROPIC_PROVIDERS = {"anthropic", "minimax", "zai"}


def _load_raw_settings():
    """Load raw sensitive settings from database (sync, for startup use only)"""
    global _setting_cache
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
    _load_raw_settings()
    if key in _setting_cache and _setting_cache[key]:
        return _setting_cache[key]

    env_value = os.environ.get(key)
    if env_value:
        return env_value

    if hasattr(settings, key):
        return getattr(settings, key)

    return None


def _parse_provider(model: str) -> tuple[str, str]:
    """从模型标识解析 provider 和 model_name。

    Returns:
        (provider, model_name)，如 ("anthropic", "claude-3-5-sonnet-20241022")
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        model_name = model
        provider = "anthropic" if model_name.startswith("claude") else "openai"
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
        api_key = api_key or settings.LLM_API_KEY
        api_base = api_base or settings.LLM_API_BASE

        kwargs.pop("max_retries", None)

        if provider in _ANTHROPIC_PROVIDERS:
            return ChatAnthropic(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,  # type: ignore[arg-type]
                api_key=SecretStr(api_key) if api_key else None,  # type: ignore[arg-type]
                thinking=thinking,
                base_url=api_base or None,
                profile=profile,
                max_retries=settings.LLM_MAX_RETRIES,
                **kwargs,
            )

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            streaming=True,
            api_key=api_key or "sk-placeholder",  # type: ignore[arg-type]
            base_url=api_base or None,
            profile=profile,
            max_retries=settings.LLM_MAX_RETRIES,
            **kwargs,
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
    ) -> BaseChatModel:
        """获取 LangChain 聊天模型（带缓存）。"""
        model = model or settings.LLM_MODEL
        provider, model_name = _parse_provider(model)

        if profile is None and settings.LLM_MAX_INPUT_TOKENS is not None:
            profile = {"max_input_tokens": settings.LLM_MAX_INPUT_TOKENS}

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
    def get_langgraph_model(
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
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

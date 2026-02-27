"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import logging
import os
from functools import lru_cache
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import SecretStr

from src.kernel.config import settings

logger = logging.getLogger(__name__)


# Cache for raw settings from database (loaded once)
_setting_cache: dict[str, Any] = {}


def _load_raw_settings():
    """Load raw sensitive settings from database (sync, for startup use)"""
    global _setting_cache
    if _setting_cache:
        return _setting_cache

    try:
        # Import here to avoid circular imports
        from src.infra.settings.service import get_settings_service

        # Try to get settings from database
        service = get_settings_service()
        if service:
            # Define sensitive keys to load
            sensitive_keys = [
                "LLM_API_KEY",
                "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY",
                "LANGSMITH_API_KEY",
                "EMBEDDING_API_KEY",
                "RERANK_API_KEY",
                "S3_ACCESS_KEY",
                "S3_SECRET_KEY",
                "REDIS_PASSWORD",
                "MILVUS_PASSWORD",
            ]
            for key in sensitive_keys:
                try:
                    import asyncio

                    value = asyncio.get_event_loop().run_until_complete(service.get_raw(key))
                    if value:
                        _setting_cache[key] = value
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Could not load raw settings from database: {e}")

    return _setting_cache


def get_api_key(key: str) -> Optional[str]:
    """
    Get API key with priority: database > env > settings
    This ensures sensitive values are read from database when available.
    """
    # Try to get from database first
    _load_raw_settings()
    if key in _setting_cache and _setting_cache[key]:
        return _setting_cache[key]

    # Then try explicit env
    env_value = os.environ.get(key)
    if env_value:
        return env_value

    # Finally try settings
    if hasattr(settings, key):
        return getattr(settings, key)

    return None


class LLMClient:
    """
    LLM 客户端工厂类

    创建 LangChain 兼容的聊天模型，支持实例缓存。
    """

    # 模型实例缓存：相同配置复用同一实例，避免每次请求重建
    _model_cache: dict[tuple, BaseChatModel] = {}

    @staticmethod
    def get_model(
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """
        获取 LangChain 聊天模型

        Args:
            model: 模型名称 (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            api_key: API 密钥
            api_base: 自定义 API 端点
            thinking: Anthropic extended thinking 配置，如 {"type": "enabled"}
            **kwargs: 其他模型特定参数

        Returns:
            LangChain BaseChatModel 实例
        """
        model = model or settings.LLM_MODEL
        model_name = model.split("/")[-1] if "/" in model else model
        provider = model.split("/")[0] if "/" in model else "openai"

        # 从模型名推断提供商
        if provider == model_name:
            if model_name.startswith("claude"):
                provider = "anthropic"
            elif model_name.startswith("gpt"):
                provider = "openai"
            else:
                provider = "openai"

        # 构建缓存 key（thinking dict 转 tuple 以便 hash）
        thinking_key = tuple(sorted(thinking.items())) if thinking else None
        cache_key = (provider, model_name, temperature, max_tokens, api_key, api_base, thinking_key)

        if cache_key in LLMClient._model_cache:
            return LLMClient._model_cache[cache_key]

        logger.info(f"Creating {provider} model: {model_name}")
        # 创建对应的 LangChain 模型
        if provider == "anthropic":
            instance = LLMClient._create_anthropic_model(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=api_base,
                thinking=thinking,
                **kwargs,
            )
        else:
            instance = LLMClient._create_openai_model(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                api_base=api_base,
                **kwargs,
            )

        LLMClient._model_cache[cache_key] = instance
        return instance

    @staticmethod
    def _create_anthropic_model(
        model_name: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """创建 Anthropic Claude 模型"""

        # 优先使用显式传入的参数，其次使用 settings（已在 initialize_settings 时从数据库加载）
        api_key = api_key or settings.ANTHROPIC_API_KEY or settings.LLM_API_KEY
        api_base = api_base or settings.ANTHROPIC_BASE_URL or settings.LLM_API_BASE

        return ChatAnthropic(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=SecretStr(api_key) if api_key else None,  # type: ignore[arg-type]
            thinking=thinking,
            base_url=api_base if api_base else None,
            **kwargs,
        )

    @staticmethod
    def _create_openai_model(
        model_name: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """创建 OpenAI 或 OpenAI 兼容模型"""
        # settings 已在 initialize_settings 时从数据库加载
        api_key = api_key or settings.LLM_API_KEY or "sk-placeholder"
        api_base = api_base or settings.LLM_API_BASE

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            streaming=True,
            api_key=api_key,  # type: ignore[arg-type]
            base_url=api_base if api_base else None,
            **kwargs,
        )

    @staticmethod
    @traceable(name="get_deep_agent_model", run_type="llm")
    def get_deep_agent_model(
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """
        获取 DeepAgent 配置的模型

        Args:
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            配置好的 LangChain 模型
        """
        return LLMClient.get_model(
            model=model or settings.LLM_MODEL,
            **kwargs,
        )

    @staticmethod
    def get_langgraph_model(
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """
        获取 LangGraph 配置的模型

        Args:
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            配置好的 LangChain 模型
        """
        return LLMClient.get_model(model=model, **kwargs)


@lru_cache
def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例（单例）"""
    return LLMClient()

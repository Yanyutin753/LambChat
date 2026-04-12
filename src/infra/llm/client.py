"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import asyncio
from collections import OrderedDict
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

# ── Provider 注册表 ──
# 每个条目: provider_slug → (协议类型, 模型名前缀列表)
# 协议类型: "anthropic" | "google" | "openai"
# 不在此注册表的 provider 统一走 OpenAI 兼容接口
PROVIDER_REGISTRY: dict[str, tuple[str, list[str]]] = {
    # Anthropic 协议
    "anthropic": ("anthropic", ["claude"]),
    "minimax": ("anthropic", ["abab", "minimax"]),
    # zai 在 _resolve_protocol 中动态路由：coding plan → anthropic，其余 → openai
    # Google 协议
    "google": ("google", ["gemini", "gemma"]),
    "gemini": ("google", ["gemini", "gemma"]),
    # OpenAI 兼容协议（显式列出，保持完整性）
    "openai": ("openai", ["gpt", "o1", "o3", "o4", "chatgpt"]),
    "deepseek": ("openai", ["deepseek"]),
    "meta": ("openai", ["llama"]),
    "mistral": ("openai", ["mistral", "mixtral"]),
    "qwen": ("openai", ["qwen"]),
    "groq": ("openai", ["groq"]),
    "xai": ("openai", ["grok"]),
    "cohere": ("openai", ["command"]),
    "zhipu": ("openai", ["glm", "chatglm"]),
    "moonshot": ("openai", ["moonshot", "kimi"]),
    "ollama": ("openai", []),
    "perplexity": ("openai", ["sonar"]),
    "stepfun": ("openai", ["step"]),
    "doubao": ("openai", ["doubao"]),
    "spark": ("openai", ["spark"]),
    "yi": ("openai", ["yi"]),
    "baichuan": ("openai", ["baichuan"]),
    "internlm": ("openai", ["internlm"]),
    "tencent": ("openai", ["hunyuan"]),
    "zeroone": ("openai", ["zero"]),
    # zai coding plan → Claude 协议
    "zai": ("anthropic", []),
}


def _resolve_protocol(provider: str) -> str:
    """解析 provider 对应的协议类型。"""
    entry = PROVIDER_REGISTRY.get(provider)
    return entry[0] if entry else "openai"


def _parse_provider(model: str) -> tuple[str, str]:
    """从模型标识解析 provider 和 model_name。

    支持格式:
      - "provider/model-name" → 直接取 provider 部分
      - "model-name" (无 /)  → 按前缀推断 provider

    Returns:
        (provider, model_name)，如 ("anthropic", "claude-3-5-sonnet-20241022")
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider, model_name

    # 无 / 时按模型名前缀推断
    lower = model.lower()
    for slug, (_, prefixes) in PROVIDER_REGISTRY.items():
        for prefix in prefixes:
            if lower.startswith(prefix):
                return slug, model

    return "openai", model


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
    """LLM 客户端工厂，支持 LRU 实例缓存和 fallback。"""

    _model_cache: OrderedDict[tuple, BaseChatModel] = OrderedDict()

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

        protocol = _resolve_protocol(provider)

        if protocol == "anthropic":
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
        if protocol == "google":
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
        """获取 LangChain 聊天模型（带 LRU 缓存）。

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
        explicit_provider: Optional[str] = None
        if model_id:
            try:
                from src.infra.agent.model_storage import get_model_storage

                db_model = await get_model_storage().get(model_id)
                if db_model:
                    model = db_model.value
                    if db_model.provider:
                        explicit_provider = db_model.provider
                    # 直接从 DB 配置获取所有覆盖参数
                    if not api_key and db_model.api_key:
                        api_key = db_model.api_key
                        from src.infra.llm.models_service import set_cached_api_key

                        set_cached_api_key(db_model.value, db_model.api_key)
                    if not api_base and db_model.api_base:
                        api_base = db_model.api_base
                    if db_model.temperature is not None:
                        temperature = db_model.temperature
                    if max_tokens is None and db_model.max_tokens is not None:
                        max_tokens = db_model.max_tokens
                    if profile is None and db_model.profile:
                        raw = db_model.profile
                        profile = (
                            raw.model_dump()
                            if hasattr(raw, "model_dump")
                            else dict(raw)
                            if isinstance(raw, dict)
                            else None
                        )
                    # 已从 DB 获取完整配置，跳过缓存查找
                    use_model_config = False
                    logger.debug(f"[LLMClient] Resolved model_id={model_id} -> value={model}")
            except Exception as e:
                logger.warning(f"[LLMClient] Failed to resolve model_id={model_id}: {e}")

        # Resolve default model (only once)
        resolved_default: Optional[str] = None
        if not model:
            from src.infra.llm.models_service import get_default_model

            resolved_default = await get_default_model()
            model = resolved_default

        provider, model_name = _parse_provider(model)

        # 显式 provider 优先于从 value 解析
        if explicit_provider:
            provider = explicit_provider

        # 当模型没有显式 provider 且没有 provider 前缀（无 '/'）且与默认模型不同时，
        # 使用默认模型的 provider，确保 API 格式一致性。
        if not explicit_provider and "/" not in model:
            if resolved_default is None:
                from src.infra.llm.models_service import get_default_model

                resolved_default = await get_default_model()
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
                if not explicit_provider and model_cfg.get("provider"):
                    explicit_provider = model_cfg["provider"]
                    provider = explicit_provider
                if not api_base and model_cfg.get("api_base"):
                    api_base = model_cfg["api_base"]
                if model_cfg.get("temperature") is not None:
                    temperature = model_cfg["temperature"]
                if max_tokens is None and model_cfg.get("max_tokens") is not None:
                    max_tokens = model_cfg["max_tokens"]
                if profile is None and model_cfg.get("profile"):
                    profile = model_cfg["profile"]

            # api_key: in-process cache → DB fallback
            if not api_key and use_model_config:
                # Check in-process api_key cache first
                from src.infra.llm.models_service import get_cached_api_key

                cached_key = get_cached_api_key(model)
                if cached_key:
                    api_key = cached_key
                else:
                    # DB fallback (populates api_key cache for next time)
                    try:
                        from src.infra.agent.model_storage import get_model_storage
                        from src.infra.llm.models_service import set_cached_api_key

                        db_model = await get_model_storage().get_by_value(model)
                        if db_model and db_model.api_key:
                            api_key = db_model.api_key
                            set_cached_api_key(model, db_model.api_key)
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

        # LRU cache hit — move to end (most recently used)
        if cache_key in LLMClient._model_cache:
            LLMClient._model_cache.move_to_end(cache_key)
            return LLMClient._model_cache[cache_key]

        # LRU 淘汰：如果缓存满了，删除最久未使用的
        max_cache_size = LLMClient._get_max_cache_size()
        if len(LLMClient._model_cache) >= max_cache_size:
            oldest_key, oldest_model = LLMClient._model_cache.popitem(last=False)

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

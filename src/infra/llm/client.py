"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import asyncio
import os
from collections import OrderedDict
from functools import lru_cache
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.model_profile import ModelProfile as LangChainModelProfile
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.infra.logging import get_logger
from src.kernel.config import settings
from src.kernel.exceptions import AuthorizationError
from src.kernel.schemas.model import ModelConfig

logger = get_logger(__name__)
_close_tasks: set[asyncio.Future[None]] = set()

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
    "moonshot": ("openai", ["moonshot"]),
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
    # Kimi → Claude (Anthropic) 协议
    "kimi": ("anthropic", []),
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
    streaming: bool,
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
        streaming,
    )


def _prompt_cache_key(provider: str, model_name: str) -> str:
    """Stable routing key for provider-side prompt cache locality."""
    safe_model = model_name.replace("/", ":")
    return f"lambchat:{provider}:{safe_model}"


def _langchain_profile(profile: Optional[dict]) -> Optional[dict]:
    """Return only profile keys understood by langchain-core."""
    if not profile:
        return None

    allowed_keys = set(LangChainModelProfile.__annotations__)
    return {
        key: value for key, value in profile.items() if key in allowed_keys and value is not None
    }


async def _lookup_stored_api_key(
    *,
    model_id: Optional[str],
    model_value: str,
) -> Optional[str]:
    """Resolve a per-model api_key from storage after sanitized cache misses."""
    try:
        from src.infra.agent.model_storage import get_model_storage
        from src.infra.llm.models_service import set_cached_api_key

        storage = get_model_storage()
        stored_model = (
            await storage.get(model_id) if model_id else await storage.get_by_value(model_value)
        )
        if stored_model and stored_model.api_key:
            set_cached_api_key(stored_model.value, stored_model.api_key)
            return stored_model.api_key
    except Exception as e:
        logger.debug("Failed to fetch api_key from DB for model %s: %s", model_value, e)
    return None


def _has_explicit_anthropic_auth_omission(kwargs: dict[str, Any]) -> bool:
    """Return whether callers intentionally omitted Anthropic auth headers."""
    default_headers = kwargs.get("default_headers")
    if not isinstance(default_headers, dict):
        return False
    for header_name in ("X-Api-Key", "Authorization"):
        if header_name not in default_headers:
            continue
        header_value = default_headers[header_name]
        if header_value is None or header_value.__class__.__name__ == "Omit":
            return True
    return False


def _has_env_provider_auth(protocol: str) -> bool:
    """Return whether provider SDKs can resolve credentials from process env."""
    if protocol == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if protocol == "google":
        return bool(os.environ.get("GOOGLE_API_KEY"))
    return False


def _safe_close_client(model_instance: BaseChatModel) -> None:
    """Safely close HTTP client with error logging."""
    try:
        _client = getattr(model_instance, "async_client", None) or getattr(
            model_instance, "client", None
        )
        if _client and hasattr(_client, "aclose"):

            def _on_close_done(t: asyncio.Future[None]) -> None:
                _close_tasks.discard(t)
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.debug(f"Failed to close LLM client connections: {exc}")

            task = asyncio.ensure_future(_client.aclose())
            _close_tasks.add(task)
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
        streaming: bool = True,
        **kwargs: Any,
    ) -> BaseChatModel:
        """根据 provider 创建对应的 LangChain 模型。"""

        kwargs.pop("max_retries", None)
        profile = _langchain_profile(profile)

        protocol = _resolve_protocol(provider)

        if protocol == "anthropic":
            # 将 thinking config 转换为 Anthropic API 格式
            anthropic_thinking = None
            effort = None
            if thinking and thinking.get("type") == "enabled":
                budget_tokens = thinking.get("budget_tokens")
                level = thinking.get("level", "medium")
                # 新版模型 (Claude 4.7+) 使用 output_config.effort
                # 旧版模型使用 budget_tokens
                # 两者都传，由 API 选择
                anthropic_thinking = {"type": "enabled"}
                if budget_tokens:
                    anthropic_thinking["budget_tokens"] = budget_tokens
                effort = level
            anthropic_kwargs: dict[str, Any] = {
                "model_name": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,  # type: ignore[arg-type]
                "thinking": anthropic_thinking,
                "effort": effort,
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
                # Google only accepts minimal/low/medium/high — map "max" to "high"
                if thinking_level == "max":
                    thinking_level = "high"
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
            "streaming": streaming,
            "api_key": api_key or "sk-placeholder",
            "base_url": api_base or None,
            "max_retries": settings.LLM_MAX_RETRIES,
        }
        # OpenAI 协议: 传递 reasoning_effort 给推理模型
        # 仅 OpenAI 官方模型 (provider="openai") 支持 reasoning_effort 参数。
        # 其他 OpenAI 兼容提供商 (DeepSeek、Qwen 等) 有各自的推理机制，
        # 发送 reasoning_effort 会触发不兼容的"思考模式"导致 API 报错。
        if thinking and thinking.get("type") == "enabled":
            if provider == "openai":
                level = thinking.get("level", "medium")
                openai_effort_map = {
                    "low": "low",
                    "medium": "medium",
                    "high": "high",
                    "max": "high",
                }
                openai_kwargs["reasoning_effort"] = openai_effort_map.get(level, "medium")
            else:
                logger.debug(
                    "Thinking requested but reasoning_effort not supported "
                    "for provider '%s' (model: %s); skipped.",
                    provider,
                    model_name,
                )
        if provider == "openai":
            model_kwargs = dict(openai_kwargs.get("model_kwargs") or kwargs.pop("model_kwargs", {}))
            model_kwargs.setdefault("prompt_cache_key", _prompt_cache_key(provider, model_name))
            model_kwargs.setdefault("prompt_cache_retention", "24h")
            openai_kwargs["model_kwargs"] = model_kwargs
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
        model_config: Optional[dict[str, Any] | ModelConfig] = None,
        use_model_config: bool = True,
        streaming: bool = True,
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
        # ── 已解析配置优先：聊天入口已做权限校验和 DB 查询，避免重复查库 ──
        explicit_provider: Optional[str] = None
        if model_config is not None:
            db_model = (
                model_config
                if isinstance(model_config, ModelConfig)
                else ModelConfig(**model_config)
            )
            if not db_model.enabled:
                raise AuthorizationError("model_disabled")
            model = db_model.value
            if db_model.id:
                model_id = db_model.id
            if db_model.provider:
                explicit_provider = db_model.provider
            if not api_key and db_model.api_key:
                api_key = db_model.api_key
                from src.infra.llm.models_service import set_cached_api_key

                set_cached_api_key(db_model.value, db_model.api_key)
            if not api_key:
                from src.infra.llm.models_service import get_cached_api_key

                cached_key = get_cached_api_key(db_model.value)
                if cached_key:
                    api_key = cached_key
                else:
                    api_key = await _lookup_stored_api_key(
                        model_id=db_model.id,
                        model_value=db_model.value,
                    )
            if not api_base and db_model.api_base:
                api_base = db_model.api_base
            if db_model.temperature is not None:
                temperature = db_model.temperature
            if max_tokens is None and db_model.max_tokens is not None:
                max_tokens = db_model.max_tokens
            if profile is None and db_model.profile:
                profile = db_model.profile.model_dump()
            use_model_config = False
        elif model_id:
            try:
                from src.infra.agent.model_storage import get_model_storage

                stored_model = await get_model_storage().get(model_id)
                if not stored_model:
                    raise AuthorizationError("model_not_found")
                if not stored_model.enabled:
                    raise AuthorizationError("model_disabled")
                model = stored_model.value
                if stored_model.provider:
                    explicit_provider = stored_model.provider
                # 直接从 DB 配置获取所有覆盖参数
                if not api_key and stored_model.api_key:
                    api_key = stored_model.api_key
                    from src.infra.llm.models_service import set_cached_api_key

                    set_cached_api_key(stored_model.value, stored_model.api_key)
                if not api_base and stored_model.api_base:
                    api_base = stored_model.api_base
                if stored_model.temperature is not None:
                    temperature = stored_model.temperature
                if max_tokens is None and stored_model.max_tokens is not None:
                    max_tokens = stored_model.max_tokens
                if profile is None and stored_model.profile:
                    raw = stored_model.profile
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
            except AuthorizationError:
                raise
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
        if not explicit_provider and "/" not in model and provider == "openai":
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
                    api_key = await _lookup_stored_api_key(
                        model_id=model_id,
                        model_value=model,
                    )

        protocol = _resolve_protocol(provider)
        if not api_key and not _has_env_provider_auth(protocol):
            if protocol == "anthropic" and not _has_explicit_anthropic_auth_omission(kwargs):
                raise AuthorizationError("model_api_key_missing")
            if protocol == "google":
                raise AuthorizationError("model_api_key_missing")

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
            streaming,
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
            streaming=streaming,
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

    @staticmethod
    def close_cached_models() -> int:
        """Close all cached model clients and clear the in-process cache."""
        cached_models = list(LLMClient._model_cache.values())
        LLMClient._model_cache.clear()
        for model in cached_models:
            _safe_close_client(model)
        return len(cached_models)

    @staticmethod
    async def drain_close_tasks(timeout: float = 10.0) -> None:
        """Wait for deferred HTTP client close tasks during graceful shutdown."""
        tasks = list(_close_tasks)
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=max(0.0, float(timeout)),
            )
        except asyncio.TimeoutError:
            logger.warning(
                "LLM client close task drain timed out with %s task(s) still active",
                len(_close_tasks),
            )
        _close_tasks.difference_update(tasks)


@lru_cache
def get_llm_client() -> LLMClient:
    """获取 LLM 客户端实例（单例）"""
    return LLMClient()

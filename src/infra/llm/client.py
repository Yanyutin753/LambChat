"""
LLM 客户端

提供 LangChain 兼容的 LLM 客户端。
"""

import asyncio
import json
import os
import platform
import re
from collections import OrderedDict
from functools import lru_cache
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.model_profile import ModelProfile as LangChainModelProfile
from pydantic import SecretStr

from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel as ChatAnthropic
from src.infra.llm.google_chat import LambChatGoogleChatModel as ChatGoogleGenerativeAI
from src.infra.llm.openai_chat import LambChatOpenAIChatModel as ChatOpenAI
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


def _resolve_use_responses(protocol: str, api_format: Optional[str]) -> bool:
    """决定 OpenAI 协议模型是否走 /v1/responses（否则 /v1/chat/completions）。

    仅 OpenAI 协议可切换；优先级：模型级 api_format > 全局
    LLM_OPENAI_API_FORMAT 设置，未识别的值一律回退 chat_completions。
    Anthropic/Google 协议没有该概念，恒为 False。
    """
    if protocol != "openai":
        return False
    fmt = api_format or getattr(settings, "LLM_OPENAI_API_FORMAT", None) or "chat_completions"
    return fmt == "responses"


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


def _effective_timeout(timeout: float) -> float | None:
    return timeout if timeout > 0 else None


# ── Anti-fingerprint default request headers ──
# 第三方中转常通过 User-Agent/x-app 指纹识别官方客户端并限制其他流量
# （如 Anthropic 封锁非 Claude Code 客户端）。按协议伪装成官方客户端，
# 与 opencode 等工具的做法一致；可用 LLM_REQUEST_HEADERS 设置覆盖。
# 版本号为硬编码的近似值（会过时），且未模拟 anthropic-beta/x-stainless-*
# 等全套指纹——属 best-effort 伪装，严格的指纹校验仍可能识别；需要更强
# 伪装时用模型级/全局请求头覆盖补齐。
_ANTHROPIC_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "claude-cli/2.1.5 (external, cli)",
    "x-app": "cli",
}
_OPENCODE_UA_VERSION = "1.0.260"


def _default_request_headers(protocol: str) -> dict[str, str]:
    """内置防封请求头；Google 协议的 langchain 封装不支持 default_headers，跳过。"""
    if protocol == "anthropic":
        return dict(_ANTHROPIC_DEFAULT_HEADERS)
    if protocol == "openai":
        return {
            "User-Agent": (
                f"opencode/{_OPENCODE_UA_VERSION} "
                f"({platform.system()} {platform.release()}; {platform.machine()})"
            )
        }
    return {}


def _settings_header_overrides() -> dict[str, str]:
    """解析可选的 LLM_REQUEST_HEADERS JSON 覆盖设置。"""
    raw = getattr(settings, "LLM_REQUEST_HEADERS", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("LLM_REQUEST_HEADERS is not valid JSON; ignoring")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("LLM_REQUEST_HEADERS must be a JSON object; ignoring")
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


def _merged_request_headers(
    protocol: str,
    kwargs: dict[str, Any],
    model_headers: Optional[dict[str, str]] = None,
) -> Optional[dict[str, Any]]:
    """合并防封默认头 + 设置覆盖 + 模型级覆盖 + 调用方 default_headers。

    优先级：调用方 kwargs > 模型级 request_headers > 设置覆盖 > 内置默认
    （调用方的 Omit 等哨兵值原样保留）。无可注入头时（Google 协议且调用方
    未传）返回 None，保持原有行为。
    """
    headers: dict[str, Any] = _default_request_headers(protocol)
    headers.update(_settings_header_overrides())
    if model_headers:
        headers.update(model_headers)
    caller = kwargs.get("default_headers")
    if isinstance(caller, dict):
        headers.update(caller)
    return headers or None


def _make_cache_key(
    provider: str,
    model_name: str,
    temperature: Optional[float],
    max_tokens: Optional[int],
    api_key: Optional[str],
    api_base: Optional[str],
    thinking: Optional[dict],
    profile: Optional[dict],
    max_retries: int,
    api_format: Optional[str] = None,
    header_overrides: Optional[tuple] = None,
) -> tuple:
    # 注意：header_overrides 只含全局/模型级覆盖；调用方 kwargs（含
    # default_headers）历来不参与 key——当前无调用方按次传 headers。
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
        _effective_timeout(settings.LLM_REQUEST_TIMEOUT),
        _effective_timeout(settings.LLM_FIRST_EVENT_TIMEOUT),
        api_format,
        header_overrides,
    )


def _langchain_profile(profile: Optional[dict]) -> Optional[dict]:
    """Return only profile keys understood by langchain-core."""
    if not profile:
        return None

    allowed_keys = set(LangChainModelProfile.__annotations__)
    return {
        key: value for key, value in profile.items() if key in allowed_keys and value is not None
    }


# ── Thinking-effort capability gating (issue #211) ──
# Maximum-compatibility policy: every model family only receives thinking
# parameters documented as supported by its provider; unverified combinations
# are never sent (prefer a silent no-op over a provider 400).

# OpenAI-protocol providers whose reasoning models accept reasoning_effort.
# o1 系不发送：o1-preview/o1-mini 不支持该参数（发送即 400），o1 已退役。
_REASONING_EFFORT_PREFIXES: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-5", "o3", "o4"),
    "xai": ("grok-4",),
}
# zhipu hybrid-reasoning GLM families that accept the `thinking` request-body
# field (via model_kwargs). glm-4.7 未核实，不发送。
_ZHIPU_THINKING_PREFIXES = (
    "glm-4.5",
    "glm-4-5",
    "glm-4.6",
    "glm-4-6",
    "glm-5",
)

# 次版本限定为 1-2 位数字且后不跟数字：防止把官方 model ID 里的发布日期
# 后缀（claude-opus-4-20250514 / grok-4-0709-beta）当成次版本吞掉——否则
# (4, 20250514) 会被误判进 effort era。
_CLAUDE_VERSION_RE = re.compile(r"claude-(?:[a-z]+-)*?(\d+)(?:[-.](\d{1,2})(?!\d))?")
_GEMINI_VERSION_RE = re.compile(r"gemini-(\d+)(?:[-.](\d{1,2})(?!\d))?")
_GROK_VERSION_RE = re.compile(r"grok-(\d+)(?:[-.](\d{1,2})(?!\d))?")

_EFFORT_BY_LEVEL = {"low": "low", "medium": "medium", "high": "high", "max": "high"}


def _version_tuple(match: "re.Match[str]") -> tuple[int, int]:
    return int(match.group(1)), int(match.group(2) or 0)


def _resolve_reasoning_effort(
    provider: str,
    model_name: str,
    thinking: dict[str, Any],
) -> Optional[str]:
    """Map a thinking config to reasoning_effort for OpenAI-protocol providers.

    Returns None when the provider/model family is not documented to accept
    reasoning_effort. Thinking is always enabled; only the level varies.
    """
    prefixes = _REASONING_EFFORT_PREFIXES.get(provider)
    if not prefixes:
        return None
    name = model_name.lower()
    # 固定档/非推理变体（gpt-5.1-chat-latest、grok-4-fast-non-reasoning 等）：
    # effort 不可配置，发送会 400
    if name.endswith("-chat-latest") or name.endswith("-non-reasoning"):
        return None
    if not any(name.startswith(prefix) for prefix in prefixes):
        return None

    level = str(thinking.get("level") or "medium")
    if provider == "xai" and level == "max":
        # grok 4.6+ 的 max 档映射到 xhigh
        match = _GROK_VERSION_RE.search(name)
        return "xhigh" if match and _version_tuple(match) >= (4, 6) else "high"
    return _EFFORT_BY_LEVEL.get(level, "medium")


def _resolve_zhipu_thinking_body(
    provider: str,
    model_name: str,
    thinking: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Map a thinking config to zhipu's `thinking` request-body field."""
    # 仅智谱官方端点已验证；第三方 GLM 托管（SiliconFlow/OpenRouter 等）不发送
    if provider != "zhipu":
        return None
    name = model_name.lower()
    if not any(name.startswith(prefix) for prefix in _ZHIPU_THINKING_PREFIXES):
        return None
    return {"thinking": {"type": "enabled"}}


def _resolve_anthropic_thinking(
    model_name: str,
    thinking: Optional[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[float]]:
    """Resolve (thinking_param, effort_param, temperature_override) for Claude.

    Family eras: legacy (<= claude-3-5) and the 4.6 gap accept nothing;
    manual era (3.7 ~ 4.5) uses thinking+budget_tokens with temperature=1;
    effort era (4.7+/5) uses effort only — manual "enabled" is rejected there
    (and triggers a client-side ValueError for claude-opus-5*).
    """
    if not thinking:
        # 未配置思考的调用方（标题生成/推荐等）保持原行为，不注入任何参数
        return None, None, None
    match = _CLAUDE_VERSION_RE.search(model_name.lower())
    if match is None:
        return None, None, None
    version = _version_tuple(match)

    if version[0] >= 5 or version >= (4, 7):
        level = str(thinking.get("level") or "low")
        effort = _EFFORT_BY_LEVEL.get(level, "low")
        # Newest models also reject non-default sampling parameters outright.
        return None, effort, 1.0
    if version == (4, 6):
        # Manual thinking returns 400 and adaptive thinking is only accepted
        # on 4.7+/Sonnet 5 — no verified combination, send nothing.
        return None, None, None
    if (3, 7) <= version <= (4, 5):
        manual: dict[str, Any] = {"type": "enabled"}
        # Anthropic 对 enabled thinking 强制要求 budget_tokens（>=1024）
        manual["budget_tokens"] = thinking.get("budget_tokens") or 1024
        # Manual thinking is incompatible with any temperature other than 1.
        return manual, None, 1.0
    return None, None, None


def _resolve_gemini_thinking_level(
    model_name: str,
    thinking: dict[str, Any],
) -> Optional[str]:
    """Map a thinking config to thinking_level for Gemini 2.5+ models."""
    if not thinking:
        # 未配置思考的调用方（标题生成/推荐等）保持原行为，不注入任何参数
        return None
    match = _GEMINI_VERSION_RE.search(model_name.lower())
    if match is None or _version_tuple(match) < (2, 5):
        return None
    level = str(thinking.get("level") or "medium")
    return _EFFORT_BY_LEVEL.get(level, "medium")


def model_supports_thinking(provider: Optional[str], model_value: str) -> bool:
    """Whether this provider+model combination receives any thinking parameter.

    Mirrors the capability gates used when constructing models (single source
    of truth with the resolvers above); powers frontend control visibility
    (show the intensity picker only for thinking-capable models). Provider
    resolution matches get_model: a stored explicit provider wins over the
    "provider/model" prefix, and the prefix is always stripped from the name.

    Known acceptable deviations (both only over-report, never mis-send):
    get_model's default-model provider inheritance for unprefixed generic
    values, and zhipu models configured with api_format="responses" (the
    thinking body is chat_completions-only) are not replicated here.
    """
    parsed_provider, model_name = _parse_provider(model_value)
    effective_provider = provider or parsed_provider
    protocol = _resolve_protocol(effective_provider)
    name = model_name.lower()

    if protocol == "anthropic":
        match = _CLAUDE_VERSION_RE.search(name)
        if match is None:
            return False
        version = _version_tuple(match)
        return (3, 7) <= version <= (4, 5) or version >= (4, 7)

    if protocol == "google":
        match = _GEMINI_VERSION_RE.search(name)
        return match is not None and _version_tuple(match) >= (2, 5)

    prefixes = _REASONING_EFFORT_PREFIXES.get(effective_provider)
    if prefixes:
        if name.endswith("-chat-latest") or name.endswith("-non-reasoning"):
            return False
        return any(name.startswith(prefix) for prefix in prefixes)
    if effective_provider == "zhipu":
        return any(name.startswith(prefix) for prefix in _ZHIPU_THINKING_PREFIXES)
    return False


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
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        api_format: Optional[str] = None,
        request_headers: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """根据 provider 创建对应的 LangChain 模型。

        temperature=None 表示不发送该参数（三家客户端字段均为 float | None
        = None，None 不会进入请求 payload），由 provider 默认值接管。
        """

        kwargs.pop("max_retries", None)
        profile = _langchain_profile(profile)

        protocol = _resolve_protocol(provider)

        # 防封请求头注入（OpenAI/Anthropic 协议；Google 封装不支持，跳过）
        request_headers = _merged_request_headers(protocol, kwargs, request_headers)
        if request_headers is not None:
            kwargs["default_headers"] = request_headers

        if protocol == "anthropic":
            # 按 Claude 家族分代门控（issue #211）：manual 时代（3.7~4.5）传
            # thinking+budget_tokens 并强制 temperature=1；4.7+/5 系只传 effort
            # （对这些模型传 manual thinking 会被 API 拒绝，claude-opus-5* 更会
            # 触发 langchain-anthropic 客户端 ValueError）；3-5 系与 4.6 不传。
            anthropic_thinking, effort, temperature_override = _resolve_anthropic_thinking(
                model_name, thinking
            )
            anthropic_kwargs: dict[str, Any] = {
                "model_name": model_name,
                "temperature": (
                    temperature_override if temperature_override is not None else temperature
                ),
                "max_tokens": max_tokens,  # type: ignore[arg-type]
                "thinking": anthropic_thinking,
                "effort": effort,
                "base_url": api_base or None,
                "max_retries": 0,
                "timeout": None,
                "first_event_timeout": _effective_timeout(settings.LLM_FIRST_EVENT_TIMEOUT),
                "non_streaming_timeout": _effective_timeout(settings.LLM_REQUEST_TIMEOUT),
            }
            if api_key:
                anthropic_kwargs["api_key"] = SecretStr(api_key)
            if profile:
                anthropic_kwargs["profile"] = profile
            return ChatAnthropic(**anthropic_kwargs, **kwargs)
        if protocol == "google":
            # 仅 Gemini 2.5+ 思考系接受 thinking_level；老模型与关闭档一律不传。
            # （langchain-google-genai 文档注明 2.5 系惯用 thinking_budget、3 系用
            # thinking_level；沿用本分支原有的 thinking_level 行为，非本次回归项。）
            thinking_level = _resolve_gemini_thinking_level(model_name, thinking or {})
            google_kwargs: dict[str, Any] = {
                "model": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,  # type: ignore[arg-type]
                "base_url": api_base or None,
                "thinking_level": thinking_level,
                # google-genai treats 1 as one initial request with no SDK retry.
                "max_retries": 1,
                "timeout": None,
                "first_event_timeout": _effective_timeout(settings.LLM_FIRST_EVENT_TIMEOUT),
                "non_streaming_timeout": _effective_timeout(settings.LLM_REQUEST_TIMEOUT),
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
            "max_retries": 0,
            "timeout": None,
            "stream_chunk_timeout": None,
            "first_event_timeout": _effective_timeout(settings.LLM_FIRST_EVENT_TIMEOUT),
            "non_streaming_timeout": _effective_timeout(settings.LLM_REQUEST_TIMEOUT),
        }
        # /v1/responses 线格式开关（模型级 api_format > 全局默认）。
        # 显式传 bool：None 会让 langchain-openai 自动探测，不满足确定性。
        openai_kwargs["use_responses_api"] = _resolve_use_responses(protocol, api_format)
        # OpenAI 协议：按 provider/模型家族门控思考参数（issue #211）
        # - openai/xai 推理模型收到 reasoning_effort；responses 模式下
        #   langchain-openai 会自动映射为 reasoning.effort
        # - zhipu GLM-4.5+/GLM-5 收到 `thinking` 请求体字段（经 model_kwargs，
        #   仅 chat completions 线格式；/v1/responses 不接受该字段）
        # - 其他 OpenAI 兼容提供商 (DeepSeek、Qwen 等) 有各自的推理机制，
        #   发送 reasoning_effort 会触发不兼容的"思考模式"导致 API 报错
        reasoning_effort: Optional[str] = None
        zhipu_thinking_body: Optional[dict[str, Any]] = None
        if thinking:
            reasoning_effort = _resolve_reasoning_effort(provider, model_name, thinking)
            if not openai_kwargs["use_responses_api"]:
                zhipu_thinking_body = _resolve_zhipu_thinking_body(provider, model_name, thinking)
            if reasoning_effort is None and zhipu_thinking_body is None:
                logger.debug(
                    "Thinking requested but no thinking parameter is supported "
                    "for provider '%s' (model: %s); skipped.",
                    provider,
                    model_name,
                )
        if reasoning_effort is not None:
            openai_kwargs["reasoning_effort"] = reasoning_effort
        if zhipu_thinking_body:
            model_kwargs = dict(kwargs.pop("model_kwargs", {}) or {})
            model_kwargs.update(zhipu_thinking_body)
            openai_kwargs["model_kwargs"] = model_kwargs
        if profile:
            openai_kwargs["profile"] = profile
        return ChatOpenAI(**openai_kwargs, **kwargs)

    @staticmethod
    async def get_model(
        model: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        model_config: Optional[dict[str, Any] | ModelConfig] = None,
        use_model_config: bool = True,
        api_format: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """获取 LangChain 聊天模型（带 LRU 缓存）。

        Args:
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet")
            model_id: Model config ID (UUID). When provided, looks up the model
                config directly by ID, which resolves to a specific channel/provider.
                This takes priority over the `model` parameter.
            temperature: Sampling temperature. None (default) omits the parameter
                on the wire so the provider default applies. If use_model_config=True
                and model config has temperature set, this parameter is ignored.
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
            api_format: Wire format for OpenAI-protocol providers
                ("chat_completions" | "responses"). Overridden by model config.
        """
        # ── 已解析配置优先：聊天入口已做权限校验和 DB 查询，避免重复查库 ──
        explicit_provider: Optional[str] = None
        model_request_headers: Optional[dict[str, str]] = None
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
            if not api_format and db_model.api_format:
                api_format = db_model.api_format
            if db_model.request_headers:
                model_request_headers = db_model.request_headers
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
                if not api_format and stored_model.api_format:
                    api_format = stored_model.api_format
                if stored_model.request_headers:
                    model_request_headers = stored_model.request_headers
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
                if not api_format and model_cfg.get("api_format"):
                    api_format = model_cfg["api_format"]
                if not model_request_headers and model_cfg.get("request_headers"):
                    model_request_headers = model_cfg["request_headers"]
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
            api_format,
            # 请求头覆盖参与缓存键：全局/模型级覆盖变化后重建模型实例
            (
                tuple(sorted(_settings_header_overrides().items())) or None,
                tuple(sorted(model_request_headers.items())) if model_request_headers else None,
            ),
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
            api_format=api_format,
            request_headers=model_request_headers,
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

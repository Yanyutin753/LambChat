"""Capability-gated thinking parameter resolution for the three protocol branches.

从 client.py 抽出的思考参数解析簇（#211 最大兼容策略）：每个模型家族只接收
其 provider 文档声明支持的思考参数，未核实组合一律不发。独立成模块以遵守
仓库 src/*.py ≤1000 行门禁（largeBackendModulesSource）。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.infra.llm.providers import (
    _parse_provider,
    _resolve_protocol,
    normalize_provider,
)
from src.infra.llm.providers import (
    is_zhipu_thinking_model as _is_zhipu_thinking_model,
)
from src.infra.llm.reasoning_patch import is_deepseek_thinking_model

# Maximum-compatibility policy: every model family only receives thinking
# parameters documented as supported by its provider; unverified combinations
# are never sent (prefer a silent no-op over a provider 400).

# OpenAI-protocol providers whose reasoning models accept reasoning_effort.
# o1 系不发送：o1-preview/o1-mini 不支持该参数（发送即 400），o1 已退役。
# gpt-6 系同 gpt-5 接受 reasoning_effort（-chat-latest/-non-reasoning 变体除外）。
_REASONING_EFFORT_PREFIXES: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-5", "gpt-6", "o3", "o4"),
    "xai": ("grok-4",),
    # deepseek V4 系官方接受 reasoning_effort（low/high/max，无 medium——
    # medium 映射到 high）；旧 V3 家族（deepseek-chat/r1/v3）不发送
    "deepseek": ("deepseek-flash", "deepseek-v4"),
}
# zhipu hybrid-reasoning GLM families that accept the `thinking` request-body
# field (via extra_body). glm-4.7 未核实，不发送。
# 前缀表与谓词已下沉 providers.py（reasoning_patch 复用），此处保留别名。


# 次版本限定为 1-2 位数字且后不跟数字：防止把官方 model ID 里的发布日期
# 后缀（claude-opus-4-20250514 / grok-4-0709-beta）当成次版本吞掉——否则
# (4, 20250514) 会被误判进 effort era。
_CLAUDE_VERSION_RE = re.compile(r"claude-(?:[a-z]+-)*?(\d+)(?:[-.](\d{1,2})(?!\d))?")
_GEMINI_VERSION_RE = re.compile(r"gemini-(\d+)(?:[-.](\d{1,2})(?!\d))?")
_GROK_VERSION_RE = re.compile(r"grok-(\d+)(?:[-.](\d{1,2})(?!\d))?")

_EFFORT_BY_LEVEL = {"low": "low", "medium": "medium", "high": "high", "max": "high"}


def _version_tuple(match: "re.Match[str]") -> tuple[int, int]:
    return int(match.group(1)), int(match.group(2) or 0)


def _resolve_glm_effort(model_name: str, thinking: dict[str, Any]) -> Optional[str]:
    match = re.match(r"glm-5[.-]([23])(?:[-\[]|$)", model_name.lower())
    if match is None or thinking.get("level") is None:
        return None
    level = str(thinking["level"])
    # GLM-5.2 folds low into high; GLM-5.3 supports low/high/max on both protocols.
    return {
        "low": "high" if match[1] == "2" else "low",
        "medium": "high",
        "high": "high",
        "max": "max",
    }.get(level)


def _resolve_reasoning_effort(
    provider: str,
    model_name: str,
    thinking: dict[str, Any],
) -> Optional[str]:
    """Map a thinking config to reasoning_effort for OpenAI-protocol providers.

    Returns None when the provider/model family is not documented to accept
    reasoning_effort. Thinking is always enabled; only the level varies.
    """
    provider = normalize_provider(provider)
    name = model_name.lower()
    glm_effort = _resolve_glm_effort(name, thinking)
    if glm_effort is not None:
        return glm_effort
    if is_deepseek_thinking_model(name):
        level = str(thinking.get("level") or "medium")
        return {"low": "low", "medium": "high", "high": "high", "max": "max"}.get(level, "high")
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
    if level == "max" and provider in {"openai", "xai"}:
        # max 档原生支持度按家族分野：gpt-6 与 grok-4.6+ 原生接受
        # max/xhigh；gpt-5/o3/o4 只到 high（发 max 会 400），降档处理
        if provider == "openai" and name.startswith("gpt-6"):
            return "max"
        if provider == "xai":
            match = _GROK_VERSION_RE.search(name)
            return "xhigh" if match and _version_tuple(match) >= (4, 6) else "high"
    return _EFFORT_BY_LEVEL.get(level, "medium")


def _resolve_zhipu_thinking_body(
    provider: str,
    model_name: str,
    thinking: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Map a thinking config to zhipu's `thinking` request-body field."""
    # 全渠道支持：任意 OpenAI 协议渠道上托管的 GLM 思考系都发送（中转对未知
    # body 字段透传或忽略）；强度由独立的 reasoning_effort 字段控制。
    name = model_name.lower()
    if not _is_zhipu_thinking_model(name):
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
    (and triggers a client-side ValueError for claude-opus-5*). Without a
    thinking config, 4.7+/5 still forces temperature=1 (they reject
    non-default sampling parameters, #1218); other families send nothing.
    """
    if is_deepseek_thinking_model(model_name):
        if not thinking:
            return None, None, None
        level = str(thinking.get("level") or "high")
        return {"type": "enabled"}, "high" if level == "medium" else level, None
    name = model_name.lower()
    match = _CLAUDE_VERSION_RE.search(name)
    if not thinking:
        # 未配置思考的调用方（标题生成/记忆压缩等）不注入思考参数；但 4.7+/5
        # 系拒绝非默认采样参数，辅助调用的 0.1/0.3 温度不得透传（#1218），
        # 回落默认 temperature=1.0；老家族保持原行为。
        if match is not None:
            version = _version_tuple(match)
            if version[0] >= 5 or version >= (4, 7):
                return None, None, 1.0
        return None, None, None
    # GLM 思考系挂在 Anthropic 协议渠道（zai 等）：注入 Claude Code 同款 thinking
    # 体（智谱 Anthropic 兼容端点直接接受）。5.2/5.3 同时传 output_config.effort；
    # 老家族保持原有行为。不覆盖 temperature（智谱无 Claude
    # manual thinking 的 temp=1 约束）。
    if _is_zhipu_thinking_model(name):
        glm_thinking: dict[str, Any] = {"type": "enabled"}
        glm_thinking["budget_tokens"] = thinking.get("budget_tokens") or 1024
        return glm_thinking, _resolve_glm_effort(name, thinking), None
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
    values, and GLM models configured with api_format="responses" (the
    thinking body is chat_completions-only) are not replicated here.
    """
    parsed_provider, model_name = _parse_provider(model_value)
    effective_provider = normalize_provider(provider or parsed_provider)
    protocol = _resolve_protocol(effective_provider)
    name = model_name.lower()

    if protocol == "anthropic":
        if _is_zhipu_thinking_model(name) or is_deepseek_thinking_model(name):
            return True
        match = _CLAUDE_VERSION_RE.search(name)
        if match is None:
            return False
        version = _version_tuple(match)
        return (3, 7) <= version <= (4, 5) or version >= (4, 7)

    if protocol == "google":
        match = _GEMINI_VERSION_RE.search(name)
        return match is not None and _version_tuple(match) >= (2, 5)

    if is_deepseek_thinking_model(name):
        return True
    prefixes = _REASONING_EFFORT_PREFIXES.get(effective_provider)
    if prefixes:
        if name.endswith("-chat-latest") or name.endswith("-non-reasoning"):
            return False
        if any(name.startswith(prefix) for prefix in prefixes):
            return True
    return _is_zhipu_thinking_model(name)

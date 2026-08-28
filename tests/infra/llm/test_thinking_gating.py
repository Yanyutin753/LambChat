"""Capability-gated thinking parameter construction for the three protocol branches.

Covers the maximum-compatibility policy from issue #211: every model family
only receives thinking parameters documented as supported; unverified
combinations are never sent (prefer a silent no-op over a provider 400).

The "off" level has been retired — thinking is always enabled, only the
intensity (low/medium/high/max) varies.
"""

from src.infra.llm.client import LLMClient, model_supports_thinking

_BUDGETS = {"low": 1024, "medium": 8192, "high": 32768, "max": 65536}
ENABLED = lambda level: {"type": "enabled", "level": level, "budget_tokens": _BUDGETS[level]}  # noqa: E731


def _openai_model(provider: str, model_name: str, thinking: dict | None):
    return LLMClient._create_model(
        provider,
        model_name,
        temperature=0.7,
        api_key="sk-test",
        thinking=thinking,
    )


def _anthropic_model(model_name: str, thinking: dict | None, temperature: float = 0.7):
    return LLMClient._create_model(
        "anthropic",
        model_name,
        temperature=temperature,
        api_key="sk-test",
        thinking=thinking,
    )


def _google_model(model_name: str, thinking: dict | None):
    return LLMClient._create_model(
        "google",
        model_name,
        temperature=0.7,
        api_key="sk-test",
        thinking=thinking,
    )


# ── OpenAI provider ──────────────────────────────────────────────────────


def test_openai_reasoning_models_receive_effort_per_level() -> None:
    for level, expected in [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("max", "high"),
    ]:
        model = _openai_model("openai", "gpt-5.5", ENABLED(level))
        assert model.reasoning_effort == expected


def test_openai_non_reasoning_models_never_receive_effort() -> None:
    for model_name in ("gpt-4o", "gpt-4o-mini", "gpt-4.1"):
        model = _openai_model("openai", model_name, ENABLED("high"))
        assert model.reasoning_effort is None, model_name


def test_openai_chat_latest_variants_receive_no_effort() -> None:
    model = _openai_model("openai", "gpt-5.1-chat-latest", ENABLED("low"))
    assert model.reasoning_effort is None


# ── xAI provider (grok) ──────────────────────────────────────────────────


def test_xai_grok46_receives_effort_per_level() -> None:
    for level, expected in [("low", "low"), ("medium", "medium"), ("high", "high")]:
        model = _openai_model("xai", "grok-4.6", ENABLED(level))
        assert model.reasoning_effort == expected
    model = _openai_model("xai", "grok-4.6", ENABLED("max"))
    assert model.reasoning_effort == "xhigh"


def test_xai_grok45_has_no_xhigh() -> None:
    model = _openai_model("xai", "grok-4.5", ENABLED("max"))
    assert model.reasoning_effort == "high"


def test_xai_older_grok_models_receive_nothing() -> None:
    model = _openai_model("xai", "grok-3-mini", ENABLED("high"))
    assert model.reasoning_effort is None


def test_xai_dated_alias_is_not_misread_as_47() -> None:
    # 回归：grok-4-0709-beta 的日期后缀曾被吞成次版本号 (4,709)，max 档误发 xhigh
    model = _openai_model("xai", "grok-4-0709-beta", ENABLED("max"))
    assert model.reasoning_effort == "high"


def test_xai_non_reasoning_variant_excluded() -> None:
    model = _openai_model("xai", "grok-4-fast-non-reasoning", ENABLED("low"))
    assert model.reasoning_effort is None


def test_openai_o1_family_not_supported() -> None:
    # o1-preview/o1-mini 不支持 reasoning_effort（发送即 400），o1 已退役 → 整族不发送
    for model_name in ("o1", "o1-mini", "o1-preview"):
        model = _openai_model("openai", model_name, ENABLED("low"))
        assert model.reasoning_effort is None, model_name


# ── zhipu provider (GLM) ─────────────────────────────────────────────────


def test_zhipu_glm4_receives_thinking_body() -> None:
    model = _openai_model("zhipu", "glm-4.6", ENABLED("low"))
    assert model.model_kwargs["thinking"] == {"type": "enabled"}
    model = _openai_model("zhipu", "glm-4.5-air", ENABLED("high"))
    assert model.model_kwargs["thinking"] == {"type": "enabled"}


def test_zhipu_glm5_receives_enabled_thinking() -> None:
    model = _openai_model("zhipu", "glm-5.3", ENABLED("medium"))
    assert model.model_kwargs["thinking"] == {"type": "enabled"}


def test_zhipu_legacy_models_receive_nothing() -> None:
    model = _openai_model("zhipu", "chatglm-3-turbo", ENABLED("low"))
    assert "thinking" not in model.model_kwargs
    assert model.reasoning_effort is None


def test_zhipu_unverified_families_receive_nothing() -> None:
    # glm-4.7 未在官方矩阵核实 → 不发送
    model = _openai_model("zhipu", "glm-4.7", ENABLED("low"))
    assert "thinking" not in model.model_kwargs


def test_zhipu_body_not_sent_to_other_providers_hosting_glm() -> None:
    # 第三方 GLM 托管（SiliconFlow/OpenRouter 等）只按模型名匹配时不得收到智谱字段
    for provider in ("openai", "deepseek", "siliconflow"):
        model = _openai_model(provider, "glm-4.6", ENABLED("low"))
        assert "thinking" not in model.model_kwargs, provider


def test_zhipu_does_not_receive_openai_cache_extensions() -> None:
    model = _openai_model("zhipu", "glm-4.6", ENABLED("low"))
    assert "prompt_cache_key" not in model.model_kwargs
    assert "prompt_cache_retention" not in model.model_kwargs


# ── other OpenAI-compatible providers keep current behaviour ────────────


def test_other_openai_protocol_providers_receive_no_thinking_params() -> None:
    for provider, model_name in (("deepseek", "deepseek-chat"), ("qwen", "qwen-max")):
        model = _openai_model(provider, model_name, ENABLED("medium"))
        assert model.reasoning_effort is None
        assert "thinking" not in model.model_kwargs


# ── Anthropic protocol branch ────────────────────────────────────────────


def test_claude_3_5_receives_no_thinking_params() -> None:
    model = _anthropic_model("claude-3-5-sonnet-latest", ENABLED("high"))
    assert model.thinking is None
    assert model.reasoning_effort is None


def test_claude_manual_era_receives_thinking_and_budget() -> None:
    for model_name in ("claude-opus-4-1-20250805", "claude-sonnet-4-5", "claude-3-7-sonnet-latest"):
        model = _anthropic_model(model_name, ENABLED("medium"))
        assert model.thinking == {"type": "enabled", "budget_tokens": 8192}, model_name
        assert model.reasoning_effort is None
        # manual thinking rejects any temperature other than 1
        assert model.temperature == 1.0, model_name


def test_claude_dated_ids_resolve_to_manual_era() -> None:
    # 回归：日期后缀（20250514）曾被正则吞成次版本号，导致 Claude 4 被误判
    # 进 effort era（发 output_config.effort 而不发 manual thinking）
    for model_name in (
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-opus-4-0-20250514",
    ):
        model = _anthropic_model(model_name, ENABLED("medium"))
        assert model.thinking == {"type": "enabled", "budget_tokens": 8192}, model_name
        assert model.reasoning_effort is None, model_name


def test_claude_4_6_gap_sends_nothing() -> None:
    model = _anthropic_model("claude-opus-4-6", ENABLED("medium"))
    assert model.thinking is None
    assert model.reasoning_effort is None


def test_claude_effort_era_receives_effort_only() -> None:
    for model_name in ("claude-opus-5", "claude-sonnet-5", "claude-opus-4-7"):
        model = _anthropic_model(model_name, ENABLED("low"))
        assert model.thinking is None, model_name
        assert model.reasoning_effort == "low", model_name
        # newest models also reject non-default sampling parameters
        assert model.temperature == 1.0, model_name


def test_claude_effort_era_max_maps_to_high() -> None:
    model = _anthropic_model("claude-opus-5", ENABLED("max"))
    assert model.reasoning_effort == "high"


def test_anthropic_without_thinking_config_keeps_current_behaviour() -> None:
    # 未配置思考的调用方（标题生成/推荐等）不应被注入任何参数
    model = _anthropic_model("claude-opus-5", None)
    assert model.thinking is None
    assert model.reasoning_effort is None
    assert model.temperature == 0.7


def test_anthropic_protocol_third_party_models_receive_nothing() -> None:
    for model_name in ("kimi-k2-instruct", "minimax-m2", "glm-4.7"):
        model = _anthropic_model(model_name, ENABLED("high"))
        assert model.thinking is None, model_name
        assert model.reasoning_effort is None, model_name


# ── Google protocol branch ───────────────────────────────────────────────


def test_gemini_2_5_receives_thinking_level_per_level() -> None:
    for level, expected in [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("max", "high"),
    ]:
        model = _google_model("gemini-2.5-flash", ENABLED(level))
        assert model.reasoning_effort == expected


def test_gemini_without_thinking_config_keeps_current_behaviour() -> None:
    # 未配置思考的调用方（标题生成/推荐/记忆压缩等）不应被注入任何思考参数
    model = _google_model("gemini-2.5-flash", None)
    assert model.reasoning_effort is None


def test_gemini_newer_families_supported() -> None:
    model = _google_model("gemini-3-pro-preview", ENABLED("low"))
    assert model.reasoning_effort == "low"


def test_gemini_old_models_receive_nothing() -> None:
    for model_name in (
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemma-3-27b-it",
        "gemini-flash-latest",
    ):
        model = _google_model(model_name, ENABLED("high"))
        assert model.reasoning_effort is None, model_name


def test_gemini_2_5_lite_variant_supported() -> None:
    model = _google_model("gemini-2.5-flash-lite", ENABLED("low"))
    assert model.reasoning_effort == "low"


# ── capability predicate (drives frontend control visibility) ────────────


def test_model_supports_thinking_openai_families() -> None:
    assert model_supports_thinking("openai", "gpt-5.5") is True
    assert model_supports_thinking("openai", "o3-mini") is True
    assert model_supports_thinking("openai", "o4-mini-high") is True
    assert model_supports_thinking("xai", "grok-4.6") is True
    assert model_supports_thinking("xai", "grok-4-fast") is True


def test_model_supports_thinking_openai_exclusions() -> None:
    assert model_supports_thinking("openai", "gpt-4o") is False
    assert model_supports_thinking("openai", "gpt-4.1") is False
    assert model_supports_thinking("openai", "o1") is False
    assert model_supports_thinking("openai", "gpt-5.1-chat-latest") is False
    assert model_supports_thinking("xai", "grok-4-fast-non-reasoning") is False
    assert model_supports_thinking("xai", "grok-3") is False


def test_model_supports_thinking_zhipu() -> None:
    assert model_supports_thinking("zhipu", "glm-4.6") is True
    assert model_supports_thinking("zhipu", "glm-4.5-air") is True
    assert model_supports_thinking("zhipu", "glm-5.3") is True
    assert model_supports_thinking("zhipu", "glm-4.7") is False
    assert model_supports_thinking("zhipu", "chatglm-3-turbo") is False
    # 第三方 GLM 托管不收智谱 thinking 字段
    assert model_supports_thinking("openai", "glm-4.6") is False
    assert model_supports_thinking("deepseek", "glm-4.6") is False


def test_model_supports_thinking_anthropic() -> None:
    # manual era (3.7~4.5) 与 effort era (4.7+/5) 都支持
    assert model_supports_thinking("anthropic", "claude-3-7-sonnet-latest") is True
    assert model_supports_thinking("anthropic", "claude-sonnet-4-5") is True
    assert model_supports_thinking("anthropic", "claude-opus-4-7") is True
    assert model_supports_thinking("anthropic", "claude-opus-5") is True


def test_model_supports_thinking_anthropic_exclusions() -> None:
    assert model_supports_thinking("anthropic", "claude-3-5-sonnet-latest") is False
    # 4.6 空档：无已核实组合，不发
    assert model_supports_thinking("anthropic", "claude-opus-4-6") is False
    # Anthropic 协议上的第三方模型（无 claude 前缀）
    assert model_supports_thinking("kimi", "kimi-k2-instruct") is False
    assert model_supports_thinking("minimax", "minimax-m2") is False


def test_model_supports_thinking_google() -> None:
    assert model_supports_thinking("google", "gemini-2.5-flash") is True
    assert model_supports_thinking("google", "gemini-2.5-flash-lite") is True
    assert model_supports_thinking("google", "gemini-3-pro-preview") is True
    assert model_supports_thinking("google", "gemini-2.0-flash") is False
    assert model_supports_thinking("google", "gemini-1.5-pro") is False
    assert model_supports_thinking("google", "gemma-3-27b-it") is False


def test_model_supports_thinking_other_openai_compatible() -> None:
    assert model_supports_thinking("deepseek", "deepseek-chat") is False
    assert model_supports_thinking("deepseek", "deepseek-reasoner") is False
    assert model_supports_thinking("qwen", "qwen-max") is False
    assert model_supports_thinking("moonshot", "kimi-k2") is False
    assert model_supports_thinking("ollama", "llama3") is False


def test_model_supports_thinking_strips_provider_prefix() -> None:
    # get_model 会剥掉 "provider/model" 前缀，谓词须与之一致
    assert model_supports_thinking("openai", "openai/gpt-5.5") is True
    assert model_supports_thinking("anthropic", "anthropic/claude-opus-5") is True
    assert model_supports_thinking("google", "google/gemini-2.5-flash") is True


def test_model_supports_thinking_infers_provider_when_missing() -> None:
    # 存储层 provider 缺失时按模型名前缀推断（与 _parse_provider 一致）
    assert model_supports_thinking(None, "glm-4.6") is True
    assert model_supports_thinking(None, "gpt-5.5") is True
    assert model_supports_thinking(None, "claude-opus-5") is True
    assert model_supports_thinking(None, "gemini-2.5-flash") is True
    assert model_supports_thinking(None, "deepseek-chat") is False


def test_model_supports_thinking_explicit_provider_wins() -> None:
    # 显式 provider 优先于 value 前缀：openai 渠道托管的 glm 收不到智谱字段
    assert model_supports_thinking("openai", "zhipu/glm-4.6") is False

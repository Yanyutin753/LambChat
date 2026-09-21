"""max_tokens 未配置时各协议的行为契约。

历史坑（2026-09-21 生产事故）：Anthropic Messages API 强制要求 max_tokens
字段，langchain-anthropic 在 ``max_tokens=None`` 时会经
``set_default_max_tokens`` 校验器静默填入 ``_FALLBACK_MAX_OUTPUT_TOKENS=4096``
（模型不在其内置 ``_MODEL_PROFILES`` 注册表时必命中）。4096 会截断 agent
长输出（实测 summarizer 单次输出即可达 ~10k tokens）。

修复后语义：

- openai 协议：未配置 = 不发送（None 透传，客户端字段为 None 时不进 payload），
  由 provider 默认值接管——与 temperature 未配置不发送（PR #250）同一契约；
- anthropic 协议：未配置 = 注入显式默认 ``ANTHROPIC_DEFAULT_MAX_TOKENS``，
  绝不让 langchain 的 4096 静默兜底生效；
- anthropic 协议同时校验 deepagents 输入预算
  （``int(max_input_tokens*0.95) - max_tokens``），预算过小时告警，
  避免「预算 58,928 < 摘要+尾部+system/tools 不可再压最小值」式卡死
  再次发生时无诊断线索。
"""

import logging

import pytest
from langchain_core.messages import HumanMessage

from src.infra.llm.budget import ANTHROPIC_DEFAULT_MAX_TOKENS
from src.infra.llm.client import LLMClient
from src.kernel.schemas.model import ModelConfig, ModelProfile


def _clear_cache():
    LLMClient._model_cache.clear()


@pytest.fixture(autouse=True)
def _isolate_model_cache():
    _clear_cache()
    yield
    _clear_cache()


# ── anthropic 协议：未配置时注入显式默认，而不是 langchain 的 4096 ─────────


@pytest.mark.asyncio
async def test_get_model_anthropic_max_tokens_none_gets_explicit_default() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="zai/glm-5.3",
            label="test",
            api_key="sk-test",
        )
    )
    assert model.max_tokens == ANTHROPIC_DEFAULT_MAX_TOKENS
    # 具体锚定：绝不能是 langchain 的静默兜底值
    assert model.max_tokens != 4096


@pytest.mark.asyncio
async def test_get_model_anthropic_payload_carries_explicit_default() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="zai/glm-5.3",
            label="test",
            api_key="sk-test",
        )
    )
    payload = model._get_request_payload([HumanMessage(content="hi")], stop=None)
    assert payload["max_tokens"] == ANTHROPIC_DEFAULT_MAX_TOKENS


@pytest.mark.asyncio
async def test_get_model_anthropic_max_tokens_configured_preserved() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="zai/glm-5.3",
            label="test",
            api_key="sk-test",
            max_tokens=8192,
        )
    )
    assert model.max_tokens == 8192


# ── openai 协议：未配置 = 真不发送 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_model_openai_max_tokens_none_stays_omitted() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="openai/gpt-4o",
            label="test",
            api_key="sk-test",
        )
    )
    payload = model._get_request_payload([HumanMessage(content="hi")], stop=None)
    assert "max_tokens" not in payload


@pytest.mark.asyncio
async def test_get_model_openai_max_tokens_configured_still_applied() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="openai/gpt-4o",
            label="test",
            api_key="sk-test",
            max_tokens=2048,
        )
    )
    assert model.max_tokens == 2048


# ── 输入预算过小时的告警（deepagents: int(limit*0.95) - max_tokens） ───────


@pytest.mark.asyncio
async def test_get_model_small_input_budget_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="src.infra.llm.client"):
        await LLMClient.get_model(
            model_config=ModelConfig(
                value="zai/glm-5.3",
                label="test",
                api_key="sk-test",
                max_tokens=45000,
                profile=ModelProfile(max_input_tokens=50000),
            )
        )
    assert any("input budget" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_model_healthy_input_budget_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="src.infra.llm.client"):
        await LLMClient.get_model(
            model_config=ModelConfig(
                value="zai/glm-5.3",
                label="test",
                api_key="sk-test",
                max_tokens=32768,
                profile=ModelProfile(max_input_tokens=256000),
            )
        )
    assert not any("input budget" in r.message for r in caplog.records)

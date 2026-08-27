"""未配置 temperature 时不应向下游发送该参数。

历史行为：get_model 的 temperature 默认值硬编码 0.7，模型配置未填
temperature 时 0.7 原样下发到上游 API，覆盖了各 provider 自己的默认值
（通常为 1.0）。修复后语义：未配置 = 不发送（None），由模型侧默认值接管。

三个 LangChain 客户端（langchain-openai 1.5.0 / langchain-anthropic 1.5.6 /
langchain-google-genai 4.3.3）的 temperature 字段均为 float | None = None，
且 None 不会出现在请求 payload 中——本文件用实例属性 + payload 双重锚定
这一契约。
"""

import pytest
from langchain_core.messages import HumanMessage

from src.infra.llm.client import LLMClient, _make_cache_key
from src.kernel.schemas.model import ModelConfig


def _clear_cache():
    LLMClient._model_cache.clear()


@pytest.fixture(autouse=True)
def _isolate_model_cache():
    _clear_cache()
    yield
    _clear_cache()


# ── get_model：未配置时省略 temperature（回归主测试） ─────────────────────


@pytest.mark.asyncio
async def test_get_model_omits_temperature_when_unset() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="openai/gpt-4o",
            label="test",
            api_key="sk-test",
        )
    )
    assert model.temperature is None


@pytest.mark.asyncio
async def test_get_model_openai_payload_has_no_temperature_when_unset() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="openai/gpt-4o",
            label="test",
            api_key="sk-test",
        )
    )
    payload = model._get_request_payload([HumanMessage(content="hi")], stop=None)
    assert "temperature" not in payload


@pytest.mark.asyncio
async def test_get_model_configured_temperature_still_applied() -> None:
    model = await LLMClient.get_model(
        model_config=ModelConfig(
            value="openai/gpt-4o",
            label="test",
            api_key="sk-test",
            temperature=0.3,
        )
    )
    assert model.temperature == 0.3


# ── _create_model：None 在三种协议分支都直达客户端 ───────────────────────


def test_create_model_openai_accepts_none_temperature() -> None:
    model = LLMClient._create_model("openai", "gpt-4o", temperature=None, api_key="sk-test")
    assert model.temperature is None


def test_create_model_anthropic_accepts_none_temperature() -> None:
    model = LLMClient._create_model(
        "anthropic", "claude-sonnet-4-5", temperature=None, api_key="sk-test"
    )
    assert model.temperature is None


def test_create_model_google_accepts_none_temperature() -> None:
    model = LLMClient._create_model("google", "gemini-2.5-pro", temperature=None, api_key="sk-test")
    assert model.temperature is None


def test_anthropic_manual_thinking_still_forces_temperature_one() -> None:
    # manual thinking 与非 1 的 temperature 不兼容：即使整体未配置
    # temperature，thinking 开启时仍必须显式发送 1.0
    model = LLMClient._create_model(
        "anthropic",
        "claude-sonnet-4-5",
        temperature=None,
        api_key="sk-test",
        thinking={"type": "enabled", "level": "medium", "budget_tokens": 8192},
    )
    assert model.temperature == 1.0


# ── 缓存键：None 与显式取值不冲突 ────────────────────────────────────────


def test_cache_key_distinguishes_unset_from_explicit_temperature() -> None:
    base = ("openai", "gpt-test", None, None, "sk", None, None, None, 3)
    with_temp = ("openai", "gpt-test", 0.7, None, "sk", None, None, None, 3)
    assert _make_cache_key(*base) != _make_cache_key(*with_temp)

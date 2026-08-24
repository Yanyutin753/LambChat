from __future__ import annotations

import asyncio

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel
from src.infra.llm.openai_chat import LambChatOpenAIChatModel


@pytest.mark.parametrize(
    ("model", "base_class"),
    [
        (
            LambChatOpenAIChatModel(
                model="gpt-test",
                api_key="test-key",
                timeout=None,
                first_event_timeout=0.01,
            ),
            ChatOpenAI,
        ),
        (
            LambChatAnthropicChatModel(
                model="claude-test",
                api_key="test-key",
                timeout=None,
                first_event_timeout=0.01,
            ),
            ChatAnthropic,
        ),
    ],
)
async def test_provider_streams_are_unlimited_after_first_event(
    monkeypatch: pytest.MonkeyPatch,
    model,
    base_class,
) -> None:
    async def fake_astream(self, *args, **kwargs):
        del self, args, kwargs
        yield "started"
        await asyncio.sleep(0.02)
        yield "finished"

    monkeypatch.setattr(base_class, "_astream", fake_astream)
    stream = model._astream([])

    assert await anext(stream) == "started"
    assert await anext(stream) == "finished"


@pytest.mark.parametrize(
    ("model", "base_class"),
    [
        (
            LambChatOpenAIChatModel(
                model="gpt-test",
                api_key="test-key",
                timeout=None,
                first_event_timeout=0.01,
            ),
            ChatOpenAI,
        ),
        (
            LambChatAnthropicChatModel(
                model="claude-test",
                api_key="test-key",
                timeout=None,
                first_event_timeout=0.01,
            ),
            ChatAnthropic,
        ),
    ],
)
async def test_provider_streams_timeout_before_first_event(
    monkeypatch: pytest.MonkeyPatch,
    model,
    base_class,
) -> None:
    async def fake_astream(self, *args, **kwargs):
        del self, args, kwargs
        await asyncio.sleep(10)
        yield "never"

    monkeypatch.setattr(base_class, "_astream", fake_astream)

    with pytest.raises(asyncio.TimeoutError, match="first event"):
        await anext(model._astream([]))


@pytest.mark.parametrize(
    ("model", "base_class"),
    [
        (
            LambChatOpenAIChatModel(
                model="gpt-test",
                api_key="test-key",
                timeout=None,
                non_streaming_timeout=0.01,
            ),
            ChatOpenAI,
        ),
        (
            LambChatAnthropicChatModel(
                model="claude-test",
                api_key="test-key",
                timeout=None,
                non_streaming_timeout=0.01,
            ),
            ChatAnthropic,
        ),
    ],
)
async def test_provider_non_streaming_calls_have_a_completion_deadline(
    monkeypatch: pytest.MonkeyPatch,
    model,
    base_class,
) -> None:
    async def fake_agenerate(self, *args, **kwargs):
        del self, args, kwargs
        await asyncio.sleep(10)

    monkeypatch.setattr(base_class, "_agenerate", fake_agenerate)

    with pytest.raises(asyncio.TimeoutError):
        await model._agenerate([])


@pytest.mark.parametrize(
    ("model", "base_class"),
    [
        (
            LambChatOpenAIChatModel(
                model="gpt-test",
                api_key="test-key",
                timeout=None,
                non_streaming_timeout=None,
            ),
            ChatOpenAI,
        ),
        (
            LambChatAnthropicChatModel(
                model="claude-test",
                api_key="test-key",
                timeout=None,
                non_streaming_timeout=None,
            ),
            ChatAnthropic,
        ),
    ],
)
async def test_provider_non_streaming_calls_can_wait_without_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
    model,
    base_class,
) -> None:
    async def fake_agenerate(self, *args, **kwargs):
        del self, args, kwargs
        await asyncio.sleep(0)
        return "complete"

    monkeypatch.setattr(base_class, "_agenerate", fake_agenerate)

    assert await model._agenerate([]) == "complete"

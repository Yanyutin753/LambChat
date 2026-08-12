from __future__ import annotations

import asyncio

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from src.infra.llm.google_chat import LambChatGoogleChatModel


def _model(**kwargs) -> LambChatGoogleChatModel:
    return LambChatGoogleChatModel(
        model="gemini-3.1-pro-preview",
        google_api_key="test-key",
        max_retries=1,
        **kwargs,
    )


async def test_google_stream_only_times_out_before_first_event(monkeypatch) -> None:
    captured: dict = {}

    async def fake_astream(self, messages, **kwargs):
        del self, messages
        captured.update(kwargs)
        yield "started"
        await asyncio.sleep(0.02)
        yield "finished"

    monkeypatch.setattr(ChatGoogleGenerativeAI, "_astream", fake_astream)
    model = _model(first_event_timeout=0.01, non_streaming_timeout=0.02)
    stream = model._astream([])

    assert await anext(stream) == "started"
    assert await anext(stream) == "finished"
    assert "timeout" not in captured


async def test_google_stream_times_out_when_first_event_is_missing(monkeypatch) -> None:
    async def fake_astream(self, messages, **kwargs):
        del self, messages, kwargs
        await asyncio.sleep(10)
        yield "never"

    monkeypatch.setattr(ChatGoogleGenerativeAI, "_astream", fake_astream)
    model = _model(first_event_timeout=0.01, non_streaming_timeout=0.02)

    with pytest.raises(asyncio.TimeoutError, match="first event"):
        await anext(model._astream([]))


async def test_google_non_streaming_call_keeps_response_timeout(monkeypatch) -> None:
    captured: dict = {}

    async def fake_agenerate(self, messages, **kwargs):
        del self, messages
        captured.update(kwargs)
        return "complete"

    monkeypatch.setattr(ChatGoogleGenerativeAI, "_agenerate", fake_agenerate)
    model = _model(first_event_timeout=0.01, non_streaming_timeout=0.02)

    result = await model._agenerate([])

    assert result == "complete"
    assert captured["timeout"] == 0.02

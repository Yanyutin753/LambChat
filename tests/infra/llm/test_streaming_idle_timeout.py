"""流式 chunk 空闲超时（idle timeout）的测试。

背景（2026-09-05 生产事故 run_20260905032659）：new-api 中转到上游的流在
首事件之后停滞，`aiter_with_first_event_timeout` 只约束首个事件，之后
"yield the stream without limits"，run 挂死 8 小时且 trace 永远停在
running。本文件锁定新的 idle_timeout 参数语义与三协议适配器接线。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.infra.llm.streaming import aiter_with_first_event_timeout

CLIENT_SOURCE = Path("src/infra/llm/client.py").read_text()


async def test_idle_timeout_rejects_stalled_stream_after_first_event() -> None:
    async def chunks():
        yield "first"
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_first_event_timeout(chunks(), timeout=0.5, idle_timeout=0.05)

    assert await anext(stream) == "first"
    with pytest.raises(asyncio.TimeoutError, match="stalled.*0.05s"):
        await anext(stream)


async def test_idle_timeout_allows_chunks_arriving_within_deadline() -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.01)
        yield "b"
        await asyncio.sleep(0.01)
        yield "c"

    got = [
        item
        async for item in aiter_with_first_event_timeout(chunks(), timeout=0.5, idle_timeout=0.5)
    ]

    assert got == ["a", "b", "c"]


async def test_idle_timeout_can_be_disabled() -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.02)
        yield "b"

    got = [
        item
        async for item in aiter_with_first_event_timeout(chunks(), timeout=0.5, idle_timeout=None)
    ]

    assert got == ["a", "b"]


async def test_idle_timeout_non_positive_value_disables_it() -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.02)
        yield "b"

    got = [
        item async for item in aiter_with_first_event_timeout(chunks(), timeout=0.5, idle_timeout=0)
    ]

    assert got == ["a", "b"]


async def test_first_event_timeout_still_enforced_with_idle_timeout() -> None:
    async def chunks():
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_first_event_timeout(chunks(), timeout=0.01, idle_timeout=5)

    with pytest.raises(asyncio.TimeoutError, match="first event.*0.01s"):
        await anext(stream)


def test_stream_adapters_declare_stream_idle_timeout_field() -> None:
    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel
    from src.infra.llm.google_chat import LambChatGoogleChatModel
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    for model_cls in (
        LambChatOpenAIChatModel,
        LambChatAnthropicChatModel,
        LambChatGoogleChatModel,
    ):
        model = model_cls(model="m", api_key="sk-test", stream_idle_timeout=12.5)
        assert model.stream_idle_timeout == 12.5


def test_client_passes_idle_timeout_setting_to_all_adapters() -> None:
    from src.kernel.config.base import Settings

    assert Settings(_env_file=None).LLM_STREAM_IDLE_TIMEOUT == 120.0
    assert CLIENT_SOURCE.count("LLM_STREAM_IDLE_TIMEOUT") >= 3
    assert "stream_idle_timeout" in CLIENT_SOURCE

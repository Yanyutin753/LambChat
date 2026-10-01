"""流式 chunk 间隔告警（gap warn）的测试。

背景（2026-09-17 生产事故 run_20260917033552）：中转流在正文生成中途停滞
约 5.5 秒后恢复，恢复点落在 LaTeX token 中间，停滞期间已生成的内容被中转
丢弃，用户看到正文整段缺失。idle_timeout（默认 120s）只防挂死，盖不住
这种亚阈值停滞；gap_warn_timeout 以纯观测方式补上盲区——只告警、不干预。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from src.infra.llm.streaming import aiter_with_first_event_timeout

CLIENT_SOURCE = Path("src/infra/llm/client.py").read_text()


def _gap_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "stream gap" in r.getMessage()]


async def test_gap_beyond_threshold_warns_with_context_and_resumed_chunk(caplog) -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.05)
        yield "b"

    with caplog.at_level(logging.WARNING):
        got = [
            item
            async for item in aiter_with_first_event_timeout(
                chunks(),
                timeout=0.5,
                gap_warn_timeout=0.01,
                gap_warn_context="gpt-test",
                gap_describe=lambda item: f"id-{item}",
            )
        ]

    assert got == ["a", "b"]
    warnings = _gap_warnings(caplog)
    assert len(warnings) == 1
    assert "gpt-test" in warnings[0]
    # 恢复点 chunk 标识必须入日志，便于与 trace 里的 text_id 对账
    assert "id-b" in warnings[0]


async def test_gap_within_threshold_stays_silent(caplog) -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.005)
        yield "b"

    with caplog.at_level(logging.WARNING):
        got = [
            item
            async for item in aiter_with_first_event_timeout(
                chunks(), timeout=0.5, gap_warn_timeout=0.5
            )
        ]

    assert got == ["a", "b"]
    assert _gap_warnings(caplog) == []


async def test_gap_warn_disabled_by_none_or_non_positive(caplog) -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(0.02)
        yield "b"

    for extra in ({"gap_warn_timeout": None}, {"gap_warn_timeout": 0}, {"gap_warn_timeout": -1}):
        with caplog.at_level(logging.WARNING):
            got = [
                item
                async for item in aiter_with_first_event_timeout(chunks(), timeout=0.5, **extra)
            ]
        assert got == ["a", "b"]
        assert _gap_warnings(caplog) == []


async def test_gap_warn_does_not_interfere_with_idle_timeout() -> None:
    async def chunks():
        yield "a"
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_first_event_timeout(
        chunks(),
        timeout=0.5,
        idle_timeout=0.05,
        gap_warn_timeout=0.01,
    )

    assert await anext(stream) == "a"
    with pytest.raises(asyncio.TimeoutError, match="stalled.*0.05s"):
        await anext(stream)


def test_stream_adapters_declare_stream_gap_warn_timeout_field() -> None:
    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel
    from src.infra.llm.google_chat import LambChatGoogleChatModel
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    for model_cls in (
        LambChatOpenAIChatModel,
        LambChatAnthropicChatModel,
        LambChatGoogleChatModel,
    ):
        model = model_cls(model="m", api_key="sk-test", stream_gap_warn_timeout=7.5)
        assert model.stream_gap_warn_timeout == 7.5


def test_client_passes_gap_warn_setting_to_all_adapters() -> None:
    from src.kernel.config.base import Settings

    assert Settings(_env_file=None).LLM_STREAM_GAP_WARN_TIMEOUT == 10.0
    assert CLIENT_SOURCE.count("LLM_STREAM_GAP_WARN_TIMEOUT") >= 3

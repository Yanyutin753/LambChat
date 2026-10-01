"""空 content message:chunk 告警的测试。

背景（2026-09-17 生产事故 run_20260917033552）：中转流中断重接后在 trace
里留下一条没有 content 的 message:chunk（seq=10），它是上游丢内容的接缝
痕迹。健康链路里 present_text 的 content 恒为非空字符串，这类事件出现即
异常，落库前在此留痕。
"""

from __future__ import annotations

import logging

import pytest

from src.infra.session.dual_writer import DualEventWriter


class _FakeRedis:
    def __init__(self) -> None:
        self.xadd_calls: list[tuple[str, dict]] = []

    async def xadd(self, stream_key: str, fields: dict) -> None:
        self.xadd_calls.append((stream_key, fields))

    async def ttl(self, stream_key: str) -> int:
        return -1

    async def expire(self, stream_key: str, ttl: int) -> None:
        return None


@pytest.fixture
def writer() -> DualEventWriter:
    w = DualEventWriter()
    w._redis = _FakeRedis()
    return w


def _empty_chunk_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "Empty message:chunk" in r.getMessage()]


async def test_missing_content_message_chunk_warns(writer: DualEventWriter, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await writer.write_event(
            session_id="s1",
            event_type="message:chunk",
            data={"text_id": "lc_run--x"},
            trace_id=None,
            run_id="r1",
        )

    warnings = _empty_chunk_warnings(caplog)
    assert len(warnings) == 1
    assert "s1" in warnings[0]
    assert "r1" in warnings[0]


async def test_empty_string_content_message_chunk_warns(writer: DualEventWriter, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await writer.write_event(
            session_id="s1",
            event_type="message:chunk",
            data={"content": "", "text_id": "lc_run--x"},
            trace_id=None,
        )

    assert len(_empty_chunk_warnings(caplog)) == 1


async def test_non_empty_content_stays_silent(writer: DualEventWriter, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await writer.write_event(
            session_id="s1",
            event_type="message:chunk",
            data={"content": "正文", "text_id": "lc_run--x"},
            trace_id=None,
        )

    assert _empty_chunk_warnings(caplog) == []


async def test_other_event_types_stay_silent(writer: DualEventWriter, caplog) -> None:
    for event_type, data in (
        ("metadata", {}),
        ("tool:start", {"tool": "web_search"}),
        ("done", {"status": "completed"}),
    ):
        with caplog.at_level(logging.WARNING):
            await writer.write_event(
                session_id="s1",
                event_type=event_type,
                data=data,
                trace_id=None,
            )

    assert _empty_chunk_warnings(caplog) == []

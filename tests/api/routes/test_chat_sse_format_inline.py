"""SSE 事件格式化内联执行的回归测试。

_format_sse_event 的输出被 CHAT_SSE_DATA_MAX_BYTES (256KB) 封顶，
成本有界，无需逐事件走线程池（每 token 一次线程跳变的开销远大于格式化本身）。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_stream_events_format_inline_without_thread_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    from src.api.routes import chat

    async def _fail_run_blocking_io(func, *args, **kwargs):
        raise AssertionError("SSE event formatting should run inline, not via run_blocking_io")

    monkeypatch.setattr(chat, "run_blocking_io", _fail_run_blocking_io, raising=False)

    # 直接驱动 event_generator 内的格式化路径不可行（需完整会话栈），
    # 这里通过源码结构断言两个 yield 点均已内联。
    import inspect

    source = inspect.getsource(chat)
    assert "run_blocking_io(_format_sse_event" not in source
    assert "_format_sse_event(event)" in source


@pytest.mark.asyncio
async def test_format_sse_event_output_shape_unchanged() -> None:
    from src.api.routes.chat_sse import _format_sse_event

    event = {
        "event_type": "message:chunk",
        "data": {"content": "hello"},
        "timestamp": "2026-01-01T00:00:00Z",
        "id": "1-0",
    }
    formatted = _format_sse_event(event)
    assert formatted.startswith("event: message:chunk\ndata: ")
    assert formatted.endswith("\nid: 1-0\n\n")
    assert '"_timestamp"' in formatted

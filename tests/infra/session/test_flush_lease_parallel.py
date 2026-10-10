"""flush 批内多会话的租约获取/释放应并行执行（串行时 2N+1 次 Mongo 往返）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.infra.session import dual_writer


class _ParallelProbeTrace:
    """记录租约调用并允许用事件验证并行性。"""

    def __init__(
        self, *, fail_sessions: set[str] | None = None, expected_sessions: int = 1
    ) -> None:
        self.acquire_started: dict[str, asyncio.Event] = {}
        self.release_calls: list[str] = []
        self.fail_sessions = fail_sessions or set()
        self.expected_sessions = expected_sessions

    async def acquire_session_trace_write(self, session_id: str) -> bool:
        self.acquire_started.setdefault(session_id, asyncio.Event()).set()
        if session_id in self.fail_sessions:
            return False
        # 等全部会话的 acquire 同时在飞（串行实现会在此超时）
        async with asyncio.Lock():
            pass
        while len(self.acquire_started) < self.expected_sessions:
            await asyncio.sleep(0.01)
            if len(self.acquire_started) >= self.expected_sessions:
                break
        else:
            pass
        # 给串行实现一个明确的失败窗口
        for _ in range(200):
            if len(self.acquire_started) >= self.expected_sessions:
                return True
            await asyncio.sleep(0.01)
        raise TimeoutError("acquire 串行执行：其他会话的 acquire 未并发启动")

    async def release_session_trace_write(self, session_id: str) -> None:
        self.release_calls.append(session_id)


def _buffer_item(session_id: str) -> Any:
    # MongoBufferItem 字段顺序：trace_id, event_type, data, session_id, run_id, timestamp
    return ("trace-1", "message:chunk", {"data": {}}, session_id, "run-1", None)


@pytest.mark.asyncio
async def test_flush_acquires_leases_for_multiple_sessions_concurrently() -> None:
    probe = _ParallelProbeTrace(expected_sessions=3)
    writer = dual_writer.DualEventWriter()
    writer._mongo_buffer = [_buffer_item("s1"), _buffer_item("s2"), _buffer_item("s3")]
    writer._trace = probe  # type: ignore[assignment]

    flushed: list[Any] = []

    async def _flush(batch: list[Any]) -> None:
        flushed.append(batch)

    writer._flush_mongo_batch = _flush  # type: ignore[method-assign]

    await asyncio.wait_for(writer._do_flush(), timeout=4)

    assert len(flushed) == 1
    assert sorted(probe.release_calls) == ["s1", "s2", "s3"]


@pytest.mark.asyncio
async def test_flush_persists_healthy_sessions_when_another_session_lease_is_blocked() -> None:
    probe = _ParallelProbeTrace(fail_sessions={"s2"}, expected_sessions=3)
    writer = dual_writer.DualEventWriter()
    batch = [_buffer_item("s1"), _buffer_item("s2"), _buffer_item("s3")]
    writer._mongo_buffer = list(batch)
    writer._trace = probe  # type: ignore[assignment]

    flushed: list[Any] = []

    async def _flush(items: list[Any]) -> None:
        flushed.append(items)

    writer._flush_mongo_batch = _flush  # type: ignore[method-assign]

    await asyncio.wait_for(writer._do_flush(), timeout=4)

    assert flushed == [[batch[0], batch[2]]]
    assert writer._mongo_buffer == [batch[1]]
    # 已拿到的 s1/s3 租约被释放，s2 未拿不释放
    assert sorted(probe.release_calls) == ["s1", "s3"]


def _base(item: Any) -> str:
    from src.infra.session.dual_writer import _buffer_item_base

    return _buffer_item_base(item)[3]


@pytest.mark.asyncio
async def test_flush_release_failure_is_logged_not_swallowed_silently() -> None:
    """release 失败必须记 warning（租约泄漏会永久阻塞附件删除 fence），且不影响已成功的写入。"""

    class _ReleaseFailingTrace(_ParallelProbeTrace):
        def __init__(self) -> None:
            super().__init__(expected_sessions=1)
            self.warnings: list[str] = []

        async def release_session_trace_write(self, session_id: str) -> None:
            raise RuntimeError("mongo down")

    probe = _ReleaseFailingTrace()
    writer = dual_writer.DualEventWriter()
    writer._mongo_buffer = [_buffer_item("s1")]
    writer._trace = probe  # type: ignore[assignment]

    flushed: list[Any] = []

    async def _flush(batch: list[Any]) -> None:
        flushed.append(batch)

    writer._flush_mongo_batch = _flush  # type: ignore[method-assign]

    records: list[Any] = []

    class _Handler:
        def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
            records.append(msg % args if args else msg)

    logger = dual_writer.logger
    dual_writer.logger = _Handler()  # type: ignore[assignment]
    try:
        await asyncio.wait_for(writer._do_flush(), timeout=4)
    finally:
        dual_writer.logger = logger  # type: ignore[assignment]

    assert len(flushed) == 1  # 写入本身成功，不被 release 失败误报
    assert any("s1" in str(r) and "release" in str(r).lower() for r in records)


@pytest.mark.asyncio
async def test_flush_retries_only_blocked_session_after_lease_recovers() -> None:
    probe = _ParallelProbeTrace(fail_sessions={"s2"}, expected_sessions=2)
    writer = dual_writer.DualEventWriter()
    batch = [_buffer_item("s1"), _buffer_item("s2")]
    writer._mongo_buffer = list(batch)
    writer._trace = probe
    flushed: list[Any] = []

    async def flush(items: list[Any]) -> None:
        flushed.extend(items)

    writer._flush_mongo_batch = flush
    await writer._do_flush()
    probe.fail_sessions.clear()
    await writer._do_flush()

    assert flushed == batch
    assert writer._mongo_buffer == []
    assert probe.release_calls == ["s1", "s2"]


@pytest.mark.asyncio
async def test_lease_error_preserves_failed_events_without_blocking_healthy_session() -> None:
    class ErrorTrace(_ParallelProbeTrace):
        async def acquire_session_trace_write(self, session_id: str) -> bool:
            if session_id == "s2":
                raise RuntimeError("lease unavailable")
            return True

    writer = dual_writer.DualEventWriter()
    probe = ErrorTrace()
    writer._trace = probe
    batch = [_buffer_item("s1"), _buffer_item("s2")]
    writer._mongo_buffer = list(batch)
    flushed: list[Any] = []

    async def flush(items: list[Any]) -> None:
        flushed.extend(items)

    writer._flush_mongo_batch = flush
    with pytest.raises(RuntimeError, match="lease unavailable"):
        await writer._do_flush()

    assert flushed == [batch[0]]
    assert writer._mongo_buffer == [batch[1]]
    assert probe.release_calls == ["s1"]

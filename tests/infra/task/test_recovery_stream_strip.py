from __future__ import annotations

"""_strip_terminal_stream_events：恢复前清理 Redis Stream 内残留的终态事件。

SSE 读循环遇到 error/done/complete 事件即断开（dual_writer.
_should_stop_stream_on_event），旧关停路径或跨版本升级可能已把终态事件写进流里；
同 run 续跑前必须删掉，重放才不会提前断流。非终态事件一律保留。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.recovery import TaskRecoveryService


class _FakeRedis:
    def __init__(self, entries: list[tuple[str, dict[str, Any]]]) -> None:
        self._entries = list(entries)
        self.deleted: list[tuple[str, str]] = []

    async def xrange(self, stream_key, min="-", max="+"):
        return list(self._entries)

    async def xdel(self, stream_key, entry_id):
        self.deleted.append((stream_key, entry_id))
        self._entries = [e for e in self._entries if e[0] != entry_id]


class _FakeDualWriter:
    def __init__(self, redis: _FakeRedis) -> None:
        self.redis = redis

    @staticmethod
    def _stream_key(session_id, run_id):
        return f"session:{session_id}:run:{run_id}:events"


def _make_service() -> TaskRecoveryService:
    return TaskRecoveryService(
        storage=SimpleNamespace(),
        run_info={},
        heartbeat=SimpleNamespace(check_exists=lambda run_id: False),
        ensure_executor=lambda: SimpleNamespace(),
        submit_task=_stub,
        mark_run_failed=_stub,
    )


async def _stub(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_strip_removes_only_terminal_events(monkeypatch):
    entries = [
        ("1-1", {"event_type": "thinking", "data": "{}"}),
        ("1-2", {"event_type": "error", "data": "{}"}),
        ("1-3", {"event_type": "done", "data": "{}"}),
        ("1-4", {"event_type": "complete", "data": "{}"}),
        ("1-5", {"event_type": "message:chunk", "data": "{}"}),
    ]
    redis = _FakeRedis(entries)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: _FakeDualWriter(redis)
    )
    service = _make_service()

    removed = await service._strip_terminal_stream_events("session-1", "run-1")

    assert removed == 3
    assert [entry_id for _, entry_id in redis.deleted] == ["1-2", "1-3", "1-4"]
    remaining_types = [fields["event_type"] for _, fields in redis._entries]
    assert remaining_types == ["thinking", "message:chunk"]


@pytest.mark.asyncio
async def test_strip_returns_zero_and_swallows_redis_errors(monkeypatch):
    class _BrokenRedis:
        async def xrange(self, *args, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(_BrokenRedis()),
    )
    service = _make_service()

    removed = await service._strip_terminal_stream_events("session-1", "run-1")

    assert removed == 0


@pytest.mark.asyncio
async def test_strip_is_noop_when_no_terminal_events(monkeypatch):
    entries = [("1-1", {"event_type": "thinking", "data": "{}"})]
    redis = _FakeRedis(entries)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: _FakeDualWriter(redis)
    )
    service = _make_service()

    removed = await service._strip_terminal_stream_events("session-1", "run-1")

    assert removed == 0
    assert redis.deleted == []
    assert recovery_module.logger is not None

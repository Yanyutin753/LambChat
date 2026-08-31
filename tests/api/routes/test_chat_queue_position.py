from __future__ import annotations

"""排队位置查询端点：排队中的 run 可随时查询自己在队列中的当前位置。

此前位置只在提交响应里返回一次，前端 toast 固定显示提交时刻的位次；
有了查询端点，前端可轮询刷新"排队中（第 N 位）"，出队时自然归零。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes.chat import get_session_queue_position
from src.kernel.errors import AppError


class _FakeSessionManager:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def get_session(self, session_id: str):
        return self._session


class _FakeLimiter:
    def __init__(self, position: int) -> None:
        self.position = position
        self.calls: list[tuple[str, str]] = []

    async def get_queue_position(self, user_id: str, run_id: str) -> int:
        self.calls.append((user_id, run_id))
        return self.position


def _user() -> SimpleNamespace:
    return SimpleNamespace(sub="user-1", user_id="user-1", permissions=[])


def _session(metadata: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(id="session-1", user_id="user-1", metadata=metadata)


async def _invoke(monkeypatch: pytest.MonkeyPatch, session: Any, limiter: _FakeLimiter):
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager", lambda: _FakeSessionManager(session)
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter", lambda: limiter
    )
    return await get_session_queue_position("session-1", user=_user())


@pytest.mark.asyncio
async def test_queued_run_returns_live_position(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session({"current_run_id": "run-1", "task_status": "queued"})
    limiter = _FakeLimiter(position=3)

    result = await _invoke(monkeypatch, session, limiter)

    assert result["position"] == 3
    assert result["run_id"] == "run-1"
    assert result["task_status"] == "queued"
    assert limiter.calls == [("user-1", "run-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("task_status", ["running", "pending", "completed", "failed", None])
async def test_non_queued_run_skips_redis_lookup(
    monkeypatch: pytest.MonkeyPatch, task_status: str | None
) -> None:
    metadata: dict[str, Any] = {"current_run_id": "run-1"}
    if task_status:
        metadata["task_status"] = task_status
    session = _session(metadata)
    limiter = _FakeLimiter(position=2)

    result = await _invoke(monkeypatch, session, limiter)

    # 只有 queued 才查 Redis；pending 属于"排队侧"状态同样查询
    if task_status in {None, "queued", "pending"}:
        assert limiter.calls == [("user-1", "run-1")]
    else:
        assert result["position"] == 0
        assert limiter.calls == []


@pytest.mark.asyncio
async def test_missing_session_raises_session_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager", lambda: _FakeSessionManager(None)
    )

    with pytest.raises(AppError) as exc_info:
        await get_session_queue_position("session-1", user=_user())

    assert exc_info.value.error_code.code == "session_not_found"


@pytest.mark.asyncio
async def test_other_users_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session({"current_run_id": "run-1", "task_status": "queued"})
    session.user_id = "user-2"
    limiter = _FakeLimiter(position=1)

    with pytest.raises(AppError):
        await _invoke(monkeypatch, session, limiter)

    assert limiter.calls == []

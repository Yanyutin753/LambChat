from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.scheduler import locks


@pytest.mark.asyncio
async def test_attachment_mutation_lock_has_distinct_key_and_owner_checked_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    class _Redis:
        async def set(self, *args, **kwargs):
            calls.append(("set", args, kwargs))
            return True

        async def eval(self, *args):
            calls.append(("eval", args))
            return 1

    monkeypatch.setattr(locks, "get_redis_client", lambda: _Redis())

    token = await locks.acquire_attachment_mutation_lock("task-1")
    assert token is not None
    await locks.release_attachment_mutation_lock("task-1", token)

    set_call = calls[0]
    assert set_call[1][0] == "scheduler:attachment_mutation:task-1"
    assert set_call[2] == {"nx": True, "ex": locks.ATTACHMENT_MUTATION_LOCK_TTL}
    eval_call = calls[1]
    assert eval_call[1][2] == "scheduler:attachment_mutation:task-1"
    assert eval_call[1][3] == token


@pytest.mark.asyncio
async def test_attachment_mutation_lock_fails_closed_when_contended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = SimpleNamespace(set=lambda *args, **kwargs: None)

    async def _set(*args, **kwargs):
        return None

    redis.set = _set
    monkeypatch.setattr(locks, "get_redis_client", lambda: redis)

    assert await locks.acquire_attachment_mutation_lock("task-1") is None


@pytest.mark.asyncio
async def test_attachment_mutation_lock_extension_is_owner_token_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    class _Redis:
        async def eval(self, *args):
            calls.append(args)
            return 1

    monkeypatch.setattr(locks, "get_redis_client", lambda: _Redis())

    extended = await locks.extend_attachment_mutation_lock(
        "task-1",
        "owner-token",
        ttl=45,
    )

    assert extended is True
    assert calls[0][2:] == (
        "scheduler:attachment_mutation:task-1",
        "owner-token",
        "45",
    )

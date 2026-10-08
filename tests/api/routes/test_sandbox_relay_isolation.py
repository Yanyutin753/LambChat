"""Synthetic relay submissions must belong to the assigned user and machine."""

from types import SimpleNamespace

import pytest

from src.api.routes import sandbox as route
from src.infra.sandbox.relay import _frames
from src.kernel.errors import AppError, ErrorCode


class Redis:
    def __init__(self, owner, machine):
        self.kv = {"sandbox:callowner:c": owner, "sandbox:callassign:c": machine}
        self.writes = []
        self.reads = []

    async def get(self, key):
        return self.kv.get(key)

    async def rpush(self, key, value):
        self.writes.append((key, value))

    async def expire(self, key, ttl):
        pass

    async def lpop(self, key):
        self.reads.append(key)
        return _frames.encode_frame(_frames.FRAME_EOF)

    async def delete(self, key):
        pass


class Request:
    headers = {}

    async def body(self):
        return b"{}"

    async def stream(self):
        yield _frames.encode_frame(_frames.FRAME_EOF)


@pytest.mark.parametrize("endpoint", ["result", "stream", "upload"])
@pytest.mark.parametrize(
    "owner,assigned,caller,machine",
    [
        ("other", "mac1", "u1", "mac1"),
        ("u1", "mac1", "u1", "mac2"),
        ("u1", "mac1", "u1", ""),
        (None, "mac1", "u1", "mac1"),
        ("u1", None, "u1", "mac1"),
    ],
)
async def test_relay_rejects_unassigned_user_or_machine(
    monkeypatch, endpoint, owner, assigned, caller, machine
):
    redis = Redis(owner, assigned)
    monkeypatch.setattr(route, "_redis", lambda: redis)
    monkeypatch.setattr(route, "_binary_redis", lambda: redis)
    kwargs = {"call_id": "c", "user": SimpleNamespace(sub=caller), "machine_id": machine}
    with pytest.raises(AppError) as exc:
        if endpoint == "result":
            await route.sandbox_result(
                request=Request(), body=route.SandboxResultRequest(stage="ack"), **kwargs
            )
        elif endpoint == "stream":
            await route.sandbox_result_stream(request=Request(), **kwargs)
        else:
            await route.sandbox_upload_stream(**kwargs)
    assert exc.value.error_code == ErrorCode.SANDBOX_RESULT_MISMATCH
    assert not redis.writes and not redis.reads


@pytest.mark.parametrize("endpoint", ["result", "stream", "upload"])
@pytest.mark.parametrize("assigned,machine", [("mac1", "mac1"), ("legacy", "")])
async def test_relay_accepts_exact_assignment_or_explicit_legacy(
    monkeypatch, endpoint, assigned, machine
):
    redis = Redis("u1", assigned)
    monkeypatch.setattr(route, "_redis", lambda: redis)
    monkeypatch.setattr(route, "_binary_redis", lambda: redis)
    kwargs = {"call_id": "c", "user": SimpleNamespace(sub="u1"), "machine_id": machine}
    if endpoint == "result":
        assert await route.sandbox_result(
            request=Request(), body=route.SandboxResultRequest(stage="ack"), **kwargs
        ) == {"status": "ok"}
    elif endpoint == "stream":
        assert await route.sandbox_result_stream(request=Request(), **kwargs) == {"status": "ok"}
    else:
        response = await route.sandbox_upload_stream(**kwargs)
        assert [frame async for frame in response.body_iterator] == [
            _frames.encode_frame(_frames.FRAME_EOF)
        ]

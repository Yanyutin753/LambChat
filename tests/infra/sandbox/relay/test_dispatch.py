"""dispatch 测试：正常往返、离线快速失败、ack 超时。"""

import asyncio
import json
import time

import pytest

from src.infra.sandbox.relay import dispatch as dispatch_module
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.errors import AppError, ErrorCode


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def lpop(self, key: str) -> str | None:
        items = self.lists.get(key)
        return items.pop(0) if items else None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def delete(self, key: str) -> None:
        self.kv.pop(key, None)


class _FakeRegistry:
    def __init__(self, online: bool):
        self.online = online

    async def is_online(self, user_id: str) -> bool:
        return self.online


@pytest.fixture
def fake(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(dispatch_module, "_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(True))
    return redis


async def test_roundtrip_ack_then_done(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        assert req["timeout"] == 5  # 帧契约（spec §3.2）：daemon 按 timeout 掐表
        # 帧契约（陈旧丢弃）：req 带入队时间戳，供 channel_frames 判定陈旧
        assert isinstance(req["ts"], (int, float))
        assert 0 <= time.time() - req["ts"] < 5
        await fake.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        await asyncio.sleep(0.02)
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok", "stdout": "hi"}),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo hi"})
    await task
    assert result["stdout"] == "hi"


async def test_offline_fails_fast(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(False))
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    assert exc.value.error_code == ErrorCode.DAEMON_OFFLINE
    assert not fake.lists  # rpush 之前快速失败，不产生孤儿请求


async def test_ack_timeout_raises(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT


async def test_exec_timeout_raises_after_ack(fake, monkeypatch):
    """ack 已收到但 done 始终不来：命中总超时 deadline（seconds 取 exec 超时）。"""
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 0.05)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )

    task = asyncio.create_task(daemon())
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    await task
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT
    assert exc.value.args_data == {"seconds": 0}  # int(0.05)，区别于 ack 超时路径

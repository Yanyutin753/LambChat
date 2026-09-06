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

    async def resolve_target(self, user_id: str, machine_id: str | None = None):
        return "legacy" if self.online else None

    def queue_key(self, user_id: str, machine_id: str) -> str:
        # legacy 路由：旧断言的队列键（无机器后缀）
        return f"sandbox:req:{user_id}"


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


async def test_exec_done_error_status_returns_command_outcome(fake, monkeypatch):
    """exec 的非零退出码是命令结局而非中继故障：done 载荷带 executor 结果字段
    （stdout/stderr/exit_code）时原样回传，由 aexecute 构造 ExecuteResponse 让
    模型看到真实输出（Windows cmd.exe 上命令失败是常态，不能全部变成不透明
    AppError——生产实测模型连续 6 条命令只见 "execution failed"，无从纠错）。"""
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps(
                {
                    "user_id": "u1",
                    "stage": "ack",
                }
            ),
        )
        await asyncio.sleep(0.02)
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps(
                {
                    "user_id": "u1",
                    "stage": "done",
                    "status": "error",
                    "stdout": "",
                    "stderr": "'free' is not recognized as an internal or external command",
                    "exit_code": 1,
                    "error": None,
                }
            ),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "free -h"})
    await task
    assert result["exit_code"] == 1
    assert "not recognized" in result["stderr"]


async def test_fs_op_done_error_status_still_raises(fake, monkeypatch):
    """fs_* op 的 status=error 是 daemon 内部异常（ExecutorError 等）：仍按
    SANDBOX_EXEC_FAILED 上抛；detail 取 error 字段（None 不落成字面 "None"）。"""
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps(
                {"user_id": "u1", "stage": "done", "status": "error", "error": "illegal cwd"}
            ),
        )

    task = asyncio.create_task(daemon())
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "fs_read", {"path": "a.txt"})
    await task
    assert exc.value.error_code == ErrorCode.SANDBOX_EXEC_FAILED
    assert exc.value.args_data == {"detail": "illegal cwd"}


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


# ---------------------------------------------------------------------------
# 多机：machine_id 路由与离线语义
# ---------------------------------------------------------------------------


class _MachinesFakeRegistry:
    """resolve_target/queue_key 可控行为：online_machine 控制 resolve 结果。"""

    def __init__(self, resolved: str | None):
        self.resolved = resolved

    async def is_online(self, user_id: str) -> bool:
        return self.resolved is not None

    async def resolve_target(self, user_id: str, machine_id: str | None = None):
        return self.resolved

    def queue_key(self, user_id: str, machine_id: str) -> str:
        return f"sandbox:req:{user_id}:{machine_id}"


async def test_dispatch_routes_to_selected_machine_queue(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(dispatch_module, "_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _MachinesFakeRegistry("mac1"))
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)

    async def fake_get(key):
        return json.dumps({"user_id": "u1", "stage": "done", "status": "ok"})

    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 1)
    import contextlib

    with contextlib.suppress(Exception):
        # 只验证入队键：done 立即返回，不等待超时
        async def fast_get(key):
            return json.dumps({"user_id": "u1", "stage": "done", "status": "ok"})

        redis.get = fast_get  # type: ignore[method-assign]
        await dispatch_local_call("u1", "exec", {"command": "ls"}, machine_id="mac1")
    assert list(redis.lists) == ["sandbox:req:u1:mac1"]


async def test_dispatch_selected_machine_offline_raises_machine_error(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(dispatch_module, "_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _MachinesFakeRegistry(None))
    with pytest.raises(AppError) as exc_info:
        await dispatch_local_call("u1", "exec", {"command": "ls"}, machine_id="mac1")
    assert exc_info.value.error_code == ErrorCode.SANDBOX_MACHINE_OFFLINE


# ---------- dispatch_local_stream：流式 op 的请求下发与逐行消费 ----------


async def _collect_stream(agen):
    chunks = []
    async for chunk in agen:
        chunks.append(chunk)
    return chunks


async def test_stream_roundtrip_yields_decoded_chunks(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 5)

    from src.infra.sandbox.relay._frames import (
        FRAME_DATA,
        FRAME_EOF,
        encode_frame,
    )

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        assert req["op"] == "fs_download_stream"
        assert req["timeout"] == 5
        stream_key = f"sandbox:stream:u1:{req['call_id']}"
        await fake.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        await fake.rpush(stream_key, encode_frame(FRAME_DATA, b"ab"))
        await fake.rpush(stream_key, encode_frame(FRAME_DATA, b"cd"))
        await fake.rpush(stream_key, encode_frame(FRAME_EOF))

    task = asyncio.create_task(daemon())
    chunks = await _collect_stream(
        dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "f"}
        )
    )
    await task
    assert chunks == [b"ab", b"cd"]
    assert not fake.kv  # resp/stream 键消费完即清


async def test_stream_error_line_raises_with_detail(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 5)

    async def daemon():
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        from src.infra.sandbox.relay._frames import FRAME_ERROR, encode_frame

        await fake.rpush(
            f"sandbox:stream:u1:{req['call_id']}",
            encode_frame(FRAME_ERROR, json.dumps({"error": "file_not_found"}).encode()),
        )

    task = asyncio.create_task(daemon())
    with pytest.raises(AppError) as exc:
        async for _ in dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "missing"}
        ):
            pass
    await task
    assert exc.value.error_code == ErrorCode.SANDBOX_EXEC_FAILED
    assert "file_not_found" in str(exc.value.args_data.get("detail"))


async def test_stream_old_daemon_unsupported_op_raises_with_detail(fake, monkeypatch):
    """老 daemon 不认识流式 op：走普通 results 端点回 done(error)——detail 带
    "unsupported op"，backend 据此粘滞降级到分块通道。"""
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 5)

    async def daemon():
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps(
                {
                    "user_id": "u1",
                    "stage": "done",
                    "status": "error",
                    "error": "unsupported op: fs_download_stream",
                }
            ),
        )

    task = asyncio.create_task(daemon())
    with pytest.raises(AppError) as exc:
        async for _ in dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "f"}
        ):
            pass
    await task
    assert "unsupported op" in str(exc.value.args_data.get("detail"))


async def test_stream_ack_timeout_raises(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 5)

    with pytest.raises(AppError) as exc:
        async for _ in dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "f"}
        ):
            pass
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT

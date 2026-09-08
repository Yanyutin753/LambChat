"""dispatch 测试：正常往返、离线快速失败、ack 超时。"""

import asyncio
import json
import time

import pytest
from redis.exceptions import ResponseError

from src.infra.sandbox.relay import dispatch as dispatch_module
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.errors import AppError, ErrorCode


class _FakeRedis:
    """string/list 双库 fake。LPOP/BLPOP 命中 string key 时按真 Redis 语义
    抛 WRONGTYPE ResponseError（而非静默返回 None）——dispatch 的旧格式
    GET 兜底必须真实捕获该错误才能通过。"""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    def _wrongtype(self, key: str):
        if key in self.kv:
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def lpop(self, key: str) -> str | None:
        self._wrongtype(key)
        items = self.lists.get(key)
        return items.pop(0) if items else None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key) or ())

    async def expire(self, key: str, seconds: int) -> None:
        pass  # TTL 语义本用例不测

    async def delete(self, key: str) -> None:
        self.kv.pop(key, None)
        self.lists.pop(key, None)

    async def blpop(self, key: str, timeout: float = 0):
        self._wrongtype(key)
        items = self.lists.get(key)
        if items:
            return key, items.pop(0)
        if timeout and timeout > 0:
            await asyncio.sleep(timeout)
        return None

    async def lrem(self, key: str, count: int, value: str) -> None:
        items = self.lists.get(key)
        if items:
            self.lists[key] = [x for x in items if x != value]


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
    # 流式函数走二进制客户端（帧通道）：同一 fake 实例，行为与既有断言一致
    monkeypatch.setattr(dispatch_module, "_binary_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(True))
    return redis


async def test_roundtrip_ack_then_done(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
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
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
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
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
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
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT


async def test_exec_timeout_raises_after_ack(fake, monkeypatch):
    """ack 已收到但 done 始终不来：命中总超时 deadline（seconds 取 exec 超时）。"""
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
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
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)

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


async def test_old_format_set_resp_falls_back_to_get(fake, monkeypatch):
    """滚动发布窗口：旧实例仍以 SET（string）写 resp key——真 Redis 对
    string key 执行 BLPOP/LPOP 抛 WRONGTYPE 而非返回 None，dispatch 必须
    捕获并回落 GET，不能把兼容路径变成未处理异常。"""
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok", "stdout": "old"}),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo old"})
    await task
    assert result["stdout"] == "old"


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


# ----------
# 帧通道 × decode_responses=True 客户端（2026-09-07 生产事故）
# ----------


class _RedisByteStore:
    """Redis 服务端视角的存储：值一律 bytes（真实 Redis 不区分写入方客户端）。"""

    def __init__(self):
        self.lists: dict[str, list[bytes]] = {}
        self.kv: dict[str, bytes] = {}


class _DecodingRedisView:
    """复刻生产共享客户端（storage.redis 的 decode_responses=True）：读取按
    UTF-8 解码——非 UTF-8 字节在 lpop/get 时即抛 UnicodeDecodeError。"""

    def __init__(self, store: _RedisByteStore):
        self._store = store

    async def rpush(self, key, value):
        self._store.lists.setdefault(key, []).append(
            value.encode("utf-8") if isinstance(value, str) else value
        )

    async def lpop(self, key):
        items = self._store.lists.get(key)
        raw = items.pop(0) if items else None
        return None if raw is None else raw.decode("utf-8")

    async def set(self, key, value, ex=None):
        self._store.kv[key] = value.encode("utf-8") if isinstance(value, str) else value

    async def get(self, key):
        raw = self._store.kv.get(key)
        return None if raw is None else raw.decode("utf-8")

    async def delete(self, key):
        self._store.lists.pop(key, None)
        self._store.kv.pop(key, None)


class _BinaryRedisView(_DecodingRedisView):
    """decode_responses=False 客户端：lpop/get 直通 bytes，不做解码。"""

    async def lpop(self, key):
        items = self._store.lists.get(key)
        return items.pop(0) if items else None

    async def get(self, key):
        return self._store.kv.get(key)


async def test_stream_binary_frames_need_binary_client(monkeypatch):
    """2026-09-07 生产事故回归：fs_download_stream 的裸二进制帧在
    decode_responses=True 客户端上 lpop 即抛 UnicodeDecodeError（生产报错
    "utf-8 codec can't decode byte 0xc6 in position 3"——837128 字节 PNG 帧
    头 02 00 0C C6 08 的 position 3 正是 0xC6），reveal_file 全线误报
    file_not_found_or_empty。帧通道读取必须走二进制安全客户端。"""
    from src.infra.sandbox.relay._frames import FRAME_DATA, FRAME_EOF, encode_frame

    store = _RedisByteStore()
    decoding = _DecodingRedisView(store)
    monkeypatch.setattr(dispatch_module, "_redis", lambda: decoding)
    monkeypatch.setattr(dispatch_module, "_binary_redis", lambda: _BinaryRedisView(store))
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(True))
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 5)

    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4  # 必含非法 UTF-8 字节

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await decoding.lpop("sandbox:req:u1"))
        assert req["op"] == "fs_download_stream"
        stream_key = f"sandbox:stream:u1:{req['call_id']}"
        await decoding.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        # daemon 上行帧按 bytes 入库（与 sandbox_result_stream 端点的 rpush 一致）
        await decoding.rpush(stream_key, encode_frame(FRAME_DATA, png))
        await decoding.rpush(stream_key, encode_frame(FRAME_EOF))

    task = asyncio.create_task(daemon())
    chunks = await _collect_stream(
        dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "f"}
        )
    )
    await task
    assert chunks == [png]
    assert not store.kv  # resp 键消费完即清


async def test_stream_ack_and_error_done_back_to_back(fake, monkeypatch):
    """ack 与 error done 背靠背入队（daemon 秒败/网络延迟聚合的形态）：
    消费 ack 后不得清空 resp 队列——旧 SET 语义的 delete 残留会把已入队的
    done 连带删掉，错误结局退化成等满 exec 超时。"""
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 2)

    async def daemon():
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        resp_key = f"sandbox:resp:{req['call_id']}"
        await fake.rpush(resp_key, json.dumps({"user_id": "u1", "stage": "ack"}))
        await fake.rpush(
            resp_key,
            json.dumps({"user_id": "u1", "stage": "done", "status": "error", "error": "boom"}),
        )

    task = asyncio.create_task(daemon())
    with pytest.raises(AppError) as exc:
        async for _ in dispatch_module.dispatch_local_stream(
            "u1", "fs_download_stream", {"cwd": "/w", "path": "f"}
        ):
            pass
    await task
    assert exc.value.error_code == ErrorCode.SANDBOX_EXEC_FAILED
    assert "boom" in str(exc.value.args_data.get("detail"))


async def test_upload_stream_window_wait_aborts_on_interrupt_sentinel(fake, monkeypatch):
    """上传窗口等待期收到中断哨兵（daemon 断开时 /upload 端点推入的 error
    done）必须快速失败——否则 daemon 死后窗口永不腾空，生产者干等满
    SANDBOX_LOCAL_STREAM_TIMEOUT（600s，E2E 上传中断档实测）。"""
    monkeypatch.setattr(dispatch_module, "_STREAM_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module, "_UPBLOB_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 30)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_STREAM_TIMEOUT", 600)

    # 生产者还没推满窗口时，哨兵先行到达（模拟 daemon 秒断：端点 finally 推
    # error done 进 resp，upblob 无人消费）
    async def daemon():
        await asyncio.sleep(0.05)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        assert req["op"] == "fs_upload_stream"
        await fake.rpush(
            f"sandbox:resp:{req['call_id']}",
            json.dumps(
                {"user_id": "u1", "stage": "done", "status": "error", "error": "stream_interrupted"}
            ),
        )

    task = asyncio.create_task(daemon())
    import time as time_mod

    t0 = time_mod.monotonic()
    with pytest.raises(AppError) as exc:
        # 4MiB×(窗口+2) 帧：推满窗口后进入等待，哨兵应令其快速失败
        content = b"x" * (
            dispatch_module._UPBLOB_CHUNK_BYTES * (dispatch_module._UPBLOB_WINDOW + 2)
        )
        await dispatch_module.dispatch_local_stream_upload(
            "u1", {"cwd": "/workspace/s1", "path": "big.bin", "max_bytes": 10**9}, content
        )
    dt = time_mod.monotonic() - t0
    await task
    assert exc.value.error_code == ErrorCode.SANDBOX_EXEC_FAILED
    assert "stream_interrupted" in str(exc.value.args_data.get("detail"))
    assert dt < 5, f"窗口等待未消费中断哨兵，耗时 {dt:.1f}s"


# ----------
# ACK 死线内幂等重推：断联窗口内 tool_call 帧不丢
# （2026-09-09 生产断联：帧被死连接的 BLPOP 消费即丢失，daemon 重连后无人
#  再投递，agent 侧干等 30s ACK 超时全灭 SANDBOX_TIMEOUT）
# ----------


async def test_unacked_call_is_repushed_until_ack(fake, monkeypatch):
    """帧被断联通道吞掉（首次入队无人 ack）时，dispatch 周期性重推同一
    call_id 的幂等帧：daemon 重连后收到重推帧照常执行，调用整体不失败。"""
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(dispatch_module, "_ACK_REPUSH_INTERVAL", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    received: list[dict] = []

    async def daemon():
        # 首帧被「死连接」消费（lpop 后静默）——模拟 channel 断联丢帧
        await asyncio.sleep(0.02)
        first = json.loads(await fake.lpop("sandbox:req:u1"))
        received.append(first)
        # 0.3s 后 daemon 重连，收到重推帧：ack + done
        await asyncio.sleep(0.3)
        retry = json.loads(await fake.lpop("sandbox:req:u1"))
        received.append(retry)
        assert retry["call_id"] == first["call_id"]  # 幂等重推：同一调用
        assert retry["ts"] >= first["ts"]  # ts 刷新：不被 channel 陈旧丢弃门吃掉
        await fake.set(
            f"sandbox:resp:{retry['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        await asyncio.sleep(0.02)
        await fake.set(
            f"sandbox:resp:{retry['call_id']}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok", "stdout": "hi"}),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo hi"})
    await task
    assert result["stdout"] == "hi"
    assert len(received) == 2


async def test_acked_call_is_not_repushed(fake, monkeypatch):
    """ack 到达后停止重推：正常往返只有一次入队（重推只针对未确认的丢失帧）。"""
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(dispatch_module, "_ACK_REPUSH_INTERVAL", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    queue_pushes: list[str] = []
    original_rpush = fake.rpush

    async def counting_rpush(key: str, value: str) -> None:
        if key == "sandbox:req:u1":
            queue_pushes.append(value)
        await original_rpush(key, value)

    fake.rpush = counting_rpush  # type: ignore[method-assign]

    async def daemon():
        await asyncio.sleep(0.02)  # 在首个重推点（0.05s）之前就 ack
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(
            f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"})
        )
        await asyncio.sleep(0.15)  # done 晚于多个重推点到点：验证 ack 后不再推
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok", "stdout": "hi"}),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo hi"})
    await task
    assert result["stdout"] == "hi"
    assert len(queue_pushes) == 1  # ack 一到重推即停，全程只入队一次


async def test_ack_timeout_cleans_repush_residue(fake, monkeypatch):
    """daemon 始终无响应时：重推按既有 ACK 死线失败，且 finally 清掉队列里
    的全部重推残留——不给重连后的 daemon 留「无人等待的幽灵执行」。"""
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(dispatch_module, "_ACK_REPUSH_INTERVAL", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 0.2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {"command": "echo hi"})
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT
    # 队列残留被 lrem 清空：断联期间积累的重推帧不外泄
    assert fake.lists.get("sandbox:req:u1") in (None, [])

"""工具调用下发与结果等待：Redis list 请求 + key 轮询结果（spec §3.2，lpop 轮询替代 BLPOP）。"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from src.infra.sandbox.relay import _frames as _frames_codec
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

_POLL_INTERVAL = 0.05
# 流式结果逐行消费的轮询：行粒度小、吞吐优先，比控制面轮询更密
_STREAM_POLL_INTERVAL = 0.01


def _redis():
    return get_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


async def dispatch_local_call(
    user_id: str,
    op: str,
    payload: dict,
    *,
    timeout: float | None = None,
    machine_id: str | None = None,
) -> dict:
    """下发工具调用到目标机。

    ``machine_id``：会话级选机（None = 注册表默认解析：默认机 → 唯一在线机
    → legacy）。显式指定且该机离线时报 SANDBOX_MACHINE_OFFLINE（区别于无任何
    机器在线的 DAEMON_OFFLINE，前端据此提示换机）。
    """
    registry = _registry()
    if machine_id:
        target = await registry.resolve_target(user_id, machine_id)
        if target is None:
            raise AppError(ErrorCode.SANDBOX_MACHINE_OFFLINE, args={"machine": machine_id})
    else:
        target = await registry.resolve_target(user_id)
        if target is None:
            raise AppError(ErrorCode.DAEMON_OFFLINE)
    exec_timeout = timeout if timeout is not None else float(settings.SANDBOX_LOCAL_EXEC_TIMEOUT)
    call_id = uuid.uuid4().hex
    req = {
        "call_id": call_id,
        "user_id": user_id,
        "op": op,
        "payload": payload,
        "timeout": exec_timeout,
        "ts": time.time(),  # 入队时间戳：channel_frames 据此丢弃 daemon 重连后的积压陈旧请求
    }
    redis = _redis()
    resp_key = f"sandbox:resp:{call_id}"
    await redis.rpush(registry.queue_key(user_id, target), json.dumps(req))

    start = time.monotonic()
    acked = False
    ack_deadline = start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
    exec_deadline = start + exec_timeout
    try:
        while time.monotonic() < exec_deadline:
            raw = await redis.get(resp_key)
            resp = None
            if raw is not None:
                resp = json.loads(raw)
                if resp.get("user_id") != user_id:
                    resp = None  # 他人结果，忽略
            if resp is not None and resp.get("stage") == "ack":
                acked = True
                resp = None
            if resp is not None and resp.get("stage") == "done":
                await redis.delete(resp_key)
                if resp.get("status") != "ok":
                    # exec 的非零退出码/命令超时是**命令结局**而非中继故障（daemon
                    # executor 的 status 镜像 exit_code）：带 executor 结果字段的
                    # done 载荷原样回传，由 LocalSandboxBackend.aexecute 构造
                    # ExecuteResponse——模型看得到 stdout/stderr/exit_code 才能自行
                    # 纠错（Windows cmd.exe 上命令失败是常态；劫持成 AppError 会让
                    # 模型只见 "execution failed" 而无从换命令）。其余 op（fs_* 的
                    # 内部异常）与 exec 的 daemon 级错误（expired/unsupported，无
                    # 结果字段）仍按中继失败上抛。
                    if op == "exec" and ("exit_code" in resp or "stdout" in resp):
                        return resp
                    raise AppError(
                        ErrorCode.SANDBOX_EXEC_FAILED,
                        args={"detail": str(resp.get("error") or "local execution failed")},
                    )
                return resp
            if not acked and time.monotonic() > ack_deadline:
                raise AppError(
                    ErrorCode.SANDBOX_TIMEOUT, args={"seconds": settings.SANDBOX_LOCAL_ACK_TIMEOUT}
                )
            await asyncio.sleep(_POLL_INTERVAL)
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
    finally:
        try:
            await redis.delete(resp_key)
        except Exception:  # noqa: BLE001 - 清理尽力而为
            pass


def _stream_key(user_id: str, call_id: str) -> str:
    return f"sandbox:stream:{user_id}:{call_id}"


async def dispatch_local_stream(
    user_id: str,
    op: str,
    payload: dict,
    *,
    timeout: float | None = None,
    machine_id: str | None = None,
) -> AsyncIterator[bytes]:
    """流式版下发：请求入队同 :func:`dispatch_local_call`，结果按 NDJSON 行逐块产出。

    daemon 把整个文件装进一个 chunked POST（``/api/sandbox/results/stream/…``），
    行由该端点 rpush 进 stream list，这里 lpop 逐行消费并 yield 解码后的字节。
    每块一对 HTTP 往返的分块通道在大文件上是「块数×往返时延」的线性成本，
    流式把往返摊销成每个文件常数次。

    错误语义（对齐 dispatch_local_call 的 fs op 分支）：

    - 行 ``{"error": ...}`` / resp ``done(status=error)``（老 daemon 不认识
      流式 op 回 ``unsupported op``）→ ``AppError(SANDBOX_EXEC_FAILED)``，
      ``detail`` 携带原始错误串——上层按 ``unsupported op`` 子串判别降级；
    - ack 超时/总超时 → ``AppError(SANDBOX_TIMEOUT)``。
    """
    registry = _registry()
    if machine_id:
        target = await registry.resolve_target(user_id, machine_id)
        if target is None:
            raise AppError(ErrorCode.SANDBOX_MACHINE_OFFLINE, args={"machine": machine_id})
    else:
        target = await registry.resolve_target(user_id)
        if target is None:
            raise AppError(ErrorCode.DAEMON_OFFLINE)
    exec_timeout = timeout if timeout is not None else float(settings.SANDBOX_LOCAL_STREAM_TIMEOUT)
    call_id = uuid.uuid4().hex
    req = {
        "call_id": call_id,
        "user_id": user_id,
        "op": op,
        "payload": payload,
        "timeout": exec_timeout,
        "ts": time.time(),
    }
    redis = _redis()
    stream_key = _stream_key(user_id, call_id)
    resp_key = f"sandbox:resp:{call_id}"
    await redis.rpush(registry.queue_key(user_id, target), json.dumps(req))

    start = time.monotonic()
    acked = False
    ack_deadline = start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
    exec_deadline = start + exec_timeout
    try:
        while time.monotonic() < exec_deadline:
            resp = None
            raw = await redis.get(resp_key)
            if raw is not None:
                resp = json.loads(raw)
                if resp.get("user_id") != user_id:
                    resp = None
            if resp is not None:
                if resp.get("stage") == "ack":
                    acked = True
                    await redis.delete(resp_key)
                    resp = None
                elif resp.get("stage") == "done":
                    await redis.delete(resp_key)
                    error = str(resp.get("error") or "local execution failed")
                    raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": error})
            while True:
                raw_item = await redis.lpop(stream_key)
                if raw_item is None:
                    break
                item: bytes
                if isinstance(raw_item, str):
                    item = raw_item.encode("utf-8")
                else:
                    assert isinstance(raw_item, bytes)  # redis list item 契约
                    item = raw_item
                parsed = _frames_codec.try_parse_frame(item)
                if parsed is None:
                    continue  # 残缺 item（不该发生）：跳过不炸消费器
                ftype, frame_body, _rest = parsed
                acked = True  # 首帧即存活证明
                if ftype == _frames_codec.FRAME_ERROR:
                    error = str(json.loads(frame_body).get("error") or "stream failed")
                    raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": error})
                if ftype == _frames_codec.FRAME_EOF:
                    return
                if ftype == _frames_codec.FRAME_DATA:
                    yield frame_body  # 裸字节：无 base64 解码开销
                # FRAME_META：跳过（尺寸供上层核对，不在数据流里重复）
            if not acked and time.monotonic() > ack_deadline:
                raise AppError(
                    ErrorCode.SANDBOX_TIMEOUT, args={"seconds": settings.SANDBOX_LOCAL_ACK_TIMEOUT}
                )
            await asyncio.sleep(_STREAM_POLL_INTERVAL)
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
    finally:
        for key in (resp_key, stream_key):
            try:
                await redis.delete(key)
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass


_UPBLOB_WINDOW = 8  # 生产者在途帧数上限：×4MiB 帧 = Redis 峰值 ~32MiB
_UPBLOB_CHUNK_BYTES = 4 * 1024 * 1024  # 与 daemon 侧 FS_STREAM_FRAME_BYTES 同则
_UPBLOB_POLL_INTERVAL = 0.005


def _upblob_key(user_id: str, call_id: str) -> str:
    return f"sandbox:upblob:{user_id}:{call_id}"


async def dispatch_local_stream_upload(
    user_id: str,
    payload: dict,
    content: bytes,
    *,
    machine_id: str | None = None,
) -> None:
    """流式上传（服务端 → daemon）：请求入队后生产者把整文件按帧写入 Redis
    list（有界窗口），daemon 单个 GET 拉流落盘，done 回普通 results 端点。

    与下载方向的 dispatch_local_stream 对称：每文件常数次 HTTP 往返。窗口
    上限把 Redis 峰值内存钉在 ~32MiB，与文件大小无关。错误语义同分块通道：
    ``unsupported op``（老 daemon）与文件级错误都在 ``detail`` 里，上层据此
    降级/透出。
    """
    registry = _registry()
    if machine_id:
        target = await registry.resolve_target(user_id, machine_id)
        if target is None:
            raise AppError(ErrorCode.SANDBOX_MACHINE_OFFLINE, args={"machine": machine_id})
    else:
        target = await registry.resolve_target(user_id)
        if target is None:
            raise AppError(ErrorCode.DAEMON_OFFLINE)
    exec_timeout = float(settings.SANDBOX_LOCAL_STREAM_TIMEOUT)
    call_id = uuid.uuid4().hex
    req = {
        "call_id": call_id,
        "user_id": user_id,
        "op": "fs_upload_stream",
        "payload": payload,
        "timeout": exec_timeout,
        "ts": time.time(),
    }
    redis = _redis()
    blob_key = _upblob_key(user_id, call_id)
    resp_key = f"sandbox:resp:{call_id}"
    await redis.rpush(registry.queue_key(user_id, target), json.dumps(req))

    def _build_frames() -> list[bytes]:
        out = [
            _frames_codec.encode_frame(
                _frames_codec.FRAME_META, json.dumps({"size": len(content)}).encode()
            )
        ]
        for offset in range(0, len(content), _UPBLOB_CHUNK_BYTES):
            out.append(
                _frames_codec.encode_frame(
                    _frames_codec.FRAME_DATA, content[offset : offset + _UPBLOB_CHUNK_BYTES]
                )
            )
        out.append(_frames_codec.encode_frame(_frames_codec.FRAME_EOF))
        return out

    start = time.monotonic()
    acked = False
    done: dict | None = None
    try:
        deadline = start + exec_timeout
        for frame in _build_frames():
            while time.monotonic() < deadline:
                if await redis.llen(blob_key) < _UPBLOB_WINDOW:
                    break
                await asyncio.sleep(_UPBLOB_POLL_INTERVAL)
            else:
                raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
            await redis.rpush(blob_key, frame)
            await redis.expire(blob_key, 120)
        while time.monotonic() < deadline and done is None:
            raw = await redis.get(resp_key)
            resp = json.loads(raw) if raw is not None else None
            if resp is not None and resp.get("user_id") == user_id:
                if resp.get("stage") == "ack":
                    acked = True
                    await redis.delete(resp_key)
                elif resp.get("stage") == "done":
                    done = resp
                    await redis.delete(resp_key)
            if (
                done is None
                and not acked
                and time.monotonic() > start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
            ):
                raise AppError(
                    ErrorCode.SANDBOX_TIMEOUT, args={"seconds": settings.SANDBOX_LOCAL_ACK_TIMEOUT}
                )
            if done is None:
                await asyncio.sleep(_STREAM_POLL_INTERVAL)
        if done is None:
            raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
        if done.get("status") != "ok":
            raise AppError(
                ErrorCode.SANDBOX_EXEC_FAILED,
                args={"detail": str(done.get("error") or "local execution failed")},
            )
    finally:
        for key in (resp_key, blob_key):
            try:
                await redis.delete(key)
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass

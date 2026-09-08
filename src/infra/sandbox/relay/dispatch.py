"""工具调用下发与结果等待：Redis list 请求 + 结果队列阻塞读（BLPOP，GET 兜底旧格式）。"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from redis.exceptions import ResponseError

from src.infra.sandbox.relay import _frames as _frames_codec
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_binary_redis_client, get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

# 流式结果逐行消费的轮询：行粒度小、吞吐优先，比控制面轮询更密
_STREAM_POLL_INTERVAL = 0.01

#: 结果等待的阻塞读切片（秒）：BLPOP 主通道——滚动发布窗口内旧实例仍以
#: SET（string）写 resp key，此时 BLPOP/LPOP 抛 WRONGTYPE（真 Redis 语义，
#: 并非返回 None），由 :func:`_pop_resp` 捕获后回落 GET 读旧格式。
_BLPOP_TIMEOUT = 1.0

#: 调用-机器绑定键：dispatch 入队前写目标机，results 端点校验回传者。
_ASSIGN_PREFIX = "sandbox:callassign"


def _assign_key(call_id: str) -> str:
    return f"{_ASSIGN_PREFIX}:{call_id}"


def _redis():
    return get_redis_client()


def _binary_redis():
    """帧通道专用二进制客户端：stream/upblob list 里是裸二进制帧，共享客户端
    （decode_responses=True）读取即抛 UnicodeDecodeError（2026-09-07 生产事故）。"""
    return get_binary_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


#: 旧格式（SET string）回传的轮询节拍：WRONGTYPE 兜底分支专用——老格式 key
#: 上 BLPOP 即抛即返，不加节拍会退化成对 Redis 的高频空转（比改造前的
#: 50ms 轮询更糟）；对测试 fake 而言这也是让出事件循环的点。
_LEGACY_POLL_INTERVAL = 0.05

#: ACK 未确认时的幂等重推间隔（秒）。tool_call 帧被 channel 的 BLPOP 消费后
#: 即脱离队列——连接在投递瞬间断掉（滚动发布/代理抖动）帧就丢了，daemon
#: 重连后无人再投递，调用方干等满 ACK 死线（2026-09-09 生产断联窗口内 exec
#: 全灭 SANDBOX_TIMEOUT）。重推同一 call_id（daemon 侧按 call_id 去重），
#: ACK 到达即停。
_ACK_REPUSH_INTERVAL = 5.0


class _AckRepusher:
    """下发帧的幂等重推器：ack 之前周期性重推同一请求，结束时清掉队列残留。

    ts 每次重推刷新——channel 侧按 ts 判龄丢弃陈旧帧，沿用原始时间戳会让
    重推帧在 ACK 死线附近被自己的陈旧门吃掉。cleanup 用 LREM 精确移除本
    调用推过的每一帧：调用失败（或完成）后队列里不留副本，daemon 重连后
    不会执行「已无人等待的幽灵调用」。
    """

    def __init__(self, redis, queue: str, req: dict) -> None:
        self._redis = redis
        self._queue = queue
        self._req = req
        self._pushed: list[str] = []

    async def push(self) -> None:
        self._req["ts"] = time.time()
        payload = json.dumps(self._req)
        self._pushed.append(payload)
        await self._redis.rpush(self._queue, payload)

    def next_due(self) -> float:
        return time.monotonic() + _ACK_REPUSH_INTERVAL

    async def cleanup(self) -> None:
        for payload in self._pushed:
            try:
                await self._redis.lrem(self._queue, 0, payload)
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass


async def _pop_resp(redis, key: str, *, timeout: float | None = None):
    """读一条回传结果：新格式 RPUSH 队列优先（timeout 给出则 BLPOP 阻塞）。

    兼容旧格式：resp key 被滚动窗口内的旧实例 SET 成 string 时，真 Redis 对
    LPOP/BLPOP 抛 WRONGTYPE 而非返回 None——捕获后按旧节拍轮询 GET。GET 只
    在这一分支执行：key 为 list 时 GET 同样抛 WRONGTYPE，不能作常规兜底。
    """
    try:
        if timeout is None:
            return await redis.lpop(key)
        item = await redis.blpop(key, timeout=timeout)
        return item[1] if item is not None else None
    except ResponseError as exc:
        if "WRONGTYPE" not in str(exc):
            raise
        raw = await redis.get(key)
        await asyncio.sleep(_LEGACY_POLL_INTERVAL)
        return raw


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
    # 调用-机器绑定：results 端点据此拒绝同用户其他机器冒答（call_id 难猜，
    # 但绑定后模型上无冒答空间）；无绑定键的旧调用（兼容窗口）跳过校验
    await redis.set(_assign_key(call_id), target, ex=120)
    repusher = _AckRepusher(redis, registry.queue_key(user_id, target), req)
    await repusher.push()

    start = time.monotonic()
    acked = False
    ack_deadline = start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
    exec_deadline = start + exec_timeout
    next_repush = repusher.next_due()
    try:
        while time.monotonic() < exec_deadline:
            if not acked and time.monotonic() >= next_repush:
                await repusher.push()
                next_repush = repusher.next_due()
            remaining = exec_deadline - time.monotonic()
            raw = await _pop_resp(
                redis, resp_key, timeout=min(_BLPOP_TIMEOUT, max(remaining, 0.01))
            )
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
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
    finally:
        try:
            await redis.delete(resp_key)
            await redis.delete(_assign_key(call_id))
        except Exception:  # noqa: BLE001 - 清理尽力而为
            pass
        await repusher.cleanup()


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
    redis = _binary_redis()  # stream list 是裸二进制帧（req/resp 均为 JSON，bytes 兼容）
    stream_key = _stream_key(user_id, call_id)
    resp_key = f"sandbox:resp:{call_id}"
    repusher = _AckRepusher(redis, registry.queue_key(user_id, target), req)
    await repusher.push()

    start = time.monotonic()
    acked = False
    ack_deadline = start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
    exec_deadline = start + exec_timeout
    next_repush = repusher.next_due()
    try:
        while time.monotonic() < exec_deadline:
            if not acked and time.monotonic() >= next_repush:
                await repusher.push()
                next_repush = repusher.next_due()
            resp = None
            # results 端点为 RPUSH 队列（ack/done 按序）；滚动窗口内旧实例仍
            # SET（string）：_pop_resp 捕获 WRONGTYPE 后回落 GET
            raw = await _pop_resp(redis, resp_key)
            if raw is not None:
                resp = json.loads(raw)
                if resp.get("user_id") != user_id:
                    resp = None
            if resp is not None:
                if resp.get("stage") == "ack":
                    acked = True
                    # 不 delete：队列语义下 ack 出队即消费，残留的 delete 会把
                    # 已入队的 done 连带清掉（背靠背回传时错误结局退化为超时）
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
        await repusher.cleanup()


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
    redis = _binary_redis()  # upblob list 是裸二进制帧（req/resp 均为 JSON，bytes 兼容）
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
                # 窗口等待期也要消费中断哨兵：daemon 拉流中断开时 /upload 端点
                # 会向 resp 队列推 error done——不检查就会干等满 exec_timeout
                # （窗口永不腾空，2026-09-08 E2E 上传中断档实测 600s）
                raw = await _pop_resp(redis, resp_key)
                if raw is not None:
                    resp = json.loads(raw)
                    if resp.get("user_id") == user_id and resp.get("stage") == "done":
                        raise AppError(
                            ErrorCode.SANDBOX_EXEC_FAILED,
                            args={"detail": str(resp.get("error") or "upload stream failed")},
                        )
                await asyncio.sleep(_UPBLOB_POLL_INTERVAL)
            else:
                raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
            await redis.rpush(blob_key, frame)
            await redis.expire(blob_key, 120)
        while time.monotonic() < deadline and done is None:
            # results 端点为 RPUSH 队列（ack/done 按序）；旧实例 SET（string）
            # 由 _pop_resp 捕获 WRONGTYPE 后回落 GET
            raw = await _pop_resp(redis, resp_key)
            resp = json.loads(raw) if raw is not None else None
            if resp is not None and resp.get("user_id") == user_id:
                if resp.get("stage") == "ack":
                    acked = True
                    # 同 stream 路径：不 delete，防背靠背 done 被连带清掉
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

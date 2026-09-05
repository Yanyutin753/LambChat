"""本地沙箱中继：daemon SSE 通道、结果回传、在线状态。"""

import asyncio
import json
import socket
import time
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_current_user_pat_or_jwt, require_pat_only
from src.infra.logging import get_logger
from src.infra.sandbox.relay.registry import (
    SandboxClientRegistry,
    parse_daemon_platform,
    parse_daemon_version,
)
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()

_POLL_INTERVAL = 0.05
_HEARTBEAT_SECONDS = 15
_NODE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _redis():
    return get_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


def _request_age_seconds(raw: str) -> float:
    """解析下发帧的 ts 字段算龄；缺失/损坏按 0（新鲜）处理，兼容旧格式写入方。"""
    try:
        ts = json.loads(raw).get("ts")
    except (ValueError, TypeError, AttributeError):
        return 0.0
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return 0.0
    return max(time.time() - float(ts), 0.0)


async def channel_frames(
    redis,
    registry: SandboxClientRegistry,
    user_id: str,
    client_id: str,
    *,
    stop: asyncio.Event,
    version: str = "",
    platform: str = "",
) -> AsyncIterator[str]:
    """SSE 帧生成器：hello -> (tool_call | 心跳) 循环；连接期心跳注册表。

    心跳前校验属主：新连接 register 清空注册表后，旧流在此退场（后连踢前连），
    踢旧窗口收敛到一个心跳周期（15s）。旧流结束时 finally 的 unregister 只
    hdel 自己的字段，不会破坏新连接的注册。心跳带同一 ``version``/``platform``
    重写——不带会把注册值降级回纯 node_id，daemon 版本/平台 15s 后丢失。

    陈旧请求丢弃：daemon 重连后 list 里残留的断连前积压请求，按 dispatch 写入
    的 ts 判龄，超过 ACK 超时的直接丢弃——执行窗口早已超时，下发只会白白
    消耗 daemon 并让调用方等到 exec 超时。
    """
    yield f"event: hello\ndata: {json.dumps({'client_id': client_id})}\n\n"
    loop = asyncio.get_event_loop()
    last_beat = loop.time()  # 首个心跳在间隔之后到点，保证 hello 后紧跟的是 tool_call
    while not stop.is_set():
        now = loop.time()
        if now - last_beat >= _HEARTBEAT_SECONDS:
            active = await registry.get_active(user_id)
            if active is None or active[0] != client_id:
                return  # 已被新连接取代（或注册表失效），旧流退场
            await registry.heartbeat(
                user_id, client_id, _NODE_ID, version=version, platform=platform
            )
            last_beat = now
            yield ": heartbeat\n\n"
        raw = await redis.lpop(f"sandbox:req:{user_id}")
        if raw is not None:
            age = _request_age_seconds(raw)
            if age > settings.SANDBOX_LOCAL_ACK_TIMEOUT:
                logger.debug(
                    "sandbox channel drops stale request for user %s (age %.1fs > %ss)",
                    user_id,
                    age,
                    settings.SANDBOX_LOCAL_ACK_TIMEOUT,
                )
                continue
            yield f"event: tool_call\ndata: {raw}\n\n"
            continue
        await asyncio.sleep(_POLL_INTERVAL)


def _version_tuple(version: str) -> tuple[int, ...]:
    """语义化版本串 → 可比较 int 元组：按 ``.`` 分段，非数字段容错按 0 处理。

    空串 → ``(0,)``（最低）：M1 旧 daemon 不上报 version，按最低版本拒连，
    倒逼升级到带版本上报与 self-update 的新客户端。段数不齐时短元组直接
    比较（``(0, 1) < (0, 1, 0)``），与直觉一致。

    数字判定必须 ``isascii() and isdigit()``（M4 T8 加固）：Unicode 数字
    （如 "٥"）``isdigit()`` 为真且 ``int()`` 可转成 5——伪造 version "٥.0"
    若被解析成 (5,0) 就绕过了版本门。非 ASCII 数字一律按 0（拒连侧）。
    """
    if not version:
        return (0,)
    return tuple(
        int(part) if part.isascii() and part.isdigit() else 0
        for part in version.strip().split(".")
    )


@router.get("/channel")
async def sandbox_channel(
    version: str = "",
    platform: str = "",
    user: TokenPayload = Depends(require_pat_only("sandbox:execute")),
):
    """daemon SSE 通道。``?version=``/``?platform=`` 是 daemon connect URL
    自带的客户端版本与归一平台（服务端访问日志可见），随 register/heartbeat
    存入注册表 hash value，status 端点解析成 daemon_version/daemon_platform
    暴露；platform 另供文件命令生成的平台分支（M4 T3）查询。

    版本门（M4 T5）：version 低于 ``SANDBOX_MIN_DAEMON_VERSION``（缺失按最低）
    直接 426 拒连——错误在 StreamingResponse 建立前 raise，走全局 AppError
    处理器返回统一 JSON 契约，daemon 侧拿到结构化错误码而非沉默断流；拒绝
    的连接不 register，不产生幽灵在线。
    """
    if _version_tuple(version) < _version_tuple(settings.SANDBOX_MIN_DAEMON_VERSION):
        logger.info(
            "sandbox channel rejected daemon version %r (min %s) for user %s",
            version,
            settings.SANDBOX_MIN_DAEMON_VERSION,
            user.sub,
        )
        raise AppError(
            ErrorCode.DAEMON_VERSION_UNSUPPORTED,
            args={
                "version": version or "unknown",
                "min": settings.SANDBOX_MIN_DAEMON_VERSION,
            },
        )
    registry = _registry()
    client_id = uuid.uuid4().hex[:12]
    await registry.register(user.sub, client_id, _NODE_ID, version=version, platform=platform)
    stop = asyncio.Event()

    async def generator():
        try:
            async for frame in channel_frames(
                _redis(),
                registry,
                user.sub,
                client_id,
                stop=stop,
                version=version,
                platform=platform,
            ):
                yield frame
        finally:
            await registry.unregister(user.sub, client_id)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class SandboxResultRequest(BaseModel):
    stage: str  # "ack" | "done"
    status: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None


@router.post("/results/{call_id}")
async def sandbox_result(
    call_id: str,
    request: Request,
    body: SandboxResultRequest,
    user: TokenPayload = Depends(require_pat_only("sandbox:execute")),
):
    # 回传 body 上限：stdout/base64 是失控大头，超限即拒绝，防止打爆 Redis 与内存
    if len(await request.body()) > settings.SANDBOX_RESULTS_MAX_BYTES:
        raise AppError(ErrorCode.SANDBOX_PAYLOAD_TOO_LARGE)
    payload = {"user_id": user.sub, **body.model_dump(exclude_none=True)}
    await _redis().set(f"sandbox:resp:{call_id}", json.dumps(payload), ex=120)
    return {"status": "ok"}


@router.get("/status")
async def sandbox_status(user: TokenPayload = Depends(get_current_user_pat_or_jwt)):
    active = await _registry().get_active(user.sub)
    if active is None:
        return {"online": False}
    # hash value 可能是 node_id|version|platform（新 daemon）、node_id|version
    # （M2）或纯 node_id（M1 旧格式），解析不出的字段为 null
    return {
        "online": True,
        "client_id": active[0],
        "daemon_version": parse_daemon_version(active[1]) or None,
        "daemon_platform": parse_daemon_platform(active[1]) or None,
    }


@router.post("/offline")
async def sandbox_offline(user: TokenPayload = Depends(require_pat_only("sandbox:execute"))):
    """daemon 优雅退出通知：主动注销当前活跃连接。

    不打此端点时，断连要等注册表 TTL（35s）或心跳属主校验（15s 周期）才暴露——
    M1 冒烟实证的窗口是 15-35s；daemon 退出前调一次 offline 把窗口收敛到一次 RTT。
    """
    registry = _registry()
    active = await registry.get_active(user.sub)
    if active is not None:
        await registry.unregister(user.sub, active[0])
    return {"status": "offline"}

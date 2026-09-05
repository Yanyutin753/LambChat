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
from src.infra.sandbox.relay.registry import SandboxClientRegistry
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
    redis, registry: SandboxClientRegistry, user_id: str, client_id: str, *, stop: asyncio.Event
) -> AsyncIterator[str]:
    """SSE 帧生成器：hello -> (tool_call | 心跳) 循环；连接期心跳注册表。

    心跳前校验属主：新连接 register 清空注册表后，旧流在此退场（后连踢前连），
    踢旧窗口收敛到一个心跳周期（15s）。旧流结束时 finally 的 unregister 只
    hdel 自己的字段，不会破坏新连接的注册。

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
            await registry.heartbeat(user_id, client_id, _NODE_ID)
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


@router.get("/channel")
async def sandbox_channel(user: TokenPayload = Depends(require_pat_only("sandbox:execute"))):
    registry = _registry()
    client_id = uuid.uuid4().hex[:12]
    await registry.register(user.sub, client_id, _NODE_ID)
    stop = asyncio.Event()

    async def generator():
        try:
            async for frame in channel_frames(_redis(), registry, user.sub, client_id, stop=stop):
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
    return {"online": True, "client_id": active[0]}


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

"""本地沙箱中继：daemon SSE 通道、结果回传、在线状态。"""

import asyncio
import json
import socket
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_current_user_pat_or_jwt, require_pat_scope
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.user import TokenPayload

router = APIRouter()

_POLL_INTERVAL = 0.05
_HEARTBEAT_SECONDS = 15
_NODE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _redis():
    return get_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


async def channel_frames(
    redis, registry: SandboxClientRegistry, user_id: str, client_id: str, *, stop: asyncio.Event
) -> AsyncIterator[str]:
    """SSE 帧生成器：hello -> (tool_call | 心跳) 循环；连接期心跳注册表。"""
    yield f"event: hello\ndata: {json.dumps({'client_id': client_id})}\n\n"
    loop = asyncio.get_event_loop()
    last_beat = loop.time()  # 首个心跳在间隔之后到点，保证 hello 后紧跟的是 tool_call
    while not stop.is_set():
        now = loop.time()
        if now - last_beat >= _HEARTBEAT_SECONDS:
            await registry.heartbeat(user_id, client_id, _NODE_ID)
            last_beat = now
            yield ": heartbeat\n\n"
        raw = await redis.lpop(f"sandbox:req:{user_id}")
        if raw is not None:
            yield f"event: tool_call\ndata: {raw}\n\n"
            continue
        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/channel")
async def sandbox_channel(user: TokenPayload = Depends(require_pat_scope("sandbox:execute"))):
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
    body: SandboxResultRequest,
    user: TokenPayload = Depends(require_pat_scope("sandbox:execute")),
):
    payload = {"user_id": user.sub, **body.model_dump(exclude_none=True)}
    await _redis().set(f"sandbox:resp:{call_id}", json.dumps(payload), ex=120)
    return {"status": "ok"}


@router.get("/status")
async def sandbox_status(user: TokenPayload = Depends(get_current_user_pat_or_jwt)):
    active = await _registry().get_active(user.sub)
    if active is None:
        return {"online": False}
    return {"online": True, "client_id": active[0]}

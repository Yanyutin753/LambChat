"""工具调用下发与结果等待：Redis list 请求 + key 轮询结果（spec §3.2，lpop 轮询替代 BLPOP）。"""

import asyncio
import json
import time
import uuid

from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

_POLL_INTERVAL = 0.05


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
                    raise AppError(
                        ErrorCode.SANDBOX_EXEC_FAILED,
                        args={"detail": str(resp.get("error", "local execution failed"))},
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

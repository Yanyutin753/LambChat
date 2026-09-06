"""本地沙箱中继：daemon SSE 通道、结果回传、在线状态。"""

import asyncio
import json
import socket
import time
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from src.api.deps import get_current_user_pat_or_jwt, require_pat_only
from src.infra.logging import get_logger
from src.infra.sandbox.relay.registry import (
    SandboxClientRegistry,
    parse_confirm_policy,
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

#: 多机 channel 的属主键前缀：同机重连换属主，旧流心跳时据此退场（对应
#: legacy 路径 register 清 hash 的「后连踢前连」语义）。
_OWNER_PREFIX = "sandbox:machineowner"


def _owner_key(user_id: str, machine_id: str) -> str:
    return f"{_OWNER_PREFIX}:{user_id}:{machine_id}"


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
    confirm_policy: str = "",
    machine_id: str = "",
    machine_name: str = "",
) -> AsyncIterator[str]:
    """SSE 帧生成器：hello -> (tool_call | 心跳) 循环；连接期心跳注册表。

    心跳前校验属主：新连接 register 清空注册表后，旧流在此退场（后连踢前连），
    踢旧窗口收敛到一个心跳周期（15s）。旧流结束时 finally 的 unregister 只
    hdel 自己的字段，不会破坏新连接的注册。心跳带同一 ``version``/``platform``
    /``confirm_policy`` 重写——不带会把注册值降级回纯 node_id，daemon
    版本/平台/策略 15s 后丢失。

    多机（``machine_id`` 非空）：属主校验按机器属主键（同机重连换属主踢旧流），
    下发队列按 ``registry.queue_key`` 分机器；legacy 路径语义零变化。

    陈旧请求丢弃：daemon 重连后 list 里残留的断连前积压请求，按 dispatch 写入
    的 ts 判龄，超过 ACK 超时的直接丢弃——执行窗口早已超时，下发只会白白
    消耗 daemon 并让调用方等到 exec 超时。
    """
    hello = {"client_id": client_id}
    if machine_id:
        hello["machine_id"] = machine_id
    yield f"event: hello\ndata: {json.dumps(hello)}\n\n"
    loop = asyncio.get_event_loop()
    last_beat = loop.time()  # 首个心跳在间隔之后到点，保证 hello 后紧跟的是 tool_call
    req_key = registry.queue_key(user_id, machine_id) if machine_id else f"sandbox:req:{user_id}"
    while not stop.is_set():
        now = loop.time()
        if now - last_beat >= _HEARTBEAT_SECONDS:
            if machine_id:
                # 多机属主校验：同机新连接已改写属主键时，旧流退场
                owner = await redis.get(_owner_key(user_id, machine_id))
                if owner != client_id:
                    return
            else:
                active = await registry.get_active(user_id)
                if active is None or active[0] != client_id:
                    return  # 已被新连接取代（或注册表失效），旧流退场
            await registry.heartbeat(
                user_id,
                client_id,
                _NODE_ID,
                version=version,
                platform=platform,
                confirm_policy=confirm_policy,
                machine_id=machine_id,
                machine_name=machine_name,
            )
            if machine_id:
                await redis.set(_owner_key(user_id, machine_id), client_id, ex=35)
            last_beat = now
            yield ": heartbeat\n\n"
        raw = await redis.lpop(req_key)
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
        int(part) if part.isascii() and part.isdigit() else 0 for part in version.strip().split(".")
    )


@router.get("/channel")
async def sandbox_channel(
    version: str = "",
    platform: str = "",
    confirm_policy: str = "",
    machine_id: str = "",
    machine_name: str = "",
    user: TokenPayload = Depends(require_pat_only("sandbox:execute")),
):
    """daemon SSE 通道。``?version=``/``?platform=``/``?confirm_policy=`` 是
    daemon connect URL 自带的客户端版本、归一平台与确认策略（服务端访问日志
    可见），随 register/heartbeat 存入注册表 hash value，status 端点解析成
    daemon_version/daemon_platform/daemon_confirm_policy 暴露；platform 供
    文件命令生成的平台分支（M4 T3）、confirm_policy 供服务端统一确认门
    实时查询（非法值在入口归一空串，门侧按未上报归 all 保守确认）；
    ``machine_id``/``machine_name``（多机 daemon）是注册表机器分槽主键与
    展示名，空值走 legacy 单机路径（0.2.0 兼容）。

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
    confirm_policy = confirm_policy if confirm_policy in ("all", "commands", "none") else ""
    registry = _registry()
    client_id = uuid.uuid4().hex[:12]
    await registry.register(
        user.sub,
        client_id,
        _NODE_ID,
        version=version,
        platform=platform,
        confirm_policy=confirm_policy,
        machine_id=machine_id,
        machine_name=machine_name,
    )
    if machine_id:  # 多机属主：同机重连改写属主键，旧流心跳时据此退场
        await _redis().set(_owner_key(user.sub, machine_id), client_id, ex=35)
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
                confirm_policy=confirm_policy,
                machine_id=machine_id,
                machine_name=machine_name,
            ):
                yield frame
        finally:
            await registry.unregister(user.sub, client_id, machine_id=machine_id)

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


@router.get("/machines")
async def sandbox_machines(user: TokenPayload = Depends(get_current_user_pat_or_jwt)):
    """在线机器列表（多机 daemon）：machine_id/name/platform/version/policy。"""
    machines = await _registry().list_machines(user.sub)
    default = await _registry().get_default_machine(user.sub)
    return {"machines": machines, "default_machine_id": default}


class MachineRenameRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


@router.patch("/machines/{machine_id}")
async def sandbox_machine_rename(
    machine_id: str,
    body: MachineRenameRequest,
    user: TokenPayload = Depends(get_current_user_pat_or_jwt),
):
    """重命名机器：写 rename 覆盖层，daemon 重连上报的 hostname 不冲掉自定义名。"""
    name = body.name.strip()
    if not name:
        raise AppError(ErrorCode.SANDBOX_MACHINE_NOT_FOUND, args={"machine": machine_id})
    if len(name) > 64:
        name = name[:64]
    await _registry().rename_machine(user.sub, machine_id, name)
    return {"status": "ok", "machine_id": machine_id, "name": name}


@router.put("/machines/{machine_id}/default")
async def sandbox_machine_set_default(
    machine_id: str,
    user: TokenPayload = Depends(get_current_user_pat_or_jwt),
):
    """设默认机：无会话级选择时的执行目标。"""
    await _registry().set_default_machine(user.sub, machine_id)
    return {"status": "ok", "default_machine_id": machine_id}


@router.delete("/machines/{machine_id}")
async def sandbox_machine_forget(
    machine_id: str,
    user: TokenPayload = Depends(get_current_user_pat_or_jwt),
):
    """移除离线机器（清集合成员、rename 覆盖层与默认机指向）。"""
    removed = await _registry().forget_machine(user.sub, machine_id)
    if not removed:
        raise AppError(
            ErrorCode.SANDBOX_MACHINE_NOT_FOUND,
            args={"machine": machine_id},
        )
    return {"status": "ok"}


@router.get("/status")
async def sandbox_status(user: TokenPayload = Depends(get_current_user_pat_or_jwt)):
    """daemon 在线状态。

    legacy 活跃连接优先（带 ``client_id``）；多机 daemon（0.3.0+ 带
    machine_id）不落 legacy hash，在线判定走 :meth:`is_online`（任一机器
    在线即在线，与机器列表一致），版本/平台/策略取缺省目标机的注册 value
    （默认机→唯一在线机，与 dispatch 解析同规则；无缺省目标时这些字段为
    null）。value 可能是 node_id|version|platform|confirm_policy（新
    daemon）、node_id|version|platform（M4）、node_id|version（M2）或纯
    node_id（M1 旧格式），解析不出的字段为 null。
    """
    registry = _registry()
    active = await registry.get_active(user.sub)
    if active is not None:
        client_id, value = active
    else:
        if not await registry.is_online(user.sub):
            return {"online": False}
        target = await registry.resolve_target(user.sub)
        client_id = None
        value = await registry.machine_value(user.sub, target) if target else ""
    status = {
        "online": True,
        "daemon_version": parse_daemon_version(value) or None,
        "daemon_platform": parse_daemon_platform(value) or None,
        "daemon_confirm_policy": parse_confirm_policy(value) or None,
    }
    if client_id is not None:
        status["client_id"] = client_id
    return status


@router.post("/offline")
async def sandbox_offline(
    machine_id: str = "",
    user: TokenPayload = Depends(require_pat_only("sandbox:execute")),
):
    """daemon 优雅退出通知：主动注销当前活跃连接（``machine_id`` 定向注销多机
    中的本机；缺省走 legacy 活跃连接）。

    不打此端点时，断连要等注册表 TTL（35s）或心跳属主校验（15s 周期）才暴露——
    M1 冒烟实证的窗口是 15-35s；daemon 退出前调一次 offline 把窗口收敛到一次 RTT。
    """
    registry = _registry()
    if machine_id:
        await registry.unregister(user.sub, "", machine_id)
        await _redis().delete(_owner_key(user.sub, machine_id))
        return {"status": "offline", "machine_id": machine_id}
    active = await registry.get_active(user.sub)
    if active is not None:
        await registry.unregister(user.sub, active[0])
    return {"status": "offline"}

"""中继链路集成测试：dispatch → channel_frames（daemon 收帧）→ results 端点回传。

模拟 daemon 的 SSE 帧解析（对齐 lambchat_sandbox.transport 的 _FrameParser 契约），
把「服务端下发 - daemon 回传 - dispatch 收敛」串成一条真实链路——覆盖队列入队、
BLPOP 下发、ack/done 两阶段 RPUSH 队列、机器绑定校验与滚动发布期旧格式兜底。
"""

import asyncio
import json

import pytest
from redis.exceptions import ResponseError

from src.api.routes import sandbox as sandbox_route
from src.infra.sandbox.relay import dispatch as dispatch_module
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.errors import AppError, ErrorCode


class _FakeRedis:
    """string/list/hash 内存 Redis：TTL 忽略（本文件不测过期）。

    LPOP/BLPOP 命中 string key 按真 Redis 语义抛 WRONGTYPE（对齐
    test_dispatch 的 fake——旧格式兜底路径必须真实捕获该错误）。"""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}
        self.expires: list[str] = []

    def _wrongtype(self, key):
        if key in self.kv:
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def blpop(self, key, timeout=0):
        self._wrongtype(key)
        items = self.lists.get(key)
        if items:
            return key, items.pop(0)
        if timeout and timeout > 0:
            await asyncio.sleep(timeout)
        return None

    async def lpop(self, key):
        self._wrongtype(key)
        items = self.lists.get(key)
        return items.pop(0) if items else None

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def get(self, key):
        return self.kv.get(key)

    async def expire(self, key, seconds):
        self.expires.append(key)

    async def delete(self, key):
        self.kv.pop(key, None)
        self.lists.pop(key, None)


class _FakeRegistry:
    def __init__(self, resolved):
        self.resolved = resolved

    async def resolve_target(self, user_id, machine_id=None):
        if machine_id:
            return machine_id if machine_id == self.resolved else None
        return self.resolved

    def queue_key(self, user_id, machine_id):
        return (
            f"sandbox:req:{user_id}:{machine_id}"
            if machine_id != "legacy"
            else f"sandbox:req:{user_id}"
        )


class _FakeRequest:
    def __init__(self, body: bytes = b""):
        self._body = body
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        return self._body


def _fake_user():
    from src.kernel.schemas.user import TokenPayload

    return TokenPayload(sub="u1", username="t", roles=["user"], permissions=["sandbox:execute"])


@pytest.fixture
def wired(monkeypatch):
    """dispatch 与 channel_frames/results 端点共用同一个 fake Redis。"""
    redis = _FakeRedis()
    registry = _FakeRegistry("mac1")
    monkeypatch.setattr(dispatch_module, "_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: redis)
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)
    monkeypatch.setattr(dispatch_module, "_BLPOP_TIMEOUT", 0.01)
    monkeypatch.setattr(sandbox_route, "_BLPOP_TIMEOUT", 0.01)
    return redis


async def _consume_tool_call_frame(redis, registry) -> dict:
    """模拟 daemon 消费 SSE 通道：从队列经 channel_frames 拿到 tool_call 帧。"""
    stop = asyncio.Event()
    request = None
    async for frame in sandbox_route.channel_frames(
        redis,
        registry,
        "u1",
        "c1",
        stop=stop,
        version="0.4.0",
        platform="linux",
        machine_id="mac1",
        machine_name="SRV",
    ):
        if frame.startswith("event: tool_call"):
            payload = frame.split("data: ", 1)[1].strip()
            request = json.loads(payload)
            break
    stop.set()
    assert request is not None, "daemon 未收到 tool_call 帧"
    return request


async def test_full_relay_chain_roundtrip(wired, monkeypatch):
    """dispatch → 队列 → channel 帧下发 → ack/done 经 results 端点回传 → dispatch 返回。"""
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        request = await _consume_tool_call_frame(wired, _FakeRegistry("mac1"))
        assert request["op"] == "exec"
        call_id = request["call_id"]
        # daemon 先 ack 再 done（均走真实 results 端点，带 machine_id 绑定）
        await sandbox_route.sandbox_result(
            call_id=call_id,
            request=_FakeRequest(),
            body=sandbox_route.SandboxResultRequest(stage="ack"),
            machine_id="mac1",
            user=_fake_user(),
        )
        await sandbox_route.sandbox_result(
            call_id=call_id,
            request=_FakeRequest(),
            body=sandbox_route.SandboxResultRequest(stage="done", status="ok", stdout="hi"),
            machine_id="mac1",
            user=_fake_user(),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo hi"}, machine_id="mac1")
    await task
    assert result["stdout"] == "hi"
    # 调用上下文清理：resp 队列与机器绑定键不留残骸
    assert not any(k.startswith("sandbox:resp:") for k in wired.lists)
    assert not any(k.startswith("sandbox:callassign:") for k in wired.kv)


async def test_result_from_wrong_machine_is_rejected(wired, monkeypatch):
    """机器绑定：A 机冒答 B 机的调用被拒（409 sandbox_result_mismatch），不写队列。"""
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def attacker():
        request = await _consume_tool_call_frame(wired, _FakeRegistry("mac1"))
        with pytest.raises(AppError) as exc:
            await sandbox_route.sandbox_result(
                call_id=request["call_id"],
                request=_FakeRequest(),
                body=sandbox_route.SandboxResultRequest(stage="ack"),
                machine_id="pc-evil",
                user=_fake_user(),
            )
        assert exc.value.error_code == ErrorCode.SANDBOX_RESULT_MISMATCH
        assert not any(k.startswith("sandbox:resp:") for k in wired.lists)

    task = asyncio.create_task(attacker())
    with pytest.raises(AppError):
        await dispatch_local_call("u1", "exec", {"command": "ls"}, machine_id="mac1")
    await task


async def test_result_without_machine_id_still_accepted(wired, monkeypatch):
    """兼容窗口：旧 daemon 不带 machine_id 回传——绑定校验跳过（放行）。"""
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def legacy_daemon():
        request = await _consume_tool_call_frame(wired, _FakeRegistry("mac1"))
        await sandbox_route.sandbox_result(
            call_id=request["call_id"],
            request=_FakeRequest(),
            body=sandbox_route.SandboxResultRequest(stage="ack"),
            machine_id="",  # 旧 daemon：不携带机器标识
            user=_fake_user(),
        )
        await sandbox_route.sandbox_result(
            call_id=request["call_id"],
            request=_FakeRequest(),
            body=sandbox_route.SandboxResultRequest(stage="done", status="ok"),
            machine_id="",
            user=_fake_user(),
        )

    task = asyncio.create_task(legacy_daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "ls"}, machine_id="mac1")
    await task
    assert result["status"] == "ok"


async def test_legacy_set_result_still_readable_during_rolling_deploy(wired, monkeypatch):
    """滚动发布兜底：旧实例 SET 写入的 resp 值仍可被新 dispatch 读到（GET 兜底）。"""
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def old_replica_daemon():
        request = await _consume_tool_call_frame(wired, _FakeRegistry("mac1"))
        call_id = request["call_id"]
        # 旧格式：SET 直接覆盖（而非 RPUSH 队列）
        await wired.set(
            f"sandbox:resp:{call_id}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok"}),
        )

    task = asyncio.create_task(old_replica_daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "ls"}, machine_id="mac1")
    await task
    assert result["status"] == "ok"


async def test_results_endpoint_writes_queue_with_expiry(wired):
    """results 端点写入形态：RPUSH 队列（ack/done 两阶段依次入队）+ EXPIRE。"""
    wired.kv["sandbox:callassign:call-x"] = "mac1"
    await sandbox_route.sandbox_result(
        call_id="call-x",
        request=_FakeRequest(),
        body=sandbox_route.SandboxResultRequest(stage="ack"),
        machine_id="mac1",
        user=_fake_user(),
    )
    await sandbox_route.sandbox_result(
        call_id="call-x",
        request=_FakeRequest(),
        body=sandbox_route.SandboxResultRequest(stage="done", status="ok"),
        machine_id="mac1",
        user=_fake_user(),
    )
    queue = wired.lists["sandbox:resp:call-x"]
    assert json.loads(queue[0])["stage"] == "ack"
    assert json.loads(queue[1])["stage"] == "done"
    assert wired.expires.count("sandbox:resp:call-x") == 2


async def test_heartbeat_emitted_before_registry_writes(monkeypatch):
    """心跳帧必须先于注册表三连写发射：keepalive 只该依赖事件循环本身。

    注册表写入走共享 Redis 池——重任务把池占满时 await 会长时间挂起，若心
    跳跟在写后停发，daemon 侧 45s 读超时就误判断联（2026-09-09 生产断联）。
    属主校验/注册表写后移到心跳发射之后。"""
    monkeypatch.setattr(sandbox_route, "_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(sandbox_route, "_BLPOP_TIMEOUT", 0.01)

    calls: list[str] = []

    class _OrderRecordingRegistry(_FakeRegistry):
        async def get_active(self, user_id):
            calls.append("get_active")
            return ("c1", "node1")

        async def heartbeat(self, *args, **kwargs):
            calls.append("heartbeat")

    redis = _FakeRedis()
    registry = _OrderRecordingRegistry("legacy")  # legacy 路径（无 machine_id）
    stop = asyncio.Event()

    agen = sandbox_route.channel_frames(redis, registry, "u1", "c1", stop=stop)
    try:
        hello = await agen.__anext__()
        assert hello.startswith("event: hello")
        beat = await agen.__anext__()
        assert beat.startswith(": heartbeat")
        assert calls == []  # 心跳已在客户端手上，注册表还没写
        await agen.__anext__()  # 从 yield 恢复：此刻才做属主校验 + 注册表写
        assert calls == ["get_active", "heartbeat"]
    finally:
        stop.set()
        await agen.aclose()

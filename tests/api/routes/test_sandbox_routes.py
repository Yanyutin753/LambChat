"""sandbox 通道路由测试：帧生成器、双连接踢旧流、results 写入、status、PAT-only 收紧。"""

import asyncio
import json
import time

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import sandbox as sandbox_route


def _fake_user():
    from src.kernel.schemas.user import TokenPayload

    return TokenPayload(sub="u1", username="t", roles=["user"], permissions=["sandbox:execute"])


def _fake_pat_user(request: Request):
    """模拟 PAT 通道：get_current_user_pat_or_jwt 命中 PAT 时会在 request.state 挂 scopes。"""
    from src.kernel.schemas.user import TokenPayload

    request.state.pat_scopes = ["sandbox:execute"]
    return TokenPayload(sub="u1", username="t", roles=["user"], permissions=["sandbox:execute"])


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def lpop(self, key):
        items = self.lists.get(key)
        return items.pop(0) if items else None

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def get(self, key):
        return self.kv.get(key)


class _FakeRegistry:
    def __init__(self):
        self.beats = 0
        self.active: tuple[str, str] | None = ("c1", "node-a")
        self.unregistered: list[tuple[str, str]] = []
        self.registered: list[tuple[str, str, str, str, str, str]] = []
        self.heartbeats: list[tuple[str, str, str, str, str, str]] = []

    async def register(
        self, user_id, client_id, node_id, *, version="", platform="", confirm_policy=""
    ):
        self.active = (client_id, node_id)
        self.registered.append((user_id, client_id, node_id, version, platform, confirm_policy))

    async def heartbeat(
        self, user_id, client_id, node_id, *, version="", platform="", confirm_policy=""
    ):
        self.beats += 1
        self.heartbeats.append((user_id, client_id, node_id, version, platform, confirm_policy))

    async def unregister(self, user_id, client_id):
        self.unregistered.append((user_id, client_id))

    async def is_online(self, user_id):
        return True

    async def get_active(self, user_id):
        return self.active


async def test_channel_frames_hello_then_tool_call_then_heartbeat(monkeypatch):
    from src.api.routes.sandbox import channel_frames

    redis = _FakeRedis()
    await redis.rpush(
        "sandbox:req:u1", json.dumps({"call_id": "x", "op": "exec", "payload": {}, "timeout": 10})
    )
    registry = _FakeRegistry()
    monkeypatch.setattr(sandbox_route, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(sandbox_route, "_HEARTBEAT_SECONDS", 0.05)
    stop = asyncio.Event()
    frames = []
    async for frame in channel_frames(redis, registry, "u1", "c1", stop=stop):
        frames.append(frame)
        if len(frames) >= 3:
            stop.set()

    assert frames[0].startswith("event: hello\n")
    assert frames[1].startswith("event: tool_call\n")
    assert '"call_id": "x"' in frames[1]
    assert any(f.startswith(": heartbeat") for f in frames[2:])


@pytest.mark.parametrize("superseded_by", [("c2", "node-b"), None])
async def test_channel_frames_returns_when_superseded(monkeypatch, superseded_by):
    """后连踢前连：新连接 register 后，旧流在下一个心跳周期校验属主失败即 return。

    superseded_by=None 覆盖注册表整体失效（TTL 过期）的分支。
    """
    from src.api.routes.sandbox import channel_frames

    redis = _FakeRedis()
    await redis.rpush("sandbox:req:u1", json.dumps({"call_id": "x", "op": "exec", "payload": {}}))
    registry = _FakeRegistry()
    monkeypatch.setattr(sandbox_route, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(sandbox_route, "_HEARTBEAT_SECONDS", 0.05)
    stop = asyncio.Event()
    frames = []

    async def collect():
        async for frame in channel_frames(redis, registry, "u1", "c1", stop=stop):
            frames.append(frame)
            if len(frames) == 2:
                registry.active = superseded_by  # 第二个连接 register（或注册表失效）
            if len(frames) >= 3:
                stop.set()  # 兜底：旧实现会继续发心跳帧，勿让测试挂死

    await asyncio.wait_for(collect(), timeout=5)

    assert frames[0].startswith("event: hello\n")
    assert frames[1].startswith("event: tool_call\n")
    assert not any(f.startswith(": heartbeat") for f in frames)
    assert registry.beats == 0  # 失主后不再心跳续期，不把自己写回注册表


async def test_channel_frames_drops_stale_requests(monkeypatch):
    """陈旧请求丢弃：超过 ACK 超时的积压请求不下发（丢弃并打日志），新鲜的照常下发。

    daemon 重连后 Redis list 里可能残留断连前入队的旧请求——按 dispatch 入队时
    写入的 ts 判龄，超龄即丢，避免 daemon 一连上就收到注定超时的过期调用；
    无 ts 的帧（旧格式写入方）按新鲜处理，不误杀。
    """
    from src.api.routes.sandbox import channel_frames

    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 1)
    redis = _FakeRedis()
    await redis.rpush(
        "sandbox:req:u1",
        json.dumps({"call_id": "old", "op": "exec", "payload": {}, "ts": time.time() - 60}),
    )
    await redis.rpush(
        "sandbox:req:u1", json.dumps({"call_id": "legacy", "op": "exec", "payload": {}})
    )
    await redis.rpush(
        "sandbox:req:u1",
        json.dumps({"call_id": "new", "op": "exec", "payload": {}, "ts": time.time()}),
    )
    registry = _FakeRegistry()
    monkeypatch.setattr(sandbox_route, "_POLL_INTERVAL", 0.01)
    stop = asyncio.Event()
    frames = []
    async for frame in channel_frames(redis, registry, "u1", "c1", stop=stop):
        frames.append(frame)
        if len(frames) >= 3:  # hello + legacy + new（old 被丢弃）
            stop.set()

    yielded = [
        json.loads(frame.split("data: ", 1)[1])["call_id"]
        for frame in frames
        if frame.startswith("event: tool_call\n")
    ]
    assert yielded == ["legacy", "new"]  # 陈旧的 old 不出现，其余顺序保留


async def test_channel_and_results_reject_jwt(monkeypatch):
    """channel/results 是 daemon 端点：JWT（无 pat_scopes）一律 401 unauthorized。"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _FakeRedis())
    monkeypatch.setattr(sandbox_route, "_registry", lambda: _FakeRegistry())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 旧实现下 JWT 会通过并进入无限 SSE 流，wait_for 防 RED 阶段挂死
        channel_resp = await asyncio.wait_for(client.get("/api/sandbox/channel"), timeout=2.0)
        results_resp = await client.post(
            "/api/sandbox/results/call-1", json={"stage": "done", "status": "ok"}
        )
    assert channel_resp.status_code == 401
    assert channel_resp.json()["detail"]["code"] == "unauthorized"
    assert results_resp.status_code == 401
    assert results_resp.json()["detail"]["code"] == "unauthorized"


async def test_results_endpoint_writes_resp(monkeypatch):
    redis = _FakeRedis()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_redis", lambda: redis)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/sandbox/results/call-1",
            json={"stage": "done", "status": "ok", "stdout": "hi"},
        )
    assert resp.status_code == 200
    stored = json.loads(redis.kv["sandbox:resp:call-1"])
    assert stored["user_id"] == "u1" and stored["stage"] == "done"


async def test_results_rejects_oversized_body(monkeypatch):
    """results 上限：body 超过 SANDBOX_RESULTS_MAX_BYTES 返回 413，不落 Redis。

    daemon 侧 stdout/base64 回传是失控大头（如误把二进制整读进来），
    超限即拒绝，防止单次回传把 Redis 与内存打爆。
    """
    redis = _FakeRedis()
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_RESULTS_MAX_BYTES", 64)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_redis", lambda: redis)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/sandbox/results/call-1",
            json={"stage": "done", "status": "ok", "stdout": "x" * 200},
        )
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "sandbox_payload_too_large"
    assert not redis.kv  # 超限直接拒绝，不写 resp key


def _results_body_of_size(n: int) -> bytes:
    """构造恰好 n 字节的合法 results JSON body（stdout 填充字符逐字节可调）。"""
    template = json.dumps({"stage": "done", "status": "ok", "stdout": ""})
    body = json.dumps({"stage": "done", "status": "ok", "stdout": "x" * (n - len(template))})
    assert len(body.encode("utf-8")) == n
    return body.encode("utf-8")


async def _post_results_with_size(monkeypatch, body: bytes):
    """带精确字节数 body 打 results 端点；返回 (response, redis)。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_RESULTS_MAX_BYTES", 128)
    redis = _FakeRedis()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_redis", lambda: redis)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/sandbox/results/call-1",
            content=body,
            headers={"content-type": "application/json"},
        )
    return resp, redis


async def test_results_accepts_body_at_exact_limit(monkeypatch):
    """at-limit 边界：body 恰好 SANDBOX_RESULTS_MAX_BYTES 放行（上限判 > 而非 >=，
    卡在限上的合法回传不得被 413 误杀）。"""
    resp, redis = await _post_results_with_size(monkeypatch, _results_body_of_size(128))

    assert resp.status_code == 200
    assert "sandbox:resp:call-1" in redis.kv


async def test_results_rejects_body_one_byte_over_limit(monkeypatch):
    """at-limit 边界：超限 1 字节即 413 sandbox_payload_too_large，不落 Redis。"""
    resp, redis = await _post_results_with_size(monkeypatch, _results_body_of_size(129))

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "sandbox_payload_too_large"
    assert not redis.kv


async def test_status_endpoint(monkeypatch):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: _FakeRegistry())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/status")
    assert resp.status_code == 200
    # 旧格式 value（无版本/平台上报的 daemon）：daemon_version/daemon_platform 为 null
    assert resp.json() == {
        "online": True,
        "client_id": "c1",
        "daemon_version": None,
        "daemon_platform": None,
        "daemon_confirm_policy": None,
    }


async def test_status_endpoint_reports_daemon_version(monkeypatch):
    """版本地基：注册表 value 里的 node_id|version 解析成 daemon_version 返回。"""
    registry = _FakeRegistry()
    registry.active = ("c1", "node-a|0.1.0")
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "online": True,
        "client_id": "c1",
        "daemon_version": "0.1.0",
        "daemon_platform": None,  # M2 两段格式：无平台段
        "daemon_confirm_policy": None,
    }


async def test_status_endpoint_reports_daemon_platform(monkeypatch):
    """平台地基（M4 T3）：三段 value 的第三段解析成 daemon_platform 返回。"""
    registry = _FakeRegistry()
    registry.active = ("c1", "node-a|0.1.0|win32")
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "online": True,
        "client_id": "c1",
        "daemon_version": "0.1.0",
        "daemon_platform": "win32",
        "daemon_confirm_policy": None,
    }


async def test_status_endpoint_reports_confirm_policy(monkeypatch):
    """服务端确认门：四段 value 的第四段解析成 daemon_confirm_policy 返回。"""
    registry = _FakeRegistry()
    registry.active = ("c1", "node-a|0.2.0|linux|commands")
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "online": True,
        "client_id": "c1",
        "daemon_version": "0.2.0",
        "daemon_platform": "linux",
        "daemon_confirm_policy": "commands",
    }


async def test_channel_registers_confirm_policy_from_query(monkeypatch):
    """channel 端点从 query 读 confirm_policy 随 register 存入并透传帧生成器
    （心跳重写不带上会把注册值降级）；非法值归一空串。"""
    registry = _FakeRegistry()
    seen: dict[str, object] = {}

    async def fake_frames(
        redis, reg, user_id, client_id, *, stop, version="", platform="", confirm_policy=""
    ):
        seen["confirm_policy"] = confirm_policy
        if False:  # pragma: no cover - 使其成为 async generator（空流即结束）
            yield ""

    monkeypatch.setattr(sandbox_route, "channel_frames", fake_frames)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _FakeRedis())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/sandbox/channel",
            params={"version": "0.2.0", "platform": "linux", "confirm_policy": "none"},
        )
        assert resp.status_code == 200
        resp2 = await client.get(
            "/api/sandbox/channel",
            params={"version": "0.2.0", "confirm_policy": "yolo"},
        )
        assert resp2.status_code == 200
    assert registry.registered[0][5] == "none"
    assert registry.registered[1][5] == ""  # 非法值归一空串
    assert seen["confirm_policy"] == ""  # 帧生成器收到归一后的值


async def test_channel_registers_version_from_query(monkeypatch):
    """channel 端点从 query 读 version 随 register 存入；心跳帧生成器收到同一
    version（否则首个心跳会把注册值降级回纯 node_id，版本 15s 后丢失）。"""
    registry = _FakeRegistry()
    seen: dict[str, object] = {}

    async def fake_frames(
        redis, reg, user_id, client_id, *, stop, version="", platform="", confirm_policy=""
    ):
        seen["version"] = version
        seen["platform"] = platform
        seen["registered"] = list(registry.registered)
        if False:  # pragma: no cover - 使其成为 async generator（空流即结束）
            yield ""

    monkeypatch.setattr(sandbox_route, "channel_frames", fake_frames)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _FakeRedis())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/channel?version=0.2.0")
    assert resp.status_code == 200
    assert seen["version"] == "0.2.0"
    assert len(registry.registered) == 1
    user_id, _client_id, node_id, version, platform, _confirm_policy = registry.registered[0]
    assert (user_id, version) == ("u1", "0.2.0")
    assert node_id == sandbox_route._NODE_ID
    assert platform == ""  # 未上报平台：保持空（旧 daemon 兼容）


async def test_channel_registers_platform_from_query(monkeypatch):
    """平台地基（M4 T3）：channel 从 query 读 platform 随 register 存入；心跳
    帧生成器收到同一 platform（不带则 15s 后注册值降级丢平台，对齐 version）。"""
    registry = _FakeRegistry()
    seen: dict[str, object] = {}

    async def fake_frames(
        redis, reg, user_id, client_id, *, stop, version="", platform="", confirm_policy=""
    ):
        seen["platform"] = platform
        if False:  # pragma: no cover - 使其成为 async generator（空流即结束）
            yield ""

    monkeypatch.setattr(sandbox_route, "channel_frames", fake_frames)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _FakeRedis())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/sandbox/channel?version=0.2.0&platform=win32")
    assert resp.status_code == 200
    assert seen["platform"] == "win32"
    assert len(registry.registered) == 1
    user_id, _client_id, node_id, version, platform, _confirm_policy = registry.registered[0]
    assert (user_id, version, platform) == ("u1", "0.2.0", "win32")
    assert node_id == sandbox_route._NODE_ID


def _channel_app(monkeypatch, registry):
    """组装 channel 测试 app：PAT 通道 + 假注册表/Redis，返回 AsyncClient 工厂。"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _FakeRedis())
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_channel_rejects_version_below_min(monkeypatch):
    """最低版本拒连（M4 T5）：daemon 上报版本低于 SANDBOX_MIN_DAEMON_VERSION 时
    426 daemon_version_unsupported，且不注册进在线表（拒连不产生幽灵在线）。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.2.0")
    registry = _FakeRegistry()
    async with _channel_app(monkeypatch, registry) as client:
        resp = await client.get("/api/sandbox/channel?version=0.1.9")
    assert resp.status_code == 426
    detail = resp.json()["detail"]
    assert detail["code"] == "daemon_version_unsupported"
    assert detail["args"] == {"version": "0.1.9", "min": "0.2.0"}
    assert registry.registered == []


async def test_channel_rejects_missing_version(monkeypatch):
    """无 version（M1 旧 daemon / 手工连接）按最低处理：同样 426 拒连。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.2.0")
    registry = _FakeRegistry()
    async with _channel_app(monkeypatch, registry) as client:
        resp = await client.get("/api/sandbox/channel")
    assert resp.status_code == 426
    assert resp.json()["detail"]["code"] == "daemon_version_unsupported"
    assert registry.registered == []


async def test_channel_rejects_malformed_version(monkeypatch):
    """坏版本串容错：非数字段按 0 处理（"x.y.z" → (0,0,0)），低于 min 即拒。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.2.0")
    registry = _FakeRegistry()
    async with _channel_app(monkeypatch, registry) as client:
        resp = await client.get("/api/sandbox/channel?version=x.y.z")
    assert resp.status_code == 426
    assert resp.json()["detail"]["args"] == {"version": "x.y.z", "min": "0.2.0"}


async def test_channel_allows_version_at_or_above_min(monkeypatch):
    """等于/高于放行：等于 min（0.2.0）与更高（0.3.0）都正常注册进流。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.2.0")
    seen: list[str] = []

    async def fake_frames(
        redis, reg, user_id, client_id, *, stop, version="", platform="", confirm_policy=""
    ):
        seen.append(version)
        if False:  # pragma: no cover - 空 async generator
            yield ""

    monkeypatch.setattr(sandbox_route, "channel_frames", fake_frames)
    for version in ("0.2.0", "0.3.0"):
        registry = _FakeRegistry()
        async with _channel_app(monkeypatch, registry) as client:
            resp = await client.get(f"/api/sandbox/channel?version={version}")
        assert resp.status_code == 200
        assert registry.registered and registry.registered[0][3] == version


async def test_channel_allows_equal_min_with_nonnumeric_suffix(monkeypatch):
    """容错语义：非数字段按 0——"0.2.x" 解析为 (0,2,0) 不低于 min "0.2.0"，放行。"""
    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.2.0")

    async def fake_frames(
        redis, reg, user_id, client_id, *, stop, version="", platform="", confirm_policy=""
    ):
        if False:  # pragma: no cover - 空 async generator
            yield ""

    monkeypatch.setattr(sandbox_route, "channel_frames", fake_frames)
    registry = _FakeRegistry()
    async with _channel_app(monkeypatch, registry) as client:
        resp = await client.get("/api/sandbox/channel?version=0.2.ignored")
    assert resp.status_code == 200


async def test_channel_version_gate_defaults(monkeypatch):
    """默认配置即拒旧：出厂 SANDBOX_MIN_DAEMON_VERSION=0.1.0，低于它的 0.0.x 拒连。"""
    monkeypatch.setattr(
        sandbox_route.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.1.0", raising=False
    )
    registry = _FakeRegistry()
    async with _channel_app(monkeypatch, registry) as client:
        resp = await client.get("/api/sandbox/channel?version=0.0.9")
    assert resp.status_code == 426
    assert resp.json()["detail"]["code"] == "daemon_version_unsupported"


def test_version_tuple_treats_unicode_digits_as_nonnumeric():
    """Unicode 数字加固（M4 T8）："٥".isdigit() 为真且 int() 可转成 5——伪造
    version "٥.0" 必须按非数字段容错 0（拒连），不能被解析成 (5,0) 放行。"""
    assert sandbox_route._version_tuple("٥.0") == (0, 0)
    assert sandbox_route._version_tuple("1.٥") == (1, 0)
    assert sandbox_route._version_tuple("١٢.٣") == (0, 0)  # 全 Unicode 段
    # ASCII 数字行为不变
    assert sandbox_route._version_tuple("0.10.2") == (0, 10, 2)


async def test_offline_endpoint_unregisters_active_client(monkeypatch):
    """daemon 主动下线：从 get_active 取当前 client_id 注销，收敛断连检测窗口。"""
    registry = _FakeRegistry()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/sandbox/offline")
    assert resp.status_code == 200
    assert resp.json() == {"status": "offline"}
    assert registry.unregistered == [("u1", "c1")]


async def test_offline_endpoint_without_active_client(monkeypatch):
    """无活跃连接时 offline 是幂等的：不注销任何字段，仍返回 offline。"""
    registry = _FakeRegistry()
    registry.active = None
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/sandbox/offline")
    assert resp.status_code == 200
    assert resp.json() == {"status": "offline"}
    assert registry.unregistered == []


async def test_offline_endpoint_rejects_jwt(monkeypatch):
    """offline 同为 daemon 端点：JWT（无 pat_scopes）一律 401。"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    monkeypatch.setattr(sandbox_route, "_registry", lambda: _FakeRegistry())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/sandbox/offline")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "unauthorized"

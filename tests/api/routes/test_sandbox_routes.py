"""sandbox 通道路由测试：帧生成器、双连接踢旧流、results 写入、status、PAT-only 收紧。"""

import asyncio
import json

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

    async def register(self, user_id, client_id, node_id):
        self.active = (client_id, node_id)

    async def heartbeat(self, *a, **k):
        self.beats += 1

    async def unregister(self, *a, **k):
        pass

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
    assert resp.json() == {"online": True, "client_id": "c1"}

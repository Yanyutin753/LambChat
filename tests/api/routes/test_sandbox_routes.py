"""sandbox 通道路由测试：帧生成器、results 写入、status。"""

import asyncio
import json

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import sandbox as sandbox_route


def _fake_user():
    from src.kernel.schemas.user import TokenPayload

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

    async def heartbeat(self, *a, **k):
        self.beats += 1

    async def unregister(self, *a, **k):
        pass

    async def is_online(self, user_id):
        return True

    async def get_active(self, user_id):
        return ("c1", "node-a")


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


async def test_results_endpoint_writes_resp(monkeypatch):
    redis = _FakeRedis()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
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

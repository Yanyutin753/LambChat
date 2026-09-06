"""sandbox 多机路由测试：machines 列表/默认/重命名/移除、channel 机器身份、offline 定向注销。"""

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
    """PAT 通道：require_pat_only 链路要求 request.state 挂 scopes。"""
    from src.kernel.schemas.user import TokenPayload

    request.state.pat_scopes = ["sandbox:execute"]
    return TokenPayload(sub="u1", username="t", roles=["user"], permissions=["sandbox:execute"])


class _FakeRegistry:
    def __init__(self):
        self.calls: dict[str, list] = {
            k: []
            for k in (
                "register",
                "unregister",
                "list_machines",
                "set_default",
                "rename",
                "forget",
                "get_default",
                "resolve",
            )
        }
        self.machines: list[dict] = []
        self.default: str | None = None

    async def register(
        self,
        user_id,
        client_id,
        node_id,
        *,
        version="",
        platform="",
        confirm_policy="",
        machine_id="",
        machine_name="",
    ):
        self.calls["register"].append((user_id, client_id, machine_id, machine_name))

    async def unregister(self, user_id, client_id, machine_id=""):
        self.calls["unregister"].append((user_id, client_id, machine_id))

    async def list_machines(self, user_id):
        self.calls["list_machines"].append(user_id)
        return self.machines

    async def set_default_machine(self, user_id, machine_id):
        self.calls["set_default"].append(machine_id)
        self.default = machine_id

    async def get_default_machine(self, user_id):
        return self.default

    async def rename_machine(self, user_id, machine_id, name):
        self.calls["rename"].append((machine_id, name))

    def queue_key(self, user_id, machine_id):
        return f"sandbox:req:{user_id}:{machine_id}"

    async def forget_machine(self, user_id, machine_id):
        self.calls["forget"].append(machine_id)
        return True


@pytest.fixture
def fake_registry(monkeypatch):
    reg = _FakeRegistry()
    monkeypatch.setattr(sandbox_route, "_registry", lambda: reg)
    return reg


class _NoopRedis:
    async def set(self, key, value, ex=None):
        pass

    async def get(self, key):
        return None

    async def delete(self, key):
        pass


@pytest.fixture
async def client(monkeypatch, fake_registry):
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _NoopRedis())
    app = FastAPI()
    app.include_router(sandbox_route.router, prefix="/api/sandbox")
    register_error_handlers(app)
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_machines_endpoint_lists_registry(fake_registry, client):
    fake_registry.machines = [
        {
            "machine_id": "mac1",
            "name": "MacBook",
            "platform": "darwin",
            "version": "0.3.0",
            "confirm_policy": "all",
            "online": True,
        },
    ]
    resp = await client.get("/api/sandbox/machines")
    assert resp.status_code == 200
    data = resp.json()
    assert data["machines"][0]["machine_id"] == "mac1"
    assert fake_registry.calls["list_machines"] == ["u1"]


async def test_machines_default_endpoint(fake_registry, client):
    resp = await client.put("/api/sandbox/machines/mac1/default")
    assert resp.status_code == 200
    assert fake_registry.calls["set_default"] == ["mac1"]


async def test_machines_rename_endpoint(fake_registry, client):
    resp = await client.patch("/api/sandbox/machines/mac1", json={"name": "主力开发机"})
    assert resp.status_code == 200
    assert fake_registry.calls["rename"] == [("mac1", "主力开发机")]


async def test_machines_rename_rejects_empty_name(fake_registry, client):
    resp = await client.patch("/api/sandbox/machines/mac1", json={"name": "  "})
    assert resp.status_code in (400, 422)


async def test_machines_forget_endpoint(fake_registry, client):
    resp = await client.delete("/api/sandbox/machines/old1")
    assert resp.status_code == 200
    assert fake_registry.calls["forget"] == ["old1"]


async def test_channel_registers_machine_identity(fake_registry, monkeypatch):
    """channel 带 machine_id/machine_name：注册与 hello 帧都携带机器身份。"""

    class _NoopRedis:
        async def lpop(self, key):
            return None

        async def set(self, key, value, ex=None):
            pass

        async def get(self, key):
            return None

        async def delete(self, key):
            pass

    captured: dict = {}

    class _Reg(_FakeRegistry):
        async def register(
            self,
            user_id,
            client_id,
            node_id,
            *,
            version="",
            platform="",
            confirm_policy="",
            machine_id="",
            machine_name="",
        ):
            captured.update(machine_id=machine_id, machine_name=machine_name)
            await super().register(
                user_id,
                client_id,
                node_id,
                version=version,
                platform=platform,
                confirm_policy=confirm_policy,
                machine_id=machine_id,
                machine_name=machine_name,
            )

        async def unregister(self, user_id, client_id, machine_id=""):
            await super().unregister(user_id, client_id, machine_id)

    reg = _Reg()
    monkeypatch.setattr(sandbox_route, "_registry", lambda: reg)
    monkeypatch.setattr(sandbox_route, "_redis", lambda: _NoopRedis())

    app = FastAPI()
    app.include_router(sandbox_route.router, prefix="/api/sandbox")
    register_error_handlers(app)
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_pat_user
    import asyncio

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        async with c.stream(
            "GET",
            "/api/sandbox/channel?version=0.3.0&machine_id=mac1&machine_name=MacBook",
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
                if b"hello" in body:
                    break
        await asyncio.sleep(0.05)
    assert captured["machine_id"] == "mac1"
    assert captured["machine_name"] == "MacBook"
    assert b'"machine_id": "mac1"' in body


async def test_offline_unregisters_selected_machine(fake_registry, client):
    resp = await client.post("/api/sandbox/offline?machine_id=mac1")
    assert resp.status_code == 200
    assert fake_registry.calls["unregister"] == [("u1", "", "mac1")]

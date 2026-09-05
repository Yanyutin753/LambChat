"""PAT 路由测试：创建返回一次明文、列表不含哈希、撤销、自撤销。"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.api.routes.auth import pat as pat_route
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(sub="u1", username="tester", roles=["user"], permissions=["chat:write"])


def _make_app(storage) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(pat_route.router, prefix="/api/auth/pat", tags=["Auth"])
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[pat_route.get_pat_storage] = lambda: storage
    return app


class _StubStorage:
    """直接用真 PATStorage + 假 collection（复用 Task 2 的 fake 思路）。"""

    def __init__(self):
        from src.infra.auth.pat import PATStorage
        from tests.infra.auth.test_pat import _FakeCollection

        coll = _FakeCollection()
        self._inner = PATStorage()
        # 真 _get_collection 每次返回同一 collection（惰性缓存），fake 须等价：
        # 绑定同一个实例，而不是每次调用新建
        self._inner._get_collection = lambda: coll  # noqa: SLF001

    def __getattr__(self, item):
        return getattr(self._inner, item)


async def test_create_returns_token_once():
    app = _make_app(_StubStorage())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/auth/pat", json={"name": "桌面端", "scopes": ["sandbox:execute"]}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"].startswith("lc_pat_")
    assert body["pat_id"]


async def test_list_hides_token_and_hash():
    storage = _StubStorage()
    await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    app = _make_app(storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/auth/pat")
    assert resp.status_code == 200
    item = resp.json()["pats"][0]
    assert "token" not in item and "token_hash" not in item
    assert item["name"] == "a" and item["prefix"].startswith("lc_pat_")


async def test_delete_revokes():
    storage = _StubStorage()
    _, rec = await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    app = _make_app(storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(f"/api/auth/pat/{rec.pat_id}")
        missing = await client.delete("/api/auth/pat/nonexistent")
    assert resp.status_code == 200
    assert missing.status_code == 401  # PAT_NOT_FOUND


# ---------- DELETE /current：PAT 自撤销（桌面壳"取消配对"用） ----------


def _wire_real_dual_channel(monkeypatch, storage: _StubStorage):
    """让真实 get_current_user_pat_or_jwt 跑通：verify/touch 走 fake collection，
    _load_user_payload 不落真库。"""
    from unittest.mock import AsyncMock

    from src.api import deps as api_deps
    from src.infra.auth import pat as pat_module

    orig_verify = pat_module.PATStorage.verify
    monkeypatch.setattr(
        pat_module.PATStorage,
        "verify",
        lambda self, token: orig_verify(storage._inner, token),  # noqa: SLF001
    )
    monkeypatch.setattr(
        pat_module.PATStorage,
        "touch_last_used",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        api_deps,
        "_load_user_payload",
        AsyncMock(return_value=_fake_user()),
    )


def _make_dual_channel_app(storage) -> FastAPI:
    """不做依赖覆盖：/current 走真实 PAT/JWT 双通道鉴权。"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(pat_route.router, prefix="/api/auth/pat", tags=["Auth"])
    app.dependency_overrides[pat_route.get_pat_storage] = lambda: storage
    return app


async def test_delete_current_revokes_the_bearer_pat_itself(monkeypatch):
    storage = _StubStorage()
    token, rec = await storage.create(user_id="u1", name="shell", scopes=["sandbox:execute"])
    _wire_real_dual_channel(monkeypatch, storage)
    app = _make_dual_channel_app(storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(
            "/api/auth/pat/current", headers={"Authorization": f"Bearer {token}"}
        )
        # 撤销后同一 PAT 再自删 → 已不存在（401 PAT_NOT_FOUND）
        again = await client.delete(
            "/api/auth/pat/current", headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert again.status_code == 401
    assert again.json()["detail"]["code"] == "pat_not_found"
    # 存储侧确认 revoked
    record, reason = await storage.verify(token)
    assert record is None and reason == "revoked"
    assert rec.pat_id


async def test_delete_current_rejects_jwt_bearer(monkeypatch):
    """该端点仅 PAT 可用：有效 JWT 走双通道依赖放行后，端点内 400 拒绝。"""
    storage = _StubStorage()
    _wire_real_dual_channel(monkeypatch, storage)
    # verify 不命中 lc_pat_ 前缀 → JWT 分支：伪造解码放行（JWT 解码本身另有测试覆盖）
    from unittest.mock import AsyncMock

    from src.api import deps as api_deps

    jwt_payload = _fake_user()
    monkeypatch.setattr(
        api_deps,
        "get_current_user_required",
        AsyncMock(return_value=jwt_payload),
    )
    app = _make_dual_channel_app(storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(
            "/api/auth/pat/current", headers={"Authorization": "Bearer some.jwt.value"}
        )
    assert resp.status_code == 400
    assert "personal access token" in resp.json()["detail"]["message"]


async def test_delete_current_invalid_pat_rejected(monkeypatch):
    """无效 PAT：双通道依赖在进入端点前即 401（PAT_NOT_FOUND）。"""
    storage = _StubStorage()
    _wire_real_dual_channel(monkeypatch, storage)
    app = _make_dual_channel_app(storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(
            "/api/auth/pat/current", headers={"Authorization": "Bearer lc_pat_unknown"}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "pat_not_found"

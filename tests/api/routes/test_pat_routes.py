"""PAT 路由测试：创建返回一次明文、列表不含哈希、撤销。"""

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

"""PAT/JWT 双通道鉴权依赖测试。"""

import asyncio

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.infra.auth import pat as pat_module
from src.infra.auth.pat import PATRecord


@pytest.fixture(autouse=True)
def _reset_pat_touch_throttle():
    """隔离进程内 touch_last_used 节流状态，避免用例间串扰。"""
    throttle_state = getattr(api_deps, "_pat_touch_last", None)
    if throttle_state is not None:
        throttle_state.clear()
    yield
    if throttle_state is not None:
        throttle_state.clear()


def _pat_record(scopes: list[str]) -> PATRecord:
    from datetime import datetime, timezone

    return PATRecord(
        pat_id="p1",
        user_id="u1",
        name="t",
        scopes=scopes,
        token_hash="h" * 64,
        prefix="lc_pat_abc",
        created_at=datetime.now(timezone.utc),
    )


async def test_pat_token_builds_payload(monkeypatch):
    record = _pat_record(["sandbox:execute"])

    async def _no_touch(_self, _pat_id):
        return None

    monkeypatch.setattr(
        pat_module.PATStorage, "verify", lambda self, token: _async_return((record, None))
    )
    monkeypatch.setattr(pat_module.PATStorage, "touch_last_used", _no_touch)
    monkeypatch.setattr(
        api_deps,
        "_load_user_payload",
        lambda user_id: _async_return(
            api_deps.TokenPayload(
                sub="u1", username="tester", roles=["user"], permissions=["sandbox:execute"]
            )
        ),
    )
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(user=Depends(api_deps.require_pat_scope("sandbox:execute"))):
        return {"sub": user.sub}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/probe", headers={"Authorization": "Bearer lc_pat_good"})
    assert resp.status_code == 200 and resp.json()["sub"] == "u1"


async def test_pat_missing_scope_denied(monkeypatch):
    record = _pat_record([])

    async def _no_touch(_self, _pat_id):
        return None

    monkeypatch.setattr(
        pat_module.PATStorage, "verify", lambda self, token: _async_return((record, None))
    )
    monkeypatch.setattr(pat_module.PATStorage, "touch_last_used", _no_touch)
    monkeypatch.setattr(
        api_deps,
        "_load_user_payload",
        lambda user_id: _async_return(
            api_deps.TokenPayload(sub="u1", username="tester", roles=["user"], permissions=[])
        ),
    )
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(user=Depends(api_deps.require_pat_scope("sandbox:execute"))):
        return {"sub": user.sub}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/probe", headers={"Authorization": "Bearer lc_pat_bad"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "pat_scope_denied"


async def test_invalid_pat_rejected(monkeypatch):
    async def _none(_self, _token):
        return None, "unknown"

    monkeypatch.setattr(pat_module.PATStorage, "verify", _none)
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(user=Depends(api_deps.get_current_user_pat_or_jwt)):
        return {"sub": user.sub}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/probe", headers={"Authorization": "Bearer lc_pat_unknown"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "pat_not_found"


async def test_expired_pat_rejected(monkeypatch):
    """verify 返回 reason=expired 时激活 PAT_EXPIRED，与未找到/已撤销区分。"""

    async def _expired(_self, _token):
        return None, "expired"

    monkeypatch.setattr(pat_module.PATStorage, "verify", _expired)
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(user=Depends(api_deps.get_current_user_pat_or_jwt)):
        return {"sub": user.sub}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/probe", headers={"Authorization": "Bearer lc_pat_old"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "pat_expired"


async def test_pat_touch_last_used_throttled_per_pat_id(monkeypatch):
    record = _pat_record(["sandbox:execute"])
    touched: list[str] = []

    async def _verify(_self, _token):
        return record, None

    async def _touch(_self, pat_id):
        touched.append(pat_id)

    monkeypatch.setattr(pat_module.PATStorage, "verify", _verify)
    monkeypatch.setattr(pat_module.PATStorage, "touch_last_used", _touch)
    monkeypatch.setattr(
        api_deps,
        "_load_user_payload",
        lambda user_id: _async_return(
            api_deps.TokenPayload(
                sub="u1", username="tester", roles=["user"], permissions=["sandbox:execute"]
            )
        ),
    )
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(user=Depends(api_deps.get_current_user_pat_or_jwt)):
        return {"sub": user.sub}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(2):
            resp = await client.get("/probe", headers={"Authorization": "Bearer lc_pat_good"})
            assert resp.status_code == 200

    # 让 fire-and-forget 任务有机会执行
    for _ in range(10):
        await asyncio.sleep(0)

    assert touched == ["p1"]


def _async_return(value):
    fut = asyncio.get_event_loop().create_future()
    fut.set_result(value)
    return fut

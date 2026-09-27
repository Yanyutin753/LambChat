"""sandbox fs 只读端点测试：cwd 权威解析、属主校验、dispatch 参数拼装与结果透传。"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import sandbox as sandbox_route


def _fake_user():
    from src.kernel.schemas.user import TokenPayload

    return TokenPayload(sub="u1", username="t", roles=["user"], permissions=["sandbox:execute"])


def _bound_agent_options(machine_id="m1") -> dict:
    """合法绑定：sandbox_workspace JSON + 机器一致（selected_workspace_id 全条件）。"""
    workspace_id = "local-" + "a1b2c3d4" * 4
    return {
        "sandbox_workspace": json.dumps(
            {"id": workspace_id, "machineId": machine_id, "path": "/Users/t/proj"}
        ),
        "sandbox_machine_id": machine_id,
    }


def _fake_session(user_id="u1", agent_options=None) -> SimpleNamespace:
    metadata = {"conversation_config": {"agent_options": agent_options or {}}}
    return SimpleNamespace(user_id=user_id, metadata=metadata)


def _fs_app(monkeypatch, session, dispatched: list, dispatch_result=None):
    """组装 fs 端点测试 app：JWT 通道 + SessionManager/dispatch 打桩。

    dispatched 收集 (op, payload, machine_id)；dispatch_result 是 daemon 的
    done 载荷（默认 fs_ls 的 entries 结果）。
    """
    from src.infra.session import manager as session_manager_module

    class _FakeManager:
        async def get_session(self, session_id):
            return session

    monkeypatch.setattr(session_manager_module, "SessionManager", _FakeManager)

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        dispatched.append(
            {"user_id": user_id, "op": op, "payload": payload, "machine_id": machine_id}
        )
        return (
            dispatch_result
            if dispatch_result is not None
            else {
                "stage": "done",
                "status": "ok",
                "result": {"entries": [{"path": "a.txt", "is_dir": False}]},
            }
        )

    monkeypatch.setattr(sandbox_route, "dispatch_local_call", fake_dispatch)

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_fs_list_defaults_to_session_workspace(monkeypatch):
    """未绑定目录的会话：cwd=/workspace/{sid}、path 归一 "."、machine 缺省解析。"""
    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(agent_options={}), dispatched) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp.status_code == 200
    assert resp.json()["entries"] == [{"path": "a.txt", "is_dir": False}]
    assert len(dispatched) == 1
    call = dispatched[0]
    assert call["op"] == "fs_ls"
    assert call["payload"] == {"cwd": "/workspace/sess-1", "path": "."}
    assert call["machine_id"] is None


async def test_fs_list_uses_selected_workspace_binding(monkeypatch):
    """有绑定的会话：cwd=/workspace/.selected/{id}，会话级机器透传给 dispatch。"""
    dispatched: list = []
    async with _fs_app(
        monkeypatch, _fake_session(agent_options=_bound_agent_options("m9")), dispatched
    ) as client:
        resp = await client.get(
            "/api/sandbox/fs/list", params={"session_id": "sess-1", "path": "sub/dir"}
        )
    assert resp.status_code == 200
    call = dispatched[0]
    assert call["payload"]["cwd"] == "/workspace/.selected/local-" + "a1b2c3d4" * 4
    assert call["payload"]["path"] == "sub/dir"
    assert call["machine_id"] == "m9"


async def test_fs_list_rejects_foreign_session(monkeypatch):
    """属主校验：别人的会话 403，且不下发任何 fs op。"""
    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(user_id="someone-else"), dispatched) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "session_access_denied"
    assert dispatched == []


async def test_fs_list_rejects_unknown_session(monkeypatch):
    """会话不存在：404 session_not_found。"""

    class _NoneManager:
        async def get_session(self, session_id):
            return None

    from src.infra.session import manager as session_manager_module

    monkeypatch.setattr(session_manager_module, "SessionManager", _NoneManager)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox_route.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "ghost"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "session_not_found"


async def test_fs_list_rejects_injection_shaped_session_id(monkeypatch):
    """session_id 形态先挡一层：路径注入形态（含 /、..）在查库前即 404。"""
    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(), dispatched) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "../etc"})
    assert resp.status_code == 404
    assert dispatched == []


async def test_fs_list_passes_through_daemon_file_error(monkeypatch):
    """daemon 文件级错误（path_not_found）：200 + error 原样透传（与 daemon 契约一致）。"""
    dispatched: list = []
    async with _fs_app(
        monkeypatch,
        _fake_session(),
        dispatched,
        dispatch_result={"stage": "done", "status": "ok", "result": {"error": "path_not_found"}},
    ) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "s", "path": "gone"})
    assert resp.status_code == 200
    assert resp.json() == {"error": "path_not_found"}


async def test_fs_read_passes_paging_params(monkeypatch):
    """fs_read：offset/limit 行分页参数原样拼装，返回文本预览结果。"""
    dispatched: list = []
    async with _fs_app(
        monkeypatch,
        _fake_session(),
        dispatched,
        dispatch_result={
            "stage": "done",
            "status": "ok",
            "result": {
                "encoding": "utf-8",
                "content": "line1\nline2",
                "total_lines": 2,
                "start_line": 1,
                "end_line": 2,
                "next_offset": None,
            },
        },
    ) as client:
        resp = await client.get(
            "/api/sandbox/fs/read",
            params={"session_id": "sess-1", "path": "notes.md", "offset": 0, "limit": 200},
        )
    assert resp.status_code == 200
    assert resp.json()["encoding"] == "utf-8"
    call = dispatched[0]
    assert call["op"] == "fs_read"
    assert call["payload"]["path"] == "notes.md"
    assert call["payload"]["offset"] == 0
    assert call["payload"]["limit"] == 200


async def test_fs_read_rejects_over_limit(monkeypatch):
    """limit 超上限：422（FastAPI Query 校验），不打 dispatch。"""
    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(), dispatched) as client:
        resp = await client.get(
            "/api/sandbox/fs/read",
            params={"session_id": "s", "path": "a", "limit": sandbox_route._FS_READ_MAX_LINES + 1},
        )
    assert resp.status_code == 422
    assert dispatched == []


async def test_fs_list_rejects_oversized_path(monkeypatch):
    """相对路径超长：422 validation_error（daemon 逃逸检查之外的浅层防线）。"""
    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(), dispatched) as client:
        resp = await client.get(
            "/api/sandbox/fs/list",
            params={"session_id": "s", "path": "x" * (sandbox_route._FS_PATH_MAX + 1)},
        )
    assert resp.status_code == 422
    assert dispatched == []


@pytest.mark.parametrize("missing", ["machine", "id_format", "json_shape"])
async def test_fs_list_falls_back_on_invalid_binding(monkeypatch, missing):
    """坏绑定（机器不一致/id 形态非法/非 JSON）：selected_workspace_id 判 None，
    回落默认工作区——与 search_agent 的分支语义一致，不因脏数据 500。"""
    options: dict = {}
    workspace_id = "local-" + "a1b2c3d4" * 4
    if missing == "machine":  # machineId 与 sandbox_machine_id 不一致
        options = {
            "sandbox_workspace": json.dumps(
                {"id": workspace_id, "machineId": "m-other", "path": "/p"}
            ),
            "sandbox_machine_id": "m1",
        }
    elif missing == "id_format":
        options = {
            "sandbox_workspace": json.dumps({"id": "../../etc", "machineId": "m1", "path": "/p"}),
            "sandbox_machine_id": "m1",
        }
    else:  # 非 JSON 字符串
        options = {"sandbox_workspace": "not-json", "sandbox_machine_id": "m1"}

    dispatched: list = []
    async with _fs_app(monkeypatch, _fake_session(agent_options=options), dispatched) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp.status_code == 200
    assert dispatched[0]["payload"]["cwd"] == "/workspace/sess-1"

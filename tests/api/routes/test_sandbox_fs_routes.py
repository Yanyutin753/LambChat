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
    # 前端 useAgentOptions 总会显式写 sandbox 值；缺省回落全局 SANDBOX_PLATFORM
    # （出厂 daytona=云端）的分支由专项用例锁定
    options = {"sandbox": "local"}
    if agent_options is not None:
        options.update(agent_options)
    metadata = {"conversation_config": {"agent_options": options}}
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


async def test_fs_list_rejects_cloud_session(monkeypatch):
    """云端会话（sandbox=cloud）拒绝：其工作区在 E2B，转发本地 daemon 只会
    误建空目录、展示无关文件——409 sandbox_session_not_local 且不下发。"""
    dispatched: list = []
    async with _fs_app(
        monkeypatch, _fake_session(agent_options={"sandbox": "cloud"}), dispatched
    ) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "sandbox_session_not_local"
    assert dispatched == []


async def test_fs_list_platform_falls_back_to_global_default(monkeypatch):
    """会话未显式选平台时回落全局 SANDBOX_PLATFORM（与 _resolve_sandbox_platform
    同规则）：默认为 local 时放行；daytona/cloud 等非 local 平台一律拒绝。"""
    dispatched: list = []

    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_PLATFORM", "local")
    async with _fs_app(
        monkeypatch, _fake_session(agent_options={"sandbox": None}), dispatched
    ) as client:
        resp = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp.status_code == 200
    assert len(dispatched) == 1

    monkeypatch.setattr(sandbox_route.settings, "SANDBOX_PLATFORM", "daytona")
    async with _fs_app(
        monkeypatch, _fake_session(agent_options={"sandbox": None}), dispatched
    ) as client:
        resp2 = await client.get("/api/sandbox/fs/list", params={"session_id": "sess-1"})
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["code"] == "sandbox_session_not_local"
    assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# 云端电脑浏览端点（fs/cloud/*）
# ---------------------------------------------------------------------------


def _cloud_app(monkeypatch, session, manager, als_result=None, aread_result=None):
    """云端端点测试 app:SessionManager + 沙箱管理器/backend 打桩。"""
    from src.infra.session import manager as session_manager_module
    from src.infra.sandbox import session_manager as sandbox_module
    from src.api.routes import sandbox as route_module

    class _FakeSessionManager:
        async def get_session(self, sid):
            return session

    monkeypatch.setattr(session_manager_module, "SessionManager", _FakeSessionManager)

    calls: dict = {"get_or_create": [], "cloud_status": []}

    class _FakeScopedBackend:
        async def als(self, path):
            calls.setdefault("als", []).append(path)
            return (
                als_result
                if als_result is not None
                else {
                    "entries": [
                        {
                            "path": f"/home/user/sessions/sess-1/{path.rstrip('/').lstrip('./') or '.'}/sub",
                            "is_dir": True,
                        },
                        {
                            "path": f"/home/user/sessions/sess-1/{path.rstrip('/').lstrip('./') or '.'}/hello.txt"
                        },
                    ]
                }
            )

        async def aread(self, path, offset=0, limit=500):
            calls.setdefault("aread", []).append((path, offset, limit))
            return (
                aread_result
                if aread_result is not None
                else {
                    "file_data": {"content": "cloud text", "encoding": "utf-8"},
                    "total_lines": 1,
                    "start_line": 1,
                    "end_line": 1,
                    "next_offset": None,
                }
            )

    class _FakeManager:
        async def get_or_create(self, session_id, user_id, *, create=True):
            calls["get_or_create"].append({"session_id": session_id, "create": create})
            if isinstance(manager, Exception):
                raise manager
            return _FakeScopedBackend(), "/home/user/sessions/sess-1"

        async def cloud_status(self, user_id):
            calls["cloud_status"].append(user_id)
            return manager if isinstance(manager, dict) else {"platform": "e2b", "state": "paused"}

    monkeypatch.setattr(sandbox_module, "get_session_sandbox_manager", lambda: _FakeManager())
    monkeypatch.setattr(route_module, "__sandbox_manager__", _FakeManager(), raising=False)
    # 路由内 from ... import get_session_sandbox_manager 走的是函数内导入,
    # 打桩点在源模块命名空间即可生效

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(route_module.router, prefix="/api/sandbox", tags=["Sandbox"])
    app.dependency_overrides[api_deps.get_current_user_pat_or_jwt] = _fake_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver"), calls


async def test_cloud_list_passes_create_false_and_normalizes_paths(monkeypatch):
    """云端列表：只连不建（create=False）+ 条目路径归一为本地端点同构相对串。"""
    client, calls = _cloud_app(monkeypatch, _fake_session(agent_options={"sandbox": "cloud"}), None)
    async with client as c:
        resp = await c.get("/api/sandbox/fs/cloud/list", params={"session_id": "sess-1"})
    assert resp.status_code == 200
    assert calls["get_or_create"] == [{"session_id": "sess-1", "create": False}]
    entries = resp.json()["entries"]
    assert {e["path"] for e in entries} == {"./sub", "./hello.txt"}
    assert next(e for e in entries if e["path"] == "./sub")["is_dir"] is True


async def test_cloud_list_not_created_and_recycled_map_to_codes(monkeypatch):
    """PeekError 语义映射：无绑定 → 404 not_created；沙箱被回收 → 410 recycled。"""
    from src.infra.sandbox.session_manager import SandboxPeekError

    client, _ = _cloud_app(monkeypatch, _fake_session(), SandboxPeekError("not_created"))
    async with client as c:
        resp = await c.get("/api/sandbox/fs/cloud/list", params={"session_id": "sess-1"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "sandbox_cloud_not_created"

    client2, _ = _cloud_app(monkeypatch, _fake_session(), SandboxPeekError("recycled"))
    async with client2 as c:
        resp2 = await c.get("/api/sandbox/fs/cloud/list", params={"session_id": "sess-1"})
    assert resp2.status_code == 410
    assert resp2.json()["detail"]["code"] == "sandbox_cloud_recycled"


async def test_cloud_read_returns_filedata_contract(monkeypatch):
    """云端读取：FileData{content, encoding} 直通,与本地端点契约对齐。"""
    client, calls = _cloud_app(monkeypatch, _fake_session(), None)
    async with client as c:
        resp = await c.get(
            "/api/sandbox/fs/cloud/read",
            params={"session_id": "sess-1", "path": "./hello.txt", "offset": 0, "limit": 200},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["encoding"] == "utf-8" and body["content"] == "cloud text"
    assert calls["aread"][0] == ("hello.txt", 0, 200)


async def test_cloud_status_zero_side_effect(monkeypatch):
    """状态速览只读绑定（cloud_status），不触发 get_or_create。"""
    client, calls = _cloud_app(
        monkeypatch, _fake_session(), {"platform": "daytona", "state": "running"}
    )
    async with client as c:
        resp = await c.get("/api/sandbox/fs/cloud/status", params={"session_id": "sess-1"})
    assert resp.status_code == 200
    assert resp.json() == {"platform": "daytona", "state": "running"}
    assert calls["get_or_create"] == []


async def test_cloud_endpoints_reject_foreign_session(monkeypatch):
    """属主校验同样覆盖云端端点。"""
    client, _ = _cloud_app(monkeypatch, _fake_session(user_id="other"), None)
    async with client as c:
        resp = await c.get("/api/sandbox/fs/cloud/list", params={"session_id": "sess-1"})
    assert resp.status_code == 403

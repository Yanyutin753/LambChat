# 本地沙箱 M1（服务端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通服务端→本机执行的中继管道：PAT 鉴权、daemon SSE 通道、Redis 跨进程路由、LocalSandboxBackend、会话级沙箱选择（mock daemon 全测，不含真实 daemon）。

**Architecture:** 服务端 agent 不动；新增 `/api/sandbox/channel`（SSE 下发）+ `/api/sandbox/results`（POST 回传）+ `/api/auth/pat`（机器令牌）。工具调用经 Redis list → 持连接进程转发 → daemon；结果经 Redis key 回到调用方。`LocalSandboxBackend(BaseSandbox)` 只实现 `execute()`，文件操作由 deepagents 基类自动继承。

**Tech Stack:** FastAPI（StreamingResponse SSE）、redis.asyncio（`src/infra/storage/redis.py::get_redis_client`）、motor（ModelStorage 惯用法）、deepagents `BaseSandbox`。

**Spec:** `docs/superpowers/specs/2026-09-01-local-sandbox-design.md`（§3 服务端新增；§3.5 HITL 确认与 §12 后续项不在本计划，见"M2 留存"）

## Global Constraints

- 路由层禁止 `raise HTTPException`，一律 `AppError(ErrorCode.XXX, args={...})`（AGENTS.md）。
- 新增 ErrorCode 必须同步 `scripts/sync_error_locales.py` 的 TRANSLATIONS 并跑脚本，五语 i18n CI 强制（`frontend/src/i18n/__tests__/backendErrorCodeCoverage.test.ts`）。
- Python 依赖只用 `uv`；本计划**零新增第三方依赖**（redis/motor/pyjwt 均已有或不需要——PAT 用 `secrets` + `hashlib`，不签名）。
- 测试镜像 `src/` 结构；pytest asyncio_mode=auto；无全局 mongo/redis fixture，测试自建 `FastAPI()` + `dependency_overrides` + monkeypatch（参照 `tests/api/test_team_routes.py:81-109`）。
- 提交信息：Conventional Commits + 中文摘要。
- 实现与 spec 的两处有意偏差：① Redis 转发用 `lpop` 50ms 轮询替代 BLPOP（语义相同、无 redis 也可测、延迟 <100ms 满足 spec §11）；② ACK/结果两阶段经同一个 POST 端点的 `stage` 字段实现。

## File Structure

```
src/kernel/errors.py                        # +6 错误码
src/kernel/config/base.py                   # +2 配置项
src/infra/auth/pat.py                       # 新：PATStorage
src/api/deps.py                             # +get_current_user_pat_or_jwt / require_pat_scope
src/api/routes/auth/pat.py                  # 新：PAT CRUD 路由
src/infra/sandbox/relay/__init__.py         # 新：relay 包
src/infra/sandbox/relay/registry.py         # 新：daemon 在线注册表（Redis）
src/infra/sandbox/relay/dispatch.py         # 新：工具调用下发/等结果
src/api/routes/sandbox.py                   # 新：channel(SSE)/results/status 路由
src/infra/backend/local.py                  # 新：LocalSandboxBackend
src/agents/search_agent/nodes.py            # 改：agent_options.sandbox 路由（纯函数 + 分支）
src/api/main.py                             # 改：路由注册 + PAT 索引初始化
.env.example                                # +2 配置项
scripts/sync_error_locales.py               # 改：TRANSLATIONS +6
frontend/src/i18n/locales/{zh,en,ja,ko,ru}.json  # 脚本生成
tests/infra/auth/test_pat.py                # 新
tests/api/routes/test_pat_routes.py         # 新
tests/api/test_deps_pat.py                  # 新
tests/infra/sandbox/relay/test_registry.py  # 新
tests/infra/sandbox/relay/test_dispatch.py  # 新
tests/api/routes/test_sandbox_routes.py     # 新
tests/infra/backend/test_local_backend.py   # 新
tests/agents/search_agent/test_sandbox_routing.py  # 新
```

---

### Task 1: ErrorCode 六个新错误码 + 五语 i18n

**Files:**
- Modify: `src/kernel/errors.py`（在认证类错误附近插入）
- Modify: `scripts/sync_error_locales.py`（TRANSLATIONS 表）
- Generate: `frontend/src/i18n/locales/*.json`

**Interfaces:**
- Produces: `ErrorCode.PAT_NOT_FOUND`、`PAT_SCOPE_DENIED`、`PAT_EXPIRED`、`DAEMON_OFFLINE`、`SANDBOX_TIMEOUT`、`SANDBOX_PAYLOAD_TOO_LARGE`，后续任务直接引用。

- [ ] **Step 1: 在 `src/kernel/errors.py` 追加成员**（格式 = `(snake_case, http_status, english)`，照 `USERNAME_EXISTS = ("username_exists", 409, "Username '{{user}}' already exists")` 的样子）

```python
    PAT_NOT_FOUND = ("pat_not_found", 401, "Personal access token not found or revoked")
    PAT_EXPIRED = ("pat_expired", 401, "Personal access token expired")
    PAT_SCOPE_DENIED = ("pat_scope_denied", 403, "Token missing required scope '{{scope}}'")
    DAEMON_OFFLINE = ("daemon_offline", 409, "Local sandbox daemon is offline")
    SANDBOX_TIMEOUT = ("sandbox_timeout", 504, "Local sandbox call timed out after {{seconds}}s")
    SANDBOX_PAYLOAD_TOO_LARGE = ("sandbox_payload_too_large", 413, "Local sandbox payload exceeds limit")
```

- [ ] **Step 2: 在 `scripts/sync_error_locales.py` 的 `TRANSLATIONS` 加四语条目**（key 是 camelCase 码名）

```python
    "patNotFound": {
        "zh": "个人访问令牌不存在或已撤销",
        "ja": "パーソナルアクセストークンが見つからないか失効しています",
        "ko": "개인 액세스 토큰이 없거나 폐기되었습니다",
        "ru": "Персональный токен доступа не найден или отозван",
    },
    "patExpired": {
        "zh": "个人访问令牌已过期",
        "ja": "パーソナルアクセストークンの有効期限が切れました",
        "ko": "개인 액세스 토큰이 만료되었습니다",
        "ru": "Срок действия персонального токена истёк",
    },
    "patScopeDenied": {
        "zh": "令牌缺少所需权限 {{scope}}",
        "ja": "トークンに必要なスコープ {{scope}} がありません",
        "ko": "토큰에 필요한 스코프 {{scope}}가 없습니다",
        "ru": "У токена нет требуемой области {{scope}}",
    },
    "daemonOffline": {
        "zh": "本地沙箱守护进程离线",
        "ja": "ローカルサンドボックスデーモンはオフラインです",
        "ko": "로컬 샌드박스 데몬이 오프라인입니다",
        "ru": "Локальный sandbox-демон не подключён",
    },
    "sandboxTimeout": {
        "zh": "本地沙箱调用超时（{{seconds}} 秒）",
        "ja": "ローカルサンドボックス呼び出しがタイムアウトしました（{{seconds}}秒）",
        "ko": "로컬 샌드박스 호출 시간 초과({{seconds}}초)",
        "ru": "Превышено время ожидания локального sandbox ({{seconds}} с)",
    },
    "sandboxPayloadTooLarge": {
        "zh": "本地沙箱载荷超限",
        "ja": "ローカルサンドボックスのペイロードが大きすぎます",
        "ko": "로컬 샌드박스 페이로드가 너무 큽니다",
        "ru": "Полезная нагрузка локального sandbox слишком велика",
    },
```

- [ ] **Step 3: 跑同步脚本并验证五语覆盖测试**

Run: `uv run python scripts/sync_error_locales.py && cd frontend && pnpm test -- backendErrorCodeCoverage`
Expected: 脚本无报错；vitest 该文件 PASS。

- [ ] **Step 4: 后端全量 lint**

Run: `make lint`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/kernel/errors.py scripts/sync_error_locales.py frontend/src/i18n/locales
git commit -m "feat(sandbox): 本地沙箱/PAT 错误码与五语翻译"
```

---

### Task 2: PATStorage（infra 层）

**Files:**
- Create: `src/infra/auth/pat.py`
- Test: `tests/infra/auth/test_pat.py`

**Interfaces:**
- Produces（后续任务按此引用）:

```python
PAT_PREFIX = "lc_pat_"

class PATRecord(BaseModel):
    pat_id: str          # uuid4().hex
    user_id: str
    name: str
    scopes: list[str]    # v1 只会出现 ["sandbox:execute"]
    token_hash: str      # sha256 hex
    prefix: str          # token 前 12 字符，用于列表展示
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked: bool

class PATStorage:
    async def create(self, *, user_id: str, name: str, scopes: list[str],
                     expires_at: datetime | None = None) -> tuple[str, PATRecord]
        # 返回 (明文 token, record)；明文 token = PAT_PREFIX + secrets.token_urlsafe(32)
    async def verify(self, token: str) -> PATRecord          # 不存在/撤销/过期 -> None
    async def list_for_user(self, user_id: str) -> list[PATRecord]  # revoked=False，按 created_at 倒序
    async def revoke(self, *, user_id: str, pat_id: str) -> bool
    async def touch_last_used(self, pat_id: str) -> None     # update last_used_at=utcnow
```

- [ ] **Step 1: 写失败测试**（`tests/infra/auth/test_pat.py`；FakeCollection 模仿 motor 的 `insert_one/find_one/update_one/find`，照 `tests/infra/test_role_storage_indexes.py` 的 fake 模式）

```python
"""PAT 存储层测试：创建/校验/撤销/过期/范围。"""
from datetime import datetime, timedelta, timezone

import pytest

from src.infra.auth.pat import PATStorage, PAT_PREFIX


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    async def find_one(self, query: dict) -> dict | None:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    async def find(self, query: dict) -> "_FakeCursor":
        return _FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])

    async def update_one(self, query: dict, update: dict) -> None:
        doc = await self.find_one(query)
        if doc:
            doc.update(update.get("$set", {}))


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key: str, direction: int) -> "_FakeCursor":
        self._docs = sorted(self._docs, key=lambda d: d.get(key), reverse=direction == -1)
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        return self._docs


@pytest.fixture
def storage(monkeypatch) -> PATStorage:
    coll = _FakeCollection()
    st = PATStorage()
    monkeypatch.setattr(st, "_get_collection", lambda: coll)
    return st


async def test_create_returns_token_and_verifies(storage):
    token, record = await storage.create(user_id="u1", name="桌面端", scopes=["sandbox:execute"])
    assert token.startswith(PAT_PREFIX) and len(token) > 40
    verified = await storage.verify(token)
    assert verified is not None and verified.user_id == "u1"
    assert verified.scopes == ["sandbox:execute"]


async def test_verify_rejects_unknown_token(storage):
    assert await storage.verify(f"{PAT_PREFIX}nope") is None


async def test_revoke_makes_token_invalid(storage):
    token, record = await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    assert await storage.revoke(user_id="u1", pat_id=record.pat_id) is True
    assert await storage.verify(token) is None


async def test_expired_token_rejected(storage):
    token, _ = await storage.create(
        user_id="u1", name="a", scopes=["sandbox:execute"],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    assert await storage.verify(token) is None


async def test_list_for_user_excludes_revoked(storage):
    await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    _, rec2 = await storage.create(user_id="u1", name="b", scopes=["sandbox:execute"])
    await storage.revoke(user_id="u1", pat_id=rec2.pat_id)
    listed = await storage.list_for_user("u1")
    assert [p.name for p in listed] == ["a"]


async def test_touch_last_used(storage):
    token, record = await storage.create(user_id="u1", name="a", scopes=["sandbox:execute"])
    await storage.touch_last_used(record.pat_id)
    verified = await storage.verify(token)
    assert verified.last_used_at is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/auth/test_pat.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'src.infra.auth.pat'`。

- [ ] **Step 3: 实现 `src/infra/auth/pat.py`**（ModelStorage 惯用法：懒加载 collection + 唯一索引）

```python
"""PAT 个人访问令牌存储：明文只在创建时返回，库中仅存 SHA-256 哈希。"""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from src.kernel.config import settings

PAT_PREFIX = "lc_pat_"
_COLL_PATS = "pats"


class PATRecord(BaseModel):
    pat_id: str
    user_id: str
    name: str
    scopes: list[str]
    token_hash: str
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked: bool = False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PATStorage:
    def __init__(self) -> None:
        self._collection: Optional[Any] = None

    def _get_collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[_COLL_PATS]
        return self._collection

    async def ensure_indexes(self) -> None:
        coll = self._get_collection()
        await coll.create_index("pat_id", unique=True)
        await coll.create_index("token_hash", unique=True)
        await coll.create_index("user_id")

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str],
        expires_at: Optional[datetime] = None,
    ) -> tuple[str, PATRecord]:
        token = f"{PAT_PREFIX}{secrets.token_urlsafe(32)}"
        record = PATRecord(
            pat_id=uuid.uuid4().hex,
            user_id=user_id,
            name=name,
            scopes=scopes,
            token_hash=_hash_token(token),
            prefix=token[:12],
            created_at=_utcnow(),
            expires_at=expires_at,
        )
        await self._get_collection().insert_one(record.model_dump())
        return token, record

    async def verify(self, token: str) -> Optional[PATRecord]:
        doc = await self._get_collection().find_one({"token_hash": _hash_token(token)})
        if doc is None or doc.get("revoked"):
            return None
        expires_at = doc.get("expires_at")
        if expires_at is not None and expires_at <= _utcnow():
            return None
        return PATRecord(**doc)

    async def list_for_user(self, user_id: str) -> list[PATRecord]:
        cursor = self._get_collection().find({"user_id": user_id, "revoked": False})
        docs = await cursor.sort("created_at", -1).to_list(None)
        return [PATRecord(**d) for d in docs]

    async def revoke(self, *, user_id: str, pat_id: str) -> bool:
        doc = await self._get_collection().find_one({"pat_id": pat_id, "user_id": user_id})
        if doc is None:
            return False
        await self._get_collection().update_one(
            {"pat_id": pat_id}, {"$set": {"revoked": True}}
        )
        return True

    async def touch_last_used(self, pat_id: str) -> None:
        await self._get_collection().update_one(
            {"pat_id": pat_id}, {"$set": {"last_used_at": _utcnow()}}
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/infra/auth/test_pat.py -v`
Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add src/infra/auth/pat.py tests/infra/auth/test_pat.py
git commit -m "feat(sandbox): PAT 个人访问令牌存储"
```

---

### Task 3: PAT 路由（CRUD）

**Files:**
- Create: `src/api/routes/auth/pat.py`
- Modify: `src/api/main.py`（import 区 :23-54 按字母序 + include 区 :831-885 追加一行）
- Test: `tests/api/routes/test_pat_routes.py`

**Interfaces:**
- Consumes: `PATStorage`（Task 2）、`get_current_user_required`（`src/api/deps.py:121`）、`ErrorCode.PAT_NOT_FOUND`（Task 1）
- Produces: `POST /api/auth/pat`（body `{name, scopes, expires_at?}` → `{token, pat_id}`，**token 只此一次**）、`GET /api/auth/pat`（元数据列表，不含 token）、`DELETE /api/auth/pat/{pat_id}`

- [ ] **Step 1: 写失败测试**（`tests/api/routes/test_pat_routes.py`；模式照 `tests/api/test_team_routes.py:81-109`）

```python
"""PAT 路由测试：创建返回一次明文、列表不含哈希、撤销。"""
from datetime import datetime

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
        from tests.infra.auth.test_pat import _FakeCollection

        from src.infra.auth.pat import PATStorage

        self._inner = PATStorage()
        self._inner._get_collection = lambda: _FakeCollection()  # noqa: SLF001

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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/routes/test_pat_routes.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `src/api/routes/auth/pat.py`**（照 `envvar.py` 结构：router → storage 依赖 → 校验 → 静态路由在前动态在后）

```python
"""PAT 个人访问令牌管理路由。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required
from src.infra.auth.pat import PATStorage
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

router = APIRouter()

_ALLOWED_SCOPES = {"sandbox:execute"}


def get_pat_storage() -> PATStorage:
    return PATStorage()


class PATCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class PATCreateResponse(BaseModel):
    token: str
    pat_id: str


class PATItem(BaseModel):
    pat_id: str
    name: str
    scopes: list[str]
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class PATListResponse(BaseModel):
    pats: list[PATItem]


@router.post("", response_model=PATCreateResponse)
async def create_pat(
    body: PATCreateRequest,
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    for scope in body.scopes:
        if scope not in _ALLOWED_SCOPES:
            raise AppError(ErrorCode.VALIDATION_ERROR, args={"detail": f"unknown scope: {scope}"})
    token, record = await storage.create(
        user_id=user.sub, name=body.name, scopes=body.scopes, expires_at=body.expires_at
    )
    return PATCreateResponse(token=token, pat_id=record.pat_id)


@router.get("", response_model=PATListResponse)
async def list_pats(
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    records = await storage.list_for_user(user.sub)
    return PATListResponse(
        pats=[
            PATItem(
                pat_id=r.pat_id, name=r.name, scopes=r.scopes, prefix=r.prefix,
                created_at=r.created_at, expires_at=r.expires_at, last_used_at=r.last_used_at,
            )
            for r in records
        ]
    )


@router.delete("/{pat_id}")
async def revoke_pat(
    pat_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    ok = await storage.revoke(user_id=user.sub, pat_id=pat_id)
    if not ok:
        raise AppError(ErrorCode.PAT_NOT_FOUND)
    return {"status": "ok"}
```

- [ ] **Step 4: 注册路由**（`src/api/main.py`：import 括号区（:23-54，auth 相关已聚合在 `from src.api.routes.auth import ...`，若无则在 routes 的 import 中补 `pat`）；include 区 :855-885 追加）

```python
    app.include_router(auth_pat.router, prefix="/api/auth/pat", tags=["Auth"])
```

（import 形式与相邻行保持一致，例如 `from src.api.routes.auth import pat as auth_pat`。）

同时在 `_startup_index_initializers()`（main.py:471-491 列表尾部）追加 PAT 索引初始化闭包：

```python
    def _init_pat_storage():
        from src.infra.auth.pat import PATStorage

        return PATStorage().ensure_indexes()
```

- [ ] **Step 5: 跑测试 + 中间件守门测试**

Run: `uv run pytest tests/api/routes/test_pat_routes.py tests/api/test_auth_middleware_public_paths.py tests/api/test_no_http_exception.py -v`
Expected: 全部 PASS（新路由无 HTTPException、不在公开白名单）。

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/auth/pat.py src/api/main.py tests/api/routes/test_pat_routes.py
git commit -m "feat(sandbox): PAT 创建/列表/撤销路由"
```

---

### Task 4: PAT/JWT 双通道鉴权依赖

**Files:**
- Modify: `src/api/deps.py`
- Test: `tests/api/test_deps_pat.py`

**Interfaces:**
- Consumes: `PATStorage.verify`（Task 2）、`PAT_PREFIX`、现有用户/角色装载逻辑（`deps.py:121-178` 内 `UserStorage/RoleStorage` 流程）
- Produces:

```python
async def get_current_user_pat_or_jwt(request, credentials=Depends(security)) -> TokenPayload
    # lc_pat_ 前缀 -> PATStorage.verify -> 组 TokenPayload(sub=user_id, username=..., roles/permissions 从 DB 装载)
    # 其余 -> 复用现有 JWT 流程
def require_pat_scope(scope: str) -> 依赖  # 在 PAT 路径上校验 scope，JWT 路径放行（权限走角色）
```

- [ ] **Step 1: 写失败测试**（`tests/api/test_deps_pat.py`；PAT 分支 mock `PATStorage.verify` + 用户装载；scope 缺失断言 `PAT_SCOPE_DENIED`）

```python
"""PAT/JWT 双通道鉴权依赖测试。"""
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.error_handlers import register_error_handlers
from src.infra.auth import pat as pat_module
from src.infra.auth.pat import PATRecord
from src.kernel.errors import AppError, ErrorCode


def _pat_record(scopes: list[str]) -> PATRecord:
    from datetime import datetime, timezone

    return PATRecord(
        pat_id="p1", user_id="u1", name="t", scopes=scopes, token_hash="h" * 64,
        prefix="lc_pat_abc", created_at=datetime.now(timezone.utc),
    )


async def test_pat_token_builds_payload(monkeypatch):
    record = _pat_record(["sandbox:execute"])
    monkeypatch.setattr(pat_module.PATStorage, "verify", lambda self, token: _async_return(record))
    monkeypatch.setattr(api_deps, "_load_user_payload", lambda user_id: _async_return(
        api_deps.TokenPayload(sub="u1", username="tester", roles=["user"], permissions=["sandbox:execute"])
    ))
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
    monkeypatch.setattr(pat_module.PATStorage, "verify", lambda self, token: _async_return(record))
    monkeypatch.setattr(api_deps, "_load_user_payload", lambda user_id: _async_return(
        api_deps.TokenPayload(sub="u1", username="tester", roles=["user"], permissions=[])
    ))
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
        return None

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


def _async_return(value):
    import asyncio

    fut = asyncio.get_event_loop().create_future()
    fut.set_result(value)
    return fut
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/test_deps_pat.py -v`
Expected: FAIL，`_load_user_payload` / `get_current_user_pat_or_jwt` 不存在。

- [ ] **Step 3: 实现**（`src/api/deps.py`：先从 `get_current_user_required`（:121-178）中把"按 user_id 拉用户+角色并组 TokenPayload"的段落提炼为模块级 `_load_user_payload(user_id) -> TokenPayload`——原函数改为调用它，行为不变；然后追加）

```python
async def get_current_user_pat_or_jwt(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenPayload:
    """JWT 或 PAT 双通道：lc_pat_ 前缀走 PATStorage，其余走 JWT。"""
    if credentials is None or not credentials.credentials:
        raise AppError(ErrorCode.AUTH_MISSING)
    token = credentials.credentials
    if token.startswith(PAT_PREFIX):
        from src.infra.auth.pat import PATStorage

        record = await PATStorage().verify(token)
        if record is None:
            raise AppError(ErrorCode.PAT_NOT_FOUND)
        payload = await _load_user_payload(record.user_id)
        request.state.pat_scopes = record.scopes
        return payload
    return await get_current_user_required(request=request, credentials=credentials)


def require_pat_scope(scope: str):
    """要求 PAT 具备指定 scope；JWT 路径不额外限制（权限由角色体系管）。"""

    async def _checker(
        request: Request,
        user: TokenPayload = Depends(get_current_user_pat_or_jwt),
    ) -> TokenPayload:
        if getattr(request.state, "pat_scopes", None) is not None:
            if scope not in request.state.pat_scopes:
                raise AppError(ErrorCode.PAT_SCOPE_DENIED, args={"scope": scope})
        return user

    return _checker
```

（PAT verify 命中后 `touch_last_used` 节流更新：以 `record.pat_id` 为键做进程内 5 分钟去重后 fire-and-forget。）

- [ ] **Step 4: 跑新旧鉴权测试**

Run: `uv run pytest tests/api/test_deps_pat.py tests/api -k "deps or auth" -v`
Expected: 新测试 PASS；既有鉴权测试不回归。

- [ ] **Step 5: Commit**

```bash
git add src/api/deps.py tests/api/test_deps_pat.py
git commit -m "feat(sandbox): PAT/JWT 双通道鉴权依赖与 scope 校验"
```

---

### Task 5: daemon 在线注册表（Redis）

**Files:**
- Create: `src/infra/sandbox/relay/__init__.py`（空）、`src/infra/sandbox/relay/registry.py`
- Test: `tests/infra/sandbox/relay/test_registry.py`

**Interfaces:**
- Consumes: `get_redis_client()`（`src/infra/storage/redis.py:73`）
- Produces:

```python
class SandboxClientRegistry:
    # key = "sandbox:clients:{user_id}"，hash {client_id: node_id}，整体 TTL 35s（心跳续期）
    # 同用户新连接 register 时先 delete 整个 key（后连踢前连，spec §3.2）
    async def register(self, user_id: str, client_id: str, node_id: str) -> None
    async def heartbeat(self, user_id: str, client_id: str, node_id: str) -> None
    async def unregister(self, user_id: str, client_id: str) -> None
    async def is_online(self, user_id: str) -> bool
    async def get_active(self, user_id: str) -> tuple[str, str] | None  # (client_id, node_id)
```

- [ ] **Step 1: 写失败测试**（FakeRedis 只实现用到的方法）

```python
"""daemon 注册表测试：注册/心跳/TTL/踢旧连/摘除。"""
import pytest

from src.infra.sandbox.relay.registry import SandboxClientRegistry


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}
        self.ttl: dict[str, int] = {}

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ttl.pop(key, None)

    async def hset(self, key: str, field: str, value: str) -> None:
        self.store.setdefault(key, {})[field] = value

    async def hdel(self, key: str, field: str) -> None:
        self.store.get(key, {}).pop(field, None)

    async def expire(self, key: str, seconds: int) -> None:
        self.ttl[key] = seconds

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.store.get(key, {}))


@pytest.fixture
def registry(monkeypatch) -> SandboxClientRegistry:
    fake = _FakeRedis()
    reg = SandboxClientRegistry()
    monkeypatch.setattr(reg, "_redis", lambda: fake)
    return reg


async def test_register_then_online(registry):
    await registry.register("u1", "c1", "node-a")
    assert await registry.is_online("u1") is True
    assert await registry.get_active("u1") == ("c1", "node-a")


async def test_new_connection_kicks_old(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.register("u1", "c2", "node-b")
    assert await registry.get_active("u1") == ("c2", "node-b")


async def test_heartbeat_extends_ttl(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.heartbeat("u1", "c1", "node-a")
    assert await registry.is_online("u1") is True


async def test_unregister_makes_offline(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.unregister("u1", "c1")
    assert await registry.is_online("u1") is False


async def test_unknown_user_offline(registry):
    assert await registry.is_online("nobody") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/sandbox/relay/test_registry.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `src/infra/sandbox/relay/registry.py`**

```python
"""daemon 连接注册表：Redis hash + TTL 心跳判活（spec §3.2）。同用户仅一个活跃连接。"""
from src.infra.storage.redis import get_redis_client

_TTL_SECONDS = 35


def _key(user_id: str) -> str:
    return f"sandbox:clients:{user_id}"


class SandboxClientRegistry:
    def _redis(self):
        return get_redis_client()

    async def register(self, user_id: str, client_id: str, node_id: str) -> None:
        redis = self._redis()
        await redis.delete(_key(user_id))  # 后连踢前连
        await redis.hset(_key(user_id), client_id, node_id)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def heartbeat(self, user_id: str, client_id: str, node_id: str) -> None:
        redis = self._redis()
        await redis.hset(_key(user_id), client_id, node_id)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def unregister(self, user_id: str, client_id: str) -> None:
        redis = self._redis()
        await redis.hdel(_key(user_id), client_id)
        if not await redis.hgetall(_key(user_id)):
            await redis.delete(_key(user_id))

    async def is_online(self, user_id: str) -> bool:
        return bool(await self._redis().exists(_key(user_id)))

    async def get_active(self, user_id: str) -> tuple[str, str] | None:
        fields = await self._redis().hgetall(_key(user_id))
        if not fields:
            return None
        client_id = next(iter(fields))
        return client_id, fields[client_id]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/infra/sandbox/relay/test_registry.py -v`
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add src/infra/sandbox/relay/__init__.py src/infra/sandbox/relay/registry.py tests/infra/sandbox/relay/test_registry.py
git commit -m "feat(sandbox): daemon 在线注册表（Redis TTL 心跳）"
```

---

### Task 6: 工具调用下发/等结果（dispatch）+ 配置项

**Files:**
- Create: `src/infra/sandbox/relay/dispatch.py`
- Modify: `src/kernel/config/base.py`、`.env.example`
- Test: `tests/infra/sandbox/relay/test_dispatch.py`

**Interfaces:**
- Consumes: `SandboxClientRegistry`（Task 5）、`ErrorCode.DAEMON_OFFLINE / SANDBOX_TIMEOUT`（Task 1）
- Produces:

```python
async def dispatch_local_call(user_id: str, op: str, payload: dict, *, timeout: float | None = None) -> dict
    # op: "exec" | "fs_read" | "fs_write" | ...
    # 流程：is_online 检查(离线抛 DAEMON_OFFLINE) -> rpush sandbox:req:{user_id} ->
    #       轮询 sandbox:resp:{call_id}（50ms 间隔）：
    #       {"stage":"ack"}  须在 SANDBOX_LOCAL_ACK_TIMEOUT(默认30s) 内，否则 SANDBOX_TIMEOUT
    #       {"stage":"done", "status":"ok"|"error", ...}  须在 timeout(默认 SANDBOX_LOCAL_EXEC_TIMEOUT=120s) 内
    #       结果 user_id 不匹配则视为未收到，继续等
    async def cleanup() -> None  # 结束时 delete resp key（fire-and-forget 容错）
```

- [ ] **Step 1: 写失败测试**（复用 Task 5 的 `_FakeRedis` 思路，另加 rpush/lpop/get/set；模拟 ack+done、离线、ack 超时）

```python
"""dispatch 测试：正常往返、离线快速失败、ack 超时。"""
import asyncio
import json

import pytest

from src.infra.sandbox.relay import dispatch as dispatch_module
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.errors import AppError, ErrorCode


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def lpop(self, key: str) -> str | None:
        items = self.lists.get(key)
        return items.pop(0) if items else None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def delete(self, key: str) -> None:
        self.kv.pop(key, None)


class _FakeRegistry:
    def __init__(self, online: bool):
        self.online = online

    async def is_online(self, user_id: str) -> bool:
        return self.online


@pytest.fixture
def fake(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(dispatch_module, "_redis", lambda: redis)
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(True))
    return redis


async def test_roundtrip_ack_then_done(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 2)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)

    async def daemon():
        await asyncio.sleep(0.02)
        req = json.loads(await fake.lpop("sandbox:req:u1"))
        await fake.set(f"sandbox:resp:{req['call_id']}", json.dumps({"user_id": "u1", "stage": "ack"}))
        await asyncio.sleep(0.02)
        await fake.set(
            f"sandbox:resp:{req['call_id']}",
            json.dumps({"user_id": "u1", "stage": "done", "status": "ok", "stdout": "hi"}),
        )

    task = asyncio.create_task(daemon())
    result = await dispatch_local_call("u1", "exec", {"command": "echo hi"})
    await task
    assert result["stdout"] == "hi"


async def test_offline_fails_fast(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_registry", lambda: _FakeRegistry(False))
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    assert exc.value.error_code == ErrorCode.DAEMON_OFFLINE


async def test_ack_timeout_raises(fake, monkeypatch):
    monkeypatch.setattr(dispatch_module, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_ACK_TIMEOUT", 0.05)
    monkeypatch.setattr(dispatch_module.settings, "SANDBOX_LOCAL_EXEC_TIMEOUT", 5)
    with pytest.raises(AppError) as exc:
        await dispatch_local_call("u1", "exec", {})
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/infra/sandbox/relay/test_dispatch.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 配置项**（`src/kernel/config/base.py` 在 `SANDBOX_PLATFORM`（:235）附近加）

```python
    SANDBOX_LOCAL_ACK_TIMEOUT: int = 30  # 本地沙箱 daemon ACK 超时（秒）
    SANDBOX_LOCAL_EXEC_TIMEOUT: int = 120  # 本地沙箱执行总超时（秒）
```

`.env.example` 的 sandbox 分节（:111 `SANDBOX_PLATFORM=daytona` 附近）追加：

```
# 本地沙箱（daemon 中继）超时
SANDBOX_LOCAL_ACK_TIMEOUT=30
SANDBOX_LOCAL_EXEC_TIMEOUT=120
```

- [ ] **Step 4: 实现 `src/infra/sandbox/relay/dispatch.py`**

```python
"""工具调用下发与结果等待：Redis list 请求 + key 轮询结果（spec §3.2，lpop 轮询替代 BLPOP）。"""
import asyncio
import json
import time
import uuid

from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

_POLL_INTERVAL = 0.05


def _redis():
    return get_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


async def dispatch_local_call(
    user_id: str, op: str, payload: dict, *, timeout: float | None = None
) -> dict:
    if not await _registry().is_online(user_id):
        raise AppError(ErrorCode.DAEMON_OFFLINE)
    exec_timeout = timeout if timeout is not None else float(settings.SANDBOX_LOCAL_EXEC_TIMEOUT)
    call_id = uuid.uuid4().hex
    req = {"call_id": call_id, "user_id": user_id, "op": op, "payload": payload}
    redis = _redis()
    resp_key = f"sandbox:resp:{call_id}"
    await redis.rpush(f"sandbox:req:{user_id}", json.dumps(req))

    start = time.monotonic()
    acked = False
    ack_deadline = start + settings.SANDBOX_LOCAL_ACK_TIMEOUT
    exec_deadline = start + exec_timeout
    try:
        while time.monotonic() < exec_deadline:
            raw = await redis.get(resp_key)
            resp = None
            if raw is not None:
                resp = json.loads(raw)
                if resp.get("user_id") != user_id:
                    resp = None  # 他人结果，忽略
            if resp is not None and resp.get("stage") == "ack":
                acked = True
                resp = None
            if resp is not None and resp.get("stage") == "done":
                await redis.delete(resp_key)
                if resp.get("status") != "ok":
                    raise AppError(
                        ErrorCode.SANDBOX_EXEC_FAILED,
                        args={"detail": str(resp.get("error", "local execution failed"))},
                    )
                return resp
            if not acked and time.monotonic() > ack_deadline:
                raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": settings.SANDBOX_LOCAL_ACK_TIMEOUT})
            await asyncio.sleep(_POLL_INTERVAL)
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": int(exec_timeout)})
    finally:
        try:
            await redis.delete(resp_key)
        except Exception:  # noqa: BLE001 - 清理尽力而为
            pass
```

注意：代码引用了 `ErrorCode.SANDBOX_EXEC_FAILED`——回到 Task 1 的错误码清单，**在该任务补充此成员**（`("sandbox_exec_failed", 500, "Local sandbox execution failed: {{detail}}")` + 四语翻译）。实现本任务时若 Task 1 已提交，单独一个小提交补上。

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/infra/sandbox/relay/test_dispatch.py -v`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add src/infra/sandbox/relay/dispatch.py src/kernel/config/base.py .env.example tests/infra/sandbox/relay/test_dispatch.py
git commit -m "feat(sandbox): 本地工具调用下发与结果等待（Redis 往返）"
```

---

### Task 7: SSE 通道 + 结果回传 + 状态端点（路由）

**Files:**
- Create: `src/api/routes/sandbox.py`
- Modify: `src/api/main.py`（注册 `/api/sandbox`）
- Test: `tests/api/routes/test_sandbox_routes.py`

**Interfaces:**
- Consumes: `require_pat_scope("sandbox:execute")`（Task 4）、`SandboxClientRegistry`（Task 5）、`_key` 布局（Task 6：`sandbox:req:{user_id}` / `sandbox:resp:{call_id}`）
- Produces:
  - `GET /api/sandbox/channel`：SSE 流。帧：`event: hello`（`data: {"client_id": ...}`）→ `event: tool_call`（`data: {call_id, op, payload, timeout}`）循环；每 15s 一条注释心跳 `: heartbeat\n\n`；连接期间周期性 `registry.heartbeat`；断开 `unregister`
  - `POST /api/sandbox/results/{call_id}`：body `{"stage": "ack"|"done", "status"?, "stdout"?, "stderr"?, "exit_code"?, "error"?}` → 写 `sandbox:resp:{call_id}`（TTL 120s），附 `user_id`
  - `GET /api/sandbox/status`：`{"online": bool, "client_id"?: str}`
  - 可测核心生成器：`channel_frames(redis, registry, user_id, client_id, *, stop: asyncio.Event) -> AsyncIterator[str]`（端点只做包装）

- [ ] **Step 1: 写失败测试**（直接测生成器 + HTTP 测 status/results）

```python
"""sandbox 通道路由测试：帧生成器、results 写入、status。"""
import asyncio
import json

import pytest
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
    await redis.rpush("sandbox:req:u1", json.dumps({"call_id": "x", "op": "exec", "payload": {}, "timeout": 10}))
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/routes/test_sandbox_routes.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `src/api/routes/sandbox.py`**

```python
"""本地沙箱中继：daemon SSE 通道、结果回传、在线状态。"""
import asyncio
import json
import socket
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.deps import get_current_user_pat_or_jwt, require_pat_scope
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.user import TokenPayload

router = APIRouter()

_POLL_INTERVAL = 0.05
_HEARTBEAT_SECONDS = 15
_NODE_ID = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _redis():
    return get_redis_client()


def _registry() -> SandboxClientRegistry:
    return SandboxClientRegistry()


async def channel_frames(
    redis, registry: SandboxClientRegistry, user_id: str, client_id: str, *, stop: asyncio.Event
) -> AsyncIterator[str]:
    """SSE 帧生成器：hello -> (tool_call | 心跳) 循环；连接期心跳注册表。"""
    yield f"event: hello\ndata: {json.dumps({'client_id': client_id})}\n\n"
    loop = asyncio.get_event_loop()
    last_beat = loop.time()  # 首个心跳在间隔之后到点，保证 hello 后紧跟的是 tool_call
    while not stop.is_set():
        now = loop.time()
        if now - last_beat >= _HEARTBEAT_SECONDS:
            await registry.heartbeat(user_id, client_id, _NODE_ID)
            last_beat = now
            yield ": heartbeat\n\n"
        raw = await redis.lpop(f"sandbox:req:{user_id}")
        if raw is not None:
            yield f"event: tool_call\ndata: {raw}\n\n"
            continue
        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/channel")
async def sandbox_channel(user: TokenPayload = Depends(require_pat_scope("sandbox:execute"))):
    registry = _registry()
    client_id = uuid.uuid4().hex[:12]
    await registry.register(user.sub, client_id, _NODE_ID)
    stop = asyncio.Event()

    async def generator():
        try:
            async for frame in channel_frames(_redis(), registry, user.sub, client_id, stop=stop):
                yield frame
        finally:
            await registry.unregister(user.sub, client_id)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


class SandboxResultRequest(BaseModel):
    stage: str  # "ack" | "done"
    status: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None


@router.post("/results/{call_id}")
async def sandbox_result(
    call_id: str,
    body: SandboxResultRequest,
    user: TokenPayload = Depends(require_pat_scope("sandbox:execute")),
):
    payload = {"user_id": user.sub, **body.model_dump(exclude_none=True)}
    await _redis().set(f"sandbox:resp:{call_id}", json.dumps(payload), ex=120)
    return {"status": "ok"}


@router.get("/status")
async def sandbox_status(user: TokenPayload = Depends(get_current_user_pat_or_jwt)):
    active = await _registry().get_active(user.sub)
    if active is None:
        return {"online": False}
    return {"online": True, "client_id": active[0]}
```

- [ ] **Step 4: 注册路由**（`src/api/main.py` include 区，scheduled_task（:881-883）之后追加）

```python
    app.include_router(sandbox.router, prefix="/api/sandbox", tags=["Sandbox"])
```

（import 区补 `sandbox`，注意与 `src.kernel.config.settings` 无重名冲突。）

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/api/routes/test_sandbox_routes.py tests/api/test_auth_middleware_public_paths.py -v`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/sandbox.py src/api/main.py tests/api/routes/test_sandbox_routes.py
git commit -m "feat(sandbox): daemon SSE 通道/结果回传/在线状态端点"
```

---

### Task 8: LocalSandboxBackend

**Files:**
- Create: `src/infra/backend/local.py`
- Test: `tests/infra/backend/test_local_backend.py`

**Interfaces:**
- Consumes: `dispatch_local_call`（Task 6）、deepagents `BaseSandbox`（`.venv/.../deepagents/backends/sandbox.py:1411`；文件方法 ls/read/write/edit/glob/grep 全部基于 `execute()` 实现，**本后端只需实现 execute**）
- Produces:

```python
class LocalSandboxBackend(BaseSandbox):
    def __init__(self, *, user_id: str, session_id: str, exec_timeout: int | None = None)
    @property
    def id(self) -> str                       # "local-{session_id}"
    def execute(self, command, *, timeout=None) -> ExecuteResponse    # run_blocking_io 包 aexecute（照 E2BBackend :132 样式）
    async def aexecute(self, command, *, timeout=None) -> ExecuteResponse
        # dispatch_local_call(user_id, "exec", {"command": command, "cwd": f"/workspace/{session_id}"})
        # DAEMON_OFFLINE / SANDBOX_TIMEOUT 直接透传 AppError
```

- [ ] **Step 1: 先读 `ExecuteResponse` 定义**（`.venv/lib/python3.12/site-packages/deepagents/backends/protocol.py`，`SandboxBackendProtocol.execute` 返回类型；同时看 `E2BBackend.aexecute`（`src/infra/backend/e2b.py:173`）怎么构造它）。以下测试按 `exit_code/stdout/stderr` 三字段书写，**若实际字段名不同，以 protocol.py 为准同步修改实现与测试**。

- [ ] **Step 2: 写失败测试**（monkeypatch `dispatch_local_call`）

```python
"""LocalSandboxBackend 测试：execute 往返、离线透传、id。"""
import pytest

from src.infra.backend import local as local_module
from src.infra.backend.local import LocalSandboxBackend
from src.kernel.errors import AppError, ErrorCode


async def test_aexecute_maps_result(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        assert (user_id, op) == ("u1", "exec")
        assert payload["command"] == "echo hi"
        return {"status": "ok", "stdout": "hi", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("echo hi")
    assert resp.stdout == "hi" and resp.exit_code == 0


async def test_offline_propagates(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    with pytest.raises(AppError) as exc:
        await backend.aexecute("ls")
    assert exc.value.error_code == ErrorCode.DAEMON_OFFLINE


def test_id_contains_session():
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert backend.id == "local-s1"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/infra/backend/test_local_backend.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 4: 实现 `src/infra/backend/local.py`**（照 `E2BBackend` 的 run_blocking_io 同步包装样式）

```python
"""本地沙箱后端：命令经中继落到用户本机 daemon 执行（spec §3.3）。文件操作由 BaseSandbox 基于 execute() 自动获得。"""
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.kernel.config import settings
from src.utils.async_utils import run_blocking_io  # 位置以 e2b.py:132 的实际 import 为准

try:
    from deepagents.backends.sandbox import BaseSandbox
except ImportError:  # deepagents 导入路径以 e2b.py 顶部实际 import 为准
    BaseSandbox = object  # pragma: no cover


class LocalSandboxBackend(BaseSandbox):  # type: ignore[misc]
    def __init__(self, *, user_id: str, session_id: str, exec_timeout: int | None = None):
        self._user_id = user_id
        self._session_id = session_id
        self._exec_timeout = exec_timeout or settings.SANDBOX_LOCAL_EXEC_TIMEOUT

    @property
    def id(self) -> str:
        return f"local-{self._session_id}"

    async def aexecute(self, command: str, *, timeout: int | None = None) -> "ExecuteResponse":
        result = await dispatch_local_call(
            self._user_id,
            "exec",
            {"command": command, "cwd": f"/workspace/{self._session_id}"},
            timeout=float(timeout or self._exec_timeout),
        )
        return ExecuteResponse(
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code", 0),
        )

    def execute(self, command: str, *, timeout: int | None = None) -> "ExecuteResponse":
        return run_blocking_io(self.aexecute(command, timeout=timeout))
```

（`ExecuteResponse` 与 `run_blocking_io` 的 import 路径按 Step 1 读到的实际位置修正；`BaseSandbox` 的构造签名若要求额外参数，以 `E2BBackend.__init__` 调用方式为准对齐。）

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/infra/backend/test_local_backend.py -v`
Expected: 3 passed。

- [ ] **Step 6: Commit**

```bash
git add src/infra/backend/local.py tests/infra/backend/test_local_backend.py
git commit -m "feat(sandbox): LocalSandboxBackend（中继执行，文件操作经 BaseSandbox 继承）"
```

---

### Task 9: 会话级沙箱路由（agent_options.sandbox）

**Files:**
- Modify: `src/agents/search_agent/nodes.py`（`_create_backend_and_prompt` :529，分支点 :557-588）
- Test: `tests/agents/search_agent/test_sandbox_routing.py`

**Interfaces:**
- Consumes: `LocalSandboxBackend`（Task 8）、`create_sandbox_backend`（`src/infra/backend/deepagent.py:306`）、`agent_options`（`agent_node` :103 读取处）
- Produces:

```python
def _resolve_sandbox_platform(agent_options: dict | None, default_platform: str) -> str
    # agent_options["sandbox"] in {"local", "cloud"} -> 取之；否则 default_platform（settings.SANDBOX_PLATFORM）
# _create_backend_and_prompt 增加 local 分支：
#   backend = create_sandbox_backend(LocalSandboxBackend(user_id=..., session_id=...), assistant_id, user_id=user_id)
#   跳过 LazySandboxBackend 云端路径；其余组装逻辑不变
```

- [ ] **Step 1: 写失败测试**

```python
"""会话级沙箱平台解析测试。"""
import pytest

from src.agents.search_agent.nodes import _resolve_sandbox_platform


@pytest.mark.parametrize(
    ("agent_options", "expected"),
    [
        ({"sandbox": "local"}, "local"),
        ({"sandbox": "cloud"}, "cloud"),
        ({"sandbox": "bogus"}, "daytona"),
        ({}, "daytona"),
        (None, "daytona"),
    ],
)
def test_resolve_sandbox_platform(agent_options, expected):
    assert _resolve_sandbox_platform(agent_options, "daytona") == expected


def test_local_branch_wired():
    """nodes.py 的后端选择处必须引用 _resolve_sandbox_platform 并含 local 分支（源码结构断言）。"""
    from pathlib import Path

    source = Path("src/agents/search_agent/nodes.py").read_text(encoding="utf-8")
    assert "_resolve_sandbox_platform(" in source
    assert "LocalSandboxBackend" in source
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/agents/search_agent/test_sandbox_routing.py -v`
Expected: FAIL，`_resolve_sandbox_platform` 不存在。

- [ ] **Step 3: 实现**（`nodes.py`）

```python
def _resolve_sandbox_platform(agent_options: dict | None, default_platform: str) -> str:
    """会话级沙箱选择：agent_options.sandbox 覆盖全局平台（spec §3.4）。"""
    choice = (agent_options or {}).get("sandbox")
    return choice if choice in {"local", "cloud"} else default_platform
```

在 `_create_backend_and_prompt`（:557-588）`settings.ENABLE_SANDBOX` 分支内，原 `LazySandboxBackend(...)` 构造前插入：

```python
    platform = _resolve_sandbox_platform(agent_options, settings.SANDBOX_PLATFORM.lower())
    if platform == "local":
        from src.infra.backend.local import LocalSandboxBackend

        local_backend = LocalSandboxBackend(user_id=user_id, session_id=session_id)
        return create_sandbox_backend(local_backend, assistant_id, user_id=user_id), prompt
```

（`agent_options`/`user_id`/`session_id`/`assistant_id`/`prompt` 变量沿用该函数与调用方 `agent_node`（:103）作用域内既有名称；返回形状与原函数一致——先读 :529-588 确认返回是 tuple 还是仅 backend，按实际调整这一行的返回构造。）

- [ ] **Step 4: 跑测试 + search_agent 既有测试不回归**

Run: `uv run pytest tests/agents/search_agent -v`
Expected: 新测试 PASS；既有测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/agents/search_agent/nodes.py tests/agents/search_agent/test_sandbox_routing.py
git commit -m "feat(sandbox): 会话级 agent_options.sandbox=local 路由到本地后端"
```

---

### Task 10: 全量回归 + 收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-09-01-local-sandbox-design.md`（状态改"已实施 M1"）

- [ ] **Step 1: 后端全量检查**

Run: `make lint && make typecheck && uv run pytest tests -x -q`
Expected: 全绿。

- [ ] **Step 2: 前端 i18n 覆盖**

Run: `cd frontend && pnpm test -- backendErrorCodeCoverage && pnpm run build`
Expected: PASS。

- [ ] **Step 3: 手工冒烟（可选，需本机 redis）**

```bash
# 终端1：起 redis 与后端后，伪造 daemon：
curl -N -H "Authorization: Bearer <PAT>" http://127.0.0.1:8000/api/sandbox/channel
# 终端2：查状态
curl -H "Authorization: Bearer <PAT>" http://127.0.0.1:8000/api/sandbox/status
```
Expected: channel 先输出 hello 帧；status 返回 `{"online": true}`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-01-local-sandbox-design.md
git commit -m "docs(sandbox): M1 服务端中继落地标记"
```

---

## M2 留存（后续独立计划，不在本计划内）

- daemon（`client/lambchat_sandbox/`：transport/executor/fsops/audit/auth/config/cli）
- HITL 确认（spec §3.5：`local_run_command`/写确认经 ask_human 中断，服务端工具内 interrupt 后才 dispatch）
- `SANDBOX_PAYLOAD_TOO_LARGE` 的 payload 上限校验（daemon 侧产出 + results 端点侧双向）
- frontend：会话沙箱选择器、设置分区、本地工具专属 Item

## Self-Review 记录

- **Spec 覆盖**：§3.1 PAT=Task 2/3/4；§3.2 通道/注册表/路由=Task 5/6/7；§3.3 Backend=Task 8；§3.4 会话路由=Task 9；status 端点=Task 7；§3.5 与 payload 上限明确移 M2（上文"M2 留存"）。§3.6 错误码=Task 1（含执行中发现需补的 `SANDBOX_EXEC_FAILED`，已在 Task 6 Step 4 标注）。
- **占位符扫描**：Task 8 的 `ExecuteResponse`/`run_blocking_io` import 路径与 Task 9 的返回构造标注了"以实际读取为准"——这是对第三方库形状的显式核实步骤（Step 1），不是 TBD。
- **类型一致性**：`PATRecord`/`PATStorage` 方法签名在 Task 2/3/4 间一致；`sandbox:req:{user_id}`/`sandbox:resp:{call_id}` key 布局 Task 6/7 一致；`channel_frames(redis, registry, user_id, client_id, *, stop)` 签名与测试一致。

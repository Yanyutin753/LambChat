# 统一错误码与前端 i18n 报错 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端全部错误返回统一为稳定 snake_case 错误码（REST + SSE），前端以码为 i18n key 五语翻译展示。

**Architecture:** `src/kernel/errors.py` 定义 `ErrorCode` 枚举（唯一事实源）与 `AppError` 基类；`src/api/error_handlers.py` 注册 4 个全局 handler 序列化 `{"detail": {code, message, args}}`；SSE 错误事件统一为 presenter 标准形（带 `code`）；前端 `translateApiError(code, message, args, t)` 按 `backendErrors.<camelCase(code)>` 翻译，无码/未命中回退原文。

**Tech Stack:** Python 3.12 + FastAPI（后端）；React 19 + i18next（前端）；pytest / vitest。

**Spec:** `docs/superpowers/specs/2026-08-30-error-code-i18n-design.md`

## Global Constraints

- 响应契约：`{"detail": {"code": "<snake_case>", "message": "<英文兜底>", "args": {...}}}`；`args` 可省略。
- SSE 错误事件：`{"error": <原文>, "code": <码>, "type": ..., "trace_id": ..., "run_id": ..., "timestamp": ...}`。
- 兜底 message 统一英文；后端不再返回中文错误消息。
- i18n key 规则：`backendErrors.` + camelCase(code)，如 `session_not_found` → `backendErrors.sessionNotFound`。
- 现有 11 处机器码原样吸收：`team_not_found`、`team_member_model_unavailable`、`persona_preset_not_found`、`persona_preset_no_edit_permission`、`persona_preset_no_delete_permission`、`persona_preset_no_admin_permission`、`model_not_found`、`model_disabled`、`model_not_allowed`、`invalid_attachments`、`session_delete_in_progress`。
- 5 个 locale（en/zh/ja/ko/ru）必须同步增补，受 `localeKeyCompleteness.test.ts` 约束。
- 迁移完成后 `src/api/routes/` 禁止 `raise HTTPException`（CI grep 测试）。
- 工作目录：`/home/yangyang/LambChat/.worktrees/feat-error-code-i18n`，分支 `feat/error-code-i18n`。
- 后端命令用 `uv run pytest`；前端命令用 `cd frontend && pnpm test`；提交信息 Conventional Commits + 中文。

---

### Task 1: ErrorCode 枚举与 AppError 基类

**Files:**
- Create: `src/kernel/errors.py`
- Test: `tests/kernel/test_errors.py`

**Interfaces:**
- Produces: `ErrorCode(Enum)`（成员值 `(code: str, status: int)` 二元组；属性 `.code`、`.status`）、`AppError(Exception)`（`__init__(self, code, *, args=None, message=None)`；属性 `.error_code`、`.args_data`、`.message`、`.http_status`）、`ALL_ERROR_CODES`（去重校验用属性集合）。

- [ ] **Step 1: 写失败测试**

```python
"""tests/kernel/test_errors.py"""

import pytest

from src.kernel.errors import AppError, ErrorCode


def test_error_code_properties():
    assert ErrorCode.SESSION_NOT_FOUND.code == "session_not_found"
    assert ErrorCode.SESSION_NOT_FOUND.status == 404


def test_error_codes_unique():
    codes = [member.code for member in ErrorCode]
    assert len(codes) == len(set(codes))


def test_app_error_defaults():
    err = AppError(ErrorCode.SESSION_NOT_FOUND, args={"session_id": "s1"})
    assert err.error_code is ErrorCode.SESSION_NOT_FOUND
    assert err.http_status == 404
    assert err.args_data == {"session_id": "s1"}
    assert err.message == "Session not found"


def test_app_error_message_override():
    err = AppError(ErrorCode.INTERNAL_ERROR, message="boom: detail here")
    assert err.message == "boom: detail here"
    assert str(err) == "boom: detail here"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/kernel/test_errors.py -v`
Expected: FAIL（`ModuleNotFoundError: src.kernel.errors`）

- [ ] **Step 3: 实现 `src/kernel/errors.py`**

枚举含 common 域（`internal_error/500`、`validation_error/422`、`unauthorized/401`、`forbidden/403`、`not_found/404`、`rate_limited/429`、`payload_too_large/413`、`service_unavailable/503`、`conflict/409`、`bad_request/400`、`event_payload_too_large/413`）+ 按域分组的业务码（auth/session/share/mcp/skill/memory/upload/team/persona/role/user/project/human/chat/channel/marketplace/settings/envvar/github/oauth/task），目录以 Task 5 生成的 worksheet 为准增补；每个码带一句英文兜底 message（存为枚举第三元素或 `DEFAULT_MESSAGES` 字典）。骨架：

```python
"""统一错误码与业务异常。唯一事实源：前端 backendErrors.* locale key 与此对齐。"""

from enum import Enum
from typing import Any


class ErrorCode(Enum):
    # (code, http_status, default_message)
    INTERNAL_ERROR = ("internal_error", 500, "Internal server error")
    SESSION_NOT_FOUND = ("session_not_found", 404, "Session not found")
    ...

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def status(self) -> int:
        return self.value[1]

    @property
    def default_message(self) -> str:
        return self.value[2]


DEFAULT_MESSAGES: dict[str, str] = {m.code: m.default_message for m in ErrorCode}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        *,
        args: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.error_code = code
        self.args_data = args or {}
        self.message = message or code.default_message
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return self.error_code.status
```

- [ ] **Step 4: 运行测试通过后提交**

Run: `uv run pytest tests/kernel/test_errors.py -v` → PASS
Commit: `feat(kernel): 统一错误码枚举与 AppError 基类`

---

### Task 2: kernel 异常类改造（继承 AppError）

**Files:**
- Modify: `src/kernel/exceptions.py`（全文重写，13 个类改继承 AppError）
- Modify: `src/kernel/__init__.py`（导出补齐）
- Test: `tests/kernel/test_errors.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `AppError`、`ErrorCode`。
- Produces: `NotFoundError(message=None, *, code=None)` 等兼容构造——`NotFoundError("some message")` 默认码 `not_found`；`NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)` 携带精确码；`EmailNotVerifiedError(message, email)` 保持 `.email` 属性且码 `email_not_verified`。

- [ ] **Step 1: 追加失败测试**

```python
def test_retrofit_not_found_default_code():
    from src.kernel.exceptions import NotFoundError

    err = NotFoundError("whatever message")
    assert err.error_code.code == "not_found"
    assert err.http_status == 404
    assert err.message == "whatever message"


def test_retrofit_not_found_explicit_code():
    from src.kernel.exceptions import NotFoundError

    err = NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)
    assert err.error_code is ErrorCode.MESSAGE_NOT_FOUND
    assert err.args_data == {}


def test_retrofit_email_not_verified_keeps_email():
    from src.kernel.exceptions import EmailNotVerifiedError

    err = EmailNotVerifiedError("verify first", "a@b.c")
    assert err.email == "a@b.c"
    assert err.error_code.code == "email_not_verified"
    assert err.http_status == 403
```

- [ ] **Step 2: 确认失败 → 重写 `exceptions.py`**

每个类定义默认码映射：`AgentError→agent_error/500`、`ConfigurationError→configuration_error/500`、`ValidationError→validation_error/422`、`NotFoundError→not_found/404`、`AuthenticationError→unauthorized/401`、`AuthorizationError→forbidden/403`、`StorageError→storage_error/500`、`LLMError→llm_error/500`、`ToolError→tool_error/500`、`SkillError→skill_error/500`、`SessionError→session_error/500`、`EmailNotVerifiedError→email_not_verified/403`、`AccountNotActiveError→account_not_active/403`。统一改造模板：

```python
class NotFoundError(AppError):
    def __init__(self, code_or_message: "str | ErrorCode | None" = None):
        if isinstance(code_or_message, ErrorCode):
            super().__init__(code_or_message)
        else:
            super().__init__(ErrorCode.NOT_FOUND, message=code_or_message)
```

`EmailNotVerifiedError`/`AccountNotActiveError` 保留 `(message, email)` 签名，内部 `super().__init__(ErrorCode.EMAIL_NOT_VERIFIED, message=message)` 并 `self.email = email`。跑全量后端测试确认 88 处既有 raise 无回归。

- [ ] **Step 3: 测试通过后提交**

Run: `uv run pytest tests/kernel/ -v && uv run pytest -x -q` → PASS
Commit: `refactor(kernel): 异常类继承 AppError 携带错误码`

---

### Task 3: 全局异常处理器

**Files:**
- Create: `src/api/error_handlers.py`
- Modify: `src/api/main.py`（import 并在 app 创建后调用 `register_error_handlers(app)`）
- Test: `tests/api/test_error_handlers.py`

**Interfaces:**
- Consumes: `AppError`、`ErrorCode`。
- Produces: `register_error_handlers(app: FastAPI) -> None`；`error_response(exc: AppError) -> JSONResponse`（handler 内共用序列化函数，SSE 侧也可用其 payload 构造）。

- [ ] **Step 1: 写失败测试**（用 `fastapi.testclient.TestClient` 构造四个探针路由）

```python
"""tests/api/test_error_handlers.py"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.error_handlers import register_error_handlers
from src.kernel.errors import AppError, ErrorCode


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/app-error")
    async def app_error():
        raise AppError(ErrorCode.SESSION_NOT_FOUND, args={"session_id": "s1"})

    @app.get("/http-error")
    async def http_error():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="legacy message")

    @app.get("/validate")
    async def validate(q: int):
        return {"q": q}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret stack")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_shape():
    resp = _client().get("/app-error")
    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["code"] == "session_not_found"
    assert body["message"] == "Session not found"
    assert body["args"] == {"session_id": "s1"}


def test_http_exception_fallback():
    resp = _client().get("/http-error")
    body = resp.json()["detail"]
    assert resp.status_code == 404
    assert body["code"] == "not_found"
    assert body["message"] == "legacy message"


def test_validation_error_shape():
    resp = _client().get("/validate")
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["code"] == "validation_error"
    assert "q" in str(body["args"])


def test_unhandled_error_shape():
    resp = _client().get("/boom")
    assert resp.status_code == 500
    body = resp.json()["detail"]
    assert body["code"] == "internal_error"
    assert "secret" not in body["message"]
```

- [ ] **Step 2: 确认失败 → 实现 `error_handlers.py`**

```python
"""全局异常处理器：统一错误响应契约 {"detail": {code, message, args}}。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

_STATUS_FALLBACK_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def _payload(code: str, message: str, args: dict | None = None) -> dict:
    payload = {"code": code, "message": message}
    if args:
        payload["args"] = args
    return payload


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": _payload(exc.error_code.code, exc.message, exc.args_data)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_FALLBACK_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else code.default_message
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _payload(code.code, message)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": _payload(
                    "validation_error", "Request validation failed", {"fields": fields}
                )
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": _payload("internal_error", "Internal server error")},
        )
```

在 `src/api/main.py` app 实例创建后（路由注册前）调用 `register_error_handlers(app)`。

- [ ] **Step 3: 测试通过后提交**

Run: `uv run pytest tests/api/test_error_handlers.py -v` → PASS
Commit: `feat(api): 全局异常处理器统一错误响应契约`

---

### Task 4: 迁移清单提取脚本

**Files:**
- Create: `scripts/extract_raise_sites.py`

**Interfaces:**
- Produces: `docs/superpowers/plans/error-migration-worksheet.json`（每项：file、line、status、detail_expr、分类建议 literal/fstring/exc_pass/dict）。

- [ ] **Step 1: 写脚本**（AST 扫描 `src/api/routes/` 所有 `raise HTTPException` 与 `raise <Kernel异常>`，输出 JSON worksheet）
- [ ] **Step 2: 运行 `uv run python scripts/extract_raise_sites.py`，核对总数≈395+88**
- [ ] **Step 3: Commit** `chore(scripts): 错误迁移清单提取脚本`

---

### Task 5-N: 模块批量迁移（按批次）

**统一改造配方**（每个批次任务都遵循，TDD：先改该模块测试断言为 `detail["code"]`，跑失败，再改路由，跑通过）：

1. **字面量 detail**：`raise HTTPException(404, "会话不存在")` → `raise AppError(ErrorCode.SESSION_NOT_FOUND)`（码表缺就按命名规则增补）。
2. **f-string detail**：`raise HTTPException(400, f"Server '{name}' already exists")` → `raise AppError(ErrorCode.MCP_SERVER_EXISTS, args={"name": name})`，英文 message 模板进枚举，前端 locale 用 `{{name}}` 插值。
3. **str(exc) 透传**：`raise HTTPException(500, str(exc))` → `raise AppError(ErrorCode.<域>_ERROR, message=str(exc))`；可溯源的（如底层 NotFoundError）改为 `raise AppError(ErrorCode.XXX_NOT_FOUND)` 并删除 except 块让原异常冒泡。
4. **dict detail**：`HTTPException(400, {"error": "invalid_attachments", ...})` → `AppError(ErrorCode.INVALID_ATTACHMENTS)`。
5. **手工 except 转换删除**：`except NotFoundError as exc: ... HTTPException(...)` 直接删（kernel 异常已带码冒泡）；`session.py:239-245` 的字符串比较改 `exc.error_code is ErrorCode.SESSION_DELETE_IN_PROGRESS`。
6. **kernel raise 补码**：infra 层 `raise NotFoundError("message ...")` 中语义明确的改 `raise NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)`。

**批次划分**（每批一个 commit，跑该模块相关测试）：

| 批次 | 模块 | HTTPException 数 |
|------|------|-----------------|
| A | `auth/`（core/verification/oauth）、`deps.py` | ~48 |
| B | `session.py`、`chat.py`、`agent/` | ~47 |
| C | `share.py`、`project.py`、`human.py` | ~48 |
| D | `mcp.py`、`skill.py`、`settings.py`、`memory.py` | ~107 |
| E | `marketplace.py`、`channels.py`、`upload.py`、`upload_cover.py` | ~90 |
| F | `team.py`、`persona_preset.py`、`role.py`、`user.py`、`scheduled_task.py`、`envvar.py`、`github.py`、`main.py` 内联 | ~55 |
| G | infra 层 kernel raise 补码 + 29 处 except 清理 | 88 raise / 29 except |

每批步骤：改测试断言（`assert resp.json()["detail"]["code"] == "<码>"`）→ 跑失败 → 按配方改路由 → 跑通过 → `make lint && make typecheck` → Commit `refactor(api): <模块> 迁移统一错误码`。

---

### Task 6: SSE 错误事件统一

**Files:**
- Modify: `src/infra/writer/presenter_events.py:631-647`（`error()` 加 `code` 参数，默认 `internal_error`）
- Modify: `src/infra/task/executor.py:521-522`（异常类名→码映射后走标准 payload）
- Modify: `src/infra/task/recovery.py:161-162`（`error_code` 字段改名 `code`）
- Modify: `src/api/routes/chat.py:754`、`src/api/routes/agent/__init__.py:111`、`src/api/routes/chat_sse.py:35`（内联裸字符串改走 `_format_sse_event` + 标准 payload，码 `event_payload_too_large`）
- Modify: `src/api/routes/chat.py:796-801`（`/status` 响应加 `code`）
- Modify: `src/api/routes/websocket.py:60,113`（close reason 换稳定码字符串）
- Test: `tests/infra/writer/test_presenter_events.py`（或新建）

**Interfaces:**
- Produces: SSE error payload `{"error", "code", "type", "trace_id", "run_id"?, "details"?, "timestamp"}`；`presenter.error(message, error_type="Error", details=None, code=ErrorCode.INTERNAL_ERROR)`。

步骤：写失败测试（error 事件含 code 字段）→ 改 presenter → 改 5 处杂散点 → 各自测试通过 → Commit `refactor(sse): 错误事件统一标准形状并携带错误码`。

---

### Task 7: 杂项形态收敛

- `channels.py:638-645` 3 处 `{"success": False, "message"}` → AppError 标准错误。
- `main.py:884/891/955`、`session.py:901` 4 处裸 `{"error"}` → 同上。
- `auth/oauth.py:198/216/250/260` `?error=invalid_state|oauth_failed` → 码 `oauth_invalid_state`/`oauth_failed`。
- `middleware/auth.py:117-122` 与 `deps.py` 401 统一 `unauthorized` 码。
- `src/infra/task/` 的 `task_error_code` 字面量（cancelled/server_restart/expired）收编枚举 task 域。
- Commit `refactor(api): 杂项错误形态收敛`。

---

### Task 8: 前端 translateApiError 与 fetch 桥接

**Files:**
- Modify: `frontend/src/utils/backendErrors.ts`（重构）
- Modify: `frontend/src/services/api/fetch.ts:87-108`、`fetch.ts:66`
- Test: `frontend/src/utils/__tests__/backendErrors.test.ts`（新建或扩展）

**Interfaces:**
- Consumes: 后端契约 `detail.code/message/args`。
- Produces: `translateApiError(code: string | undefined, message: string, args: Record<string, unknown> | undefined, t: TFunction): string`；`ApiError extends Error`（`code?: string`、`status?: number`、`args?: Record<string, unknown>`）；`parseErrorDetail(errorData: unknown): {code?, message, args?}`（fetch/upload 共用）。

```ts
const camel = (code: string) => code.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());

export function translateApiError(code, message, args, t) {
  if (code && code !== "internal_error") {
    const key = `backendErrors.${camel(code)}`;
    const translated = t(key, { defaultValue: "", ...(args ?? {}) });
    if (translated && translated !== key) return translated;
  }
  return translateBackendError(message, t); // 原文映射 + 正则兜底（迁移期保留）
}
```

fetch.ts 改造：`!response.ok` 分支用 `parseErrorDetail` 提取三字段，`error.code/.args` 挂载，翻译走 `translateApiError`；`fetch.ts:66` 中文硬编码改 `i18n.t("backendErrors.forceRelogin")`。测试：码命中译码、无码走原文、args 插值、internal_error 原文直出。

Commit `feat(frontend): fetch 层透传错误码并按码翻译`。

---

### Task 9: 前端 SSE 消费与 upload 对齐

**Files:**
- Modify: `frontend/src/hooks/useAgent/eventProcessor.ts:577-594`、`eventHandlers.ts:612-646`、`useAgent.ts:724-735`
- Modify: `frontend/src/services/api/upload.ts:97-110`
- Test: 相应 `__tests__`

SSE error 分支：`data.code` 存在 → `translateApiError(data.code, data.error, undefined, t)`；upload.ts XHR 错误解析复用 `parseErrorDetail` + `translateApiError`。Commit `feat(frontend): SSE 与上传链路接入错误码翻译`。

---

### Task 10: 五语 locale 增补

**Files:**
- Modify: `frontend/src/i18n/locales/{en,zh,ja,ko,ru}.json` 的 `backendErrors` 节

以 Task 1 枚举最终清单为准：每个码加 `backendErrors.<camelCase>` key（en 取枚举英文 message，zh 取原中文 detail（worksheet 里有），ja/ko/ru 按语义翻译）；已有 key（如 `sessionNotFound`）直接复用不重复添加。跑 `pnpm i18n:extract` 与 `pnpm test`（`localeKeyCompleteness` 守门）。Commit `chore(i18n): backendErrors 五语同步增补错误码文案`。

---

### Task 11: 守门测试

**Files:**
- Create: `frontend/src/i18n/__tests__/backendErrorCodeCoverage.test.ts`（读 `src/kernel/errors.py` 正则提码，断言 5 locale 全覆盖 + 无孤儿 key）
- Create: `tests/api/test_no_http_exception.py`（grep `src/api/routes/` 禁 `raise HTTPException`，允许清单为空）
- Test: `tests/kernel/test_errors.py` 已有唯一性断言

Commit `test(ci): 错误码五语覆盖与 HTTPException 禁令守门`。

---

### Task 12: 文档更新

- Modify: `AGENTS.md`：开发规范节新增错误码规矩（新错误必须走 `ErrorCode` 枚举 + 五语 locale + 守门测试说明）。
- Commit `docs: AGENTS.md 增补统一错误码规范`。

---

### Task 13: 全量验证与前后端联调

- [ ] `make lint && make typecheck && uv run pytest -q`（后端全绿）
- [ ] `cd frontend && pnpm run lint && pnpm run build && pnpm test`（前端全绿）
- [ ] `make check-all`
- [ ] 联调（需 MongoDB/Redis 起服务则 `make dev-all`，否则说明受阻项）：
  - curl `POST /api/auth/login`（错误凭据）→ 响应 `detail.code == "invalid_credentials"`
  - curl 访问不存在会话 → `detail.code == "session_not_found"`
  - curl `GET /docs` 探针确认 422 形状
  - 前端 `make dev-all` 后浏览器实测：切 en/zh 语言，触发登录失败，确认 toast 为对应语言译文（browser-use 可用时执行，否则以 vitest + curl 证据为准并明确说明）
- [ ] Commit（如有修补）+ 最终 `git log --oneline` 清点

---

## Self-Review 记录

- 规格覆盖：spec §4.1/4.2→Task 1/2；§4.3→Task 3；§4.4→Task 6；§4.5→Task 7；§4.6→配方 1/Task 5；§5.1→Task 8/9；§5.2→Task 8；§5.3→Task 10；§5.4→Task 9；§6→Task 1/11/迁移步骤；§7→批次划分；联调→Task 13。
- 类型一致性：`AppError.error_code/.http_status/.args_data/.message`、`translateApiError(code, message, args, t)`、`parseErrorDetail` 在 Task 3/8/9 间签名一致。
- 占位符：Task 5 批次表 + 配方为可执行内容；worksheet 由 Task 4 脚本生成，非文档占位。

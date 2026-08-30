# 统一错误码与前端 i18n 报错设计

- 日期：2026-08-30
- 分支：`feat/error-code-i18n`（基于 `develop`）
- 状态：待评审

## 1. 背景与现状

后端错误返回目前完全没有基础设施，共 **18 种错误返回形态、395 处 `HTTPException`**（分布在 35 个路由文件）：

- 无全局异常处理器、无错误码枚举、无统一响应 schema；错误响应由 FastAPI 默认序列化决定（`{"detail": ...}`）。
- 消息语言按模块割裂：130 处中文硬编码（33%，`share.py`/`session.py`/`auth`）、224 处英文（57%，`mcp.py`/`skill.py`/`settings.py`）、11 处 snake_case 机器码、39 处 `detail=str(exc)` 透传（语言不可控）。
- `src/kernel/exceptions.py` 的 13 个异常类是裸 `Exception` 子类（无码、无状态码）；API 层 29 处逐路由手工 `except` 转换，映射规则各异（最差的靠字符串嗅探 `"message" in str(exc)` 猜中文文案）。
- SSE 错误事件有 5 种互不一致的 payload 形状（presenter 标准形、executor 兜底、recovery 带 `error_code`、路由内联裸字符串、`/status` 轮询）。
- 杂项形态：`{"success": False, "message"}` 200 响应 3 处、裸 `{"error"}` 4 处、OAuth `?error=` 重定向 4 处、WebSocket close code + 英文 reason、AuthMiddleware 英文 401 vs `deps.py` 中文 401 两套并存。

前端已有半个桥：`fetch.ts` 统一解析 `detail`（已兼容 object 形状），`backendErrors.ts` 有 ~150 条「后端原文 → i18n key」映射——以后端**原文**为 key，极脆弱；仅 8 个稳定错误码。fetch 层翻译后丢弃 code，调用方拿不到原始码。

### 开源方案评估结论

| 库 | 模式 | 结论 |
|----|------|------|
| apiexception（253⭐, MIT） | 统一响应包装 `{data, status, message, error_code}` | 强制包装所有成功响应，破坏现有 API 契约；无 i18n。否决 |
| fastapi-problem（NRWLDev, Apache-2.0） | RFC 9457（`type/title/detail/status`） | 只解决后端格式；`type` 从类名生成 kebab-case，与已有 snake_case 码约定、前端 201 处 toast 消费、测试断言全冲突。否决 |
| fastapi-problem-details（g0di） | RFC 9457 | 同上，社区更小。否决 |

行业共识（Canva 开发者文档、Stack Overflow 经典讨论、Journaly 实践）：**后端返回稳定机器可读错误码，前端以码为 i18n key 查自己的 locale 文件**，翻译留在前端。与 LambChat 现状（前端 5 语 i18n 完备、后端无 i18n）正匹配。

**决策：借鉴上述库的模式自建轻量体系（核心约 200 行），不引入依赖。**

## 2. 决策记录

| 决策点 | 结论 |
|--------|------|
| 方案 | 自建轻量体系（ErrorCode 枚举 + AppError + 全局 handler） |
| 迁移范围 | 全量一次到位：395 处 HTTPException + 88 处 kernel 异常 raise + SSE 5 种形状 + 杂项形态，单 PR 分阶段 commit |
| SSE 错误事件 | 纳入本期统一 |
| 兜底 message 语言 | 统一英文（迁移时中文 detail 一并换成英文短句，顺带消除后端消息割裂） |
| HTTPException 禁令 | 迁移完成后 CI grep 测试禁止 `src/api/routes/` 下 `raise HTTPException` |
| 翻译归属 | 前端（后端不感知语言，`Accept-Language` 不参与错误路径） |
| 响应格式 | 保持 FastAPI `detail` 外层形状，`detail` 内变为结构化对象，向后兼容 |

## 3. 响应格式契约

### REST 错误响应

```json
{
  "detail": {
    "code": "session_not_found",
    "message": "Session not found",
    "args": { "session_id": "6712f..." }
  }
}
```

- `code`：稳定 snake_case 错误码，前端翻译的唯一依据。
- `message`：英文兜底原文，仅在 locale 缺翻译时展示；动态错误（`str(exc)`）为原始内容。
- `args`：可选插值参数，对应 i18n `{{param}}`。
- 外层保持 `detail` 键：与 FastAPI 默认形状一致，前端现有 `detail` 解析逻辑（object 时取 `message`/`error`）天然兼容，已发布的移动端旧版本无感。

### SSE 错误事件（统一为 presenter 标准形）

```
event: error
data: {"error": "<原文>", "code": "<稳定码>", "type": "<异常类型>",
       "trace_id": "...", "run_id": "...", "timestamp": "..."}
```

## 4. 后端设计

### 4.1 `src/kernel/errors.py`：ErrorCode 枚举 + AppError

```python
class ErrorCode(Enum):
    """每码携带 (snake_case 码名, 默认 HTTP 状态码)，按域注释分组。"""

    SESSION_NOT_FOUND = ("session_not_found", 404)
    MESSAGE_NOT_FOUND = ("message_not_found", 404)
    SESSION_DELETE_IN_PROGRESS = ("session_delete_in_progress", 409)
    ...

    @property
    def code(self) -> str: ...
    @property
    def status(self) -> int: ...


class AppError(Exception):
    """统一业务异常。code 必填；args 供前端插值；message 可选覆盖英文兜底。"""

    def __init__(
        self, code: ErrorCode, *, args: dict[str, Any] | None = None, message: str | None = None
    ): ...
```

- 码名规则：`<域>_<语义>`，全 snake_case。现有 11 处机器码（`team_not_found`、`persona_preset_not_found`、`model_not_found` 等）**原样吸收**进枚举，不破坏已渗入测试的约定。
- 规模：预计 90–120 码，按域分组（auth/session/share/mcp/skill/memory/upload/team/persona/role/user/channel/marketplace/settings/scheduled_task/envvar/github/project/human/chat/common）。
- `common` 域放通用码：`internal_error`、`validation_error`、`unauthorized`、`forbidden`、`not_found`、`rate_limited`、`payload_too_large`、`service_unavailable` 等，兼作兜底映射目标。

### 4.2 kernel 异常类改造

`src/kernel/exceptions.py` 的 13 个异常类全部改为继承 `AppError`：

- 构造签名向后兼容：`NotFoundError("xxx message")` 仍可用（默认码 `not_found`、状态 404）。
- 需要精确码时：`NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)`。
- 效果：infra 层 88 处 `raise` 无需大改即可携带码冒泡；API 层 29 处手工 `except` 转换（含字符串嗅探）全部删除。

### 4.3 全局异常处理器

handler 实现放 `src/api/error_handlers.py`，在 `src/api/main.py` 注册，共 4 个：

| handler | 行为 |
|---------|------|
| `AppError` | 主路径：按 `code.status` 序列化契约格式 |
| `HTTPException` | 兜底（Starlette 内部、漏网遗留）：按状态码映射到 common 域通用码，`detail` 字符串并入 `message` |
| `RequestValidationError` | 422 → `validation_error`，`args` 携带字段级错误摘要 |
| `Exception` | 500 → `internal_error`，`message` 固定英文短句不泄堆栈，完整异常进日志（带 trace_id） |

### 4.4 SSE 收敛

- `src/infra/writer/presenter_events.py` 的 `error()` 增加 `code` 参数，成为唯一标准形状。
- `src/infra/task/executor.py` 兜底错误改走 presenter 或补 `code`（用异常类名映射到 `internal_error`/`agent_error`）。
- `src/infra/task/recovery.py` 的 `error_code` 字段改名 `code`（前端同步）。
- `chat.py:754`、`agent/__init__.py:111`、`chat_sse.py:35` 三处内联裸字符串统一改走 `_format_sse_event` + 标准 payload。
- `/status` 轮询接口响应增加 `code` 字段。
- 动态错误（LLM/工具 `str(exc)`）：code 给 `internal_error` 等，原文照传——前端规则「有码译码，无码/未命中原文」。

### 4.5 杂项形态收敛

- `channels.py` 3 处 `{"success": False, "message"}` 200 响应 → 正常 HTTP 状态码 + 标准错误体。
- `main.py`/`session.py` 4 处裸 `{"error"}` → 同上。
- OAuth `?error=invalid_state|oauth_failed` → 稳定码（`oauth_invalid_state`、`oauth_failed`），前端登录页按码翻译。
- WebSocket close：保留 close code 机制（协议层），reason 字符串换稳定码，前端映射翻译。
- `AuthMiddleware` 英文 401 与 `deps.py` 中文 401 统一为 `unauthorized` 码。
- `src/infra/task/` 散落的 `"task_error_code"` 字面量（`cancelled`/`server_restart`/`expired`）收编进枚举的 task 域。

### 4.6 兜底 message 语言

迁移时所有中文 detail 换成英文短句（与 en locale 文案对齐）。后端不再返回中文错误消息。

## 5. 前端设计

### 5.1 错误解析与透传（`services/api/fetch.ts`、`upload.ts`）

- `authFetch` 解析 `detail.code`，error 对象挂 `.code` + `.status`；现有 `detail.message || detail.error` 保留为回退。
- `upload.ts` XHR 路径复用同一解析函数（当前不经翻译，一并接入）。
- `fetch.ts:66` 硬编码中文「用户权限已变更，请重新登录」改 i18n。
- 组件层 45 处 `(err as Error).message || t("xxx")` 模式不动（message 恒有值）。

### 5.2 翻译函数（`utils/backendErrors.ts` 重构）

```ts
export function translateApiError(
  code: string | undefined,
  message: string,
  args: Record<string, unknown> | undefined,
  t: TFunction,
): string
```

- 规则：`code` 存在 → `t(\`backendErrors.${code}\`, { defaultValue: message, ...args })`；无 `code` → 走现有 3 条动态正则 `BACKEND_ERROR_PATTERNS`，再回退原文。
- 迁移完成后删除 ~150 条以原文为 key 的 `BACKEND_ERROR_KEYS`（稳定码部分不再需要显式映射表）。

### 5.3 locale 增补

5 个 locale（en/zh/ja/ko/ru）各增补 `backendErrors.*` 约 90–120 个 key，插值用 `{{param}}`。受现有 `localeKeyCompleteness.test.ts` 五语一致性约束。

### 5.4 SSE 消费

`eventProcessor.ts` / `eventHandlers.ts` 的 error 分支改用 `data.code` 走 `translateApiError`；`sseConnection.ts` 的终态判断逻辑同步 `code` 字段（`isTerminalSSEEvent` 不受影响，仍按 `type`/`run_id`/`trace_id` 判断）。

## 6. 守门与测试

| 层 | 内容 |
|----|------|
| 后端单测 | 4 个 handler 的响应形状与状态码；枚举码名无重复；kernel 异常兼容构造 |
| 跨栈 CI 测试 | 前端 vitest 扫描后端 `src/kernel/errors.py` 提取码清单（仿 `dedicatedInlineToolItemsSource.test.ts` 模式），断言 5 个 locale 的 `backendErrors.*` 全覆盖且无孤儿 key |
| 禁令测试 | grep 测试禁止 `src/api/routes/` 下 `raise HTTPException` |
| 迁移回归 | 现有测试中 `assert detail == "中文"` 的断言全部改为 `detail["code"]` 断言 |
| 前端单测 | `translateApiError` 优先级（码翻译 > 正则 > 原文）、fetch 层 code 透传 |

## 7. 实施顺序（单 PR 分阶段 commit）

1. 后端基建：`kernel/errors.py` + 异常类改造 + 4 个 handler + 单测。
2. 前端桥接：fetch/upload 解析、`translateApiError`、5 locale 增补。
3. 按模块分批迁移 35 个路由文件（HTTPException → AppError，中文 detail 换英文），同步改测试断言。
4. SSE 5 种形状收敛 + `/status` + recovery 字段改名。
5. 杂项形态（channels/main/OAuth/WS/AuthMiddleware）。
6. 守门测试 + `AGENTS.md` 更新（错误码规矩：新增错误必须走 ErrorCode 枚举并同步 5 locale）。

## 8. 风险与对策

| 风险 | 对策 |
|------|------|
| 39 处 `str(exc)` 透传需逐个溯源归类 | 迁移时逐处查看真实异常源，无法归类的给 `internal_error` + 原文 |
| 测试断言改动量大 | 只改断言目标（`detail["code"]`），不动测试逻辑 |
| 已发布移动端旧版本兼容 | `detail` 外层形状不变，旧版读 `detail.message`（fetch 已双形状处理）照常工作 |
| 错误码遗漏翻译 | 跨栈 CI 测试强制五语全覆盖，漏了直接挂测试 |
| 误删仍需要的原文映射 | 删除 `BACKEND_ERROR_KEYS` 前先跑全量前端测试 + 人工抽查高频错误路径 |

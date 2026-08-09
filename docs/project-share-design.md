# 项目维度分享 技术方案

## 背景

LambChat 现已具备**单会话维度**的分享能力：

- `SharedSession` 记录分享（`share_id` 为 12 字符 URL-safe token），支持 `share_type=full`（全量）/`partial`（按 `run_ids` 选部分），可见性 `visibility=public` / `authenticated`。
- 管理接口在 [src/api/routes/share.py](https://github.com/Yanyutin753/LambChat/blob/main/src/api/routes/share.py)，权限 `session:share`，公开读走 `GET /api/share/public/{share_id}`，SSR `/shared/{share_id}` 注入 SEO（[src/api/main.py](https://github.com/Yanyutin753/LambChat/blob/main/src/api/main.py)）。
- 存储层 [src/infra/share/storage.py](https://github.com/Yanyutin753/LambChat/blob/main/src/infra/share/storage.py) 基于 MongoDB 集合 `shared_sessions`。

同时平台已有 **Project（项目）** 概念：项目是"会话的文件夹"，会话通过 `session.metadata.project_id` 归属项目（[src/kernel/schemas/project.py](https://github.com/Yanyutin753/LambChat/blob/main/src/kernel/schemas/project.py)），可经 `SessionStorage.list_ids_by_project(project_id, user_id)`（[src/infra/session/storage.py](https://github.com/Yanyutin753/LambChat/blob/main/src/infra/session/storage.py)）批量枚举成员。

缺口：用户只能逐个会话分享，无法"一次分享整个项目"或"分享项目内若干会话的集合"。本方案在不破坏现有单会话分享的前提下，扩展出**项目维度分享**。

## 目标

- 一条链接分享一个项目，复刻现有会话分享的两种粒度：
  - **完整项目（full）**：分享项目内**当前全部会话**，访问时**实时**计算成员，项目后续增删会话自动反映。
  - **部分会话（partial）**：从项目内**选中若干会话**，创建**快照**（冻结 `session_ids`），后续项目变化不影响该链接。
- 复用现有可见性（public / authenticated）、SEO 注入、公开页骨架。
- 不破坏现有单会话分享（向后兼容）。

## 非目标

- 项目分享的子会话**不做 run 级 partial**：每个被分享的子会话展示其全部 `completed` 事件（与单会话 full 一致）。run 级 partial 留待后续。
- 不做协作编辑、评论、访问审计、分享统计。
- 不引入新的用户权限项。

## 关键决策（已确认）

| 编号 | 决策 | 结论 |
|---|---|---|
| D1 | full / partial 语义 | 复刻会话分享：`full=实时`、`partial=快照` |
| D2 | 存储结构 | 复用 `shared_sessions` 表，新增 `share_scope` 字段区分 |
| D3 | 内容返回 | 两级返回：manifest（项目+会话摘要）+ 按需加载子会话事件 |
| D4 | 权限 | 复用 `session:share` |

D1 的语义对照表：

| `share_scope` | `share_type` | 行为 | 数据来源 |
|---|---|---|---|
| `session` | `full` | 现有：单会话全量事件 | 读 `session_id` |
| `session` | `partial` | 现有：单会话按 `run_ids` | 读 `session_id` + `run_ids` |
| `project` | `full` | **实时**：项目内当前全部会话 | 访问时 `list_ids_by_project(project_id, owner_id)` |
| `project` | `partial` | **快照**：选中的若干会话 | 创建时冻结 `session_ids` |

## 数据模型变更

### 枚举与快照（[src/kernel/schemas/share.py](https://github.com/Yanyutin753/LambChat/blob/main/src/kernel/schemas/share.py)）

```python
class ShareScope(str, Enum):
    SESSION = "session"
    PROJECT = "project"

class ProjectSnapshot(BaseModel):
    """冻结的项目展示信息，项目改名/删除后仍可稳定渲染。"""
    id: str
    name: str
    icon: Optional[str] = None
```

### `ShareCreate` 扩展

```python
class ShareCreate(BaseModel):
    session_id: Optional[str] = None        # 由必填改为可选（scope=session 时必填）
    share_type: ShareType = ShareType.FULL
    run_ids: Optional[list[str]] = None     # scope=session 且 partial 时必填（不变）
    visibility: ShareVisibility = ShareVisibility.PUBLIC

    # 新增
    share_scope: ShareScope = ShareScope.SESSION
    project_id: Optional[str] = None            # scope=project 时必填
    session_ids: Optional[list[str]] = None     # scope=project 且 partial 时必填（快照）
```

> `session_id` 由必填改为可选**向后兼容**：现有前端创建会话分享时仍会带上该字段，不受影响。

### `SharedSession`（DB 模型）扩展

```python
class SharedSession(BaseModel):
    # ...现有字段不变...
    share_scope: ShareScope = ShareScope.SESSION       # 老数据默认 session
    project_id: Optional[str] = None
    session_ids: Optional[list[str]] = None            # project partial 快照
    project_snapshot: Optional[ProjectSnapshot] = None # 冻结的展示信息
```

### 新增响应模型

```python
class SharedProjectSessionItem(BaseModel):
    """manifest 中的子会话摘要（不含完整事件）。"""
    id: str
    name: Optional[str] = None
    agent_name: Optional[str] = None
    model: Optional[str] = None
    updated_at: datetime
    event_count: int = 0

class SharedProjectContentResponse(BaseModel):
    share_scope: ShareScope = ShareScope.PROJECT
    share_type: ShareType
    project: ProjectSnapshot
    sessions: list[SharedProjectSessionItem]
    owner: SharedContentOwner
    visibility: ShareVisibility
    events_limited: bool = False     # 子会话事件走二级接口，此处恒 False
    events_limit: Optional[int] = None
    sessions_total: int = 0          # live 模式下项目实际成员总数（用于分页）
```

`SharedSessionResponse` / `SharedSessionListItem` 增加 `share_scope`、`project_id` 字段，便于前端区分展示。

### 常量

```python
SHARE_PROJECT_SESSIONS_LIMIT = 50    # partial 模式单次可选会话数上限
SHARE_PROJECT_MANIFEST_DEFAULT = 50  # manifest 默认返回会话数
```

## 校验逻辑

替换现有 `_validate_share_run_ids` 为统一的 `_validate_share_payload`：

```python
def _validate_share_payload(data: ShareCreate) -> None:
    if data.share_scope == ShareScope.SESSION:
        if not data.session_id:
            raise HTTPException(400, "会话分享需要 session_id")
        if data.share_type == ShareType.PARTIAL:
            _validate_share_run_ids(data)        # 复用现有逻辑
        return

    # scope == PROJECT
    if not data.project_id:
        raise HTTPException(400, "项目分享需要 project_id")
    if data.share_type == ShareType.FULL:
        return                                   # 实时模式，无需 session_ids
    # PARTIAL：需要 session_ids 快照
    if not data.session_ids:
        raise HTTPException(400, "部分项目分享需要 session_ids")
    if len(data.session_ids) > SHARE_PROJECT_SESSIONS_LIMIT:
        raise HTTPException(400, f"session_ids 数量不能超过 {SHARE_PROJECT_SESSIONS_LIMIT}")
```

### 项目分享的所有权与归属校验（创建时）

```python
async def _validate_project_share(data: ShareCreate, user: TokenPayload) -> ProjectSnapshot:
    project = await get_project_storage().get_by_id(data.project_id, user.sub)
    if not project:
        raise HTTPException(404, "项目不存在")

    if data.share_type == ShareType.PARTIAL:
        actual = set(await SessionStorage().list_ids_by_project(data.project_id, user.sub))
        if not set(data.session_ids) <= actual:
            raise HTTPException(400, "部分会话不属于该项目")

    return ProjectSnapshot(id=project.id, name=project.name, icon=project.icon)
```

> **越权防护**：partial 模式必须校验所选 `session_ids` 当前确实属于该项目且项目属于当前用户，防止把他人会话塞进自己的项目分享。

## 存储层变更（[src/infra/share/storage.py](https://github.com/Yanyutin753/LambChat/blob/main/src/infra/share/storage.py)）

- `create()`：写入 `share_scope / project_id / session_ids / project_snapshot`。
- `ensure_indexes()`：新增稀疏索引 `create_index("project_id", sparse=True)`，仅对项目分享生效，不影响老数据。
- `_build_shared_session()`：读老文档时 `share_scope` 缺失默认 `SESSION`（与现有 `run_ids`/`visibility` 兜底一致）。
- 新增 `list_by_project(project_id, owner_id)`：仿 `list_by_session`。
- 新增 `delete_by_project(project_id)`：项目删除时清理项目分享记录。

## API 设计

### 管理接口（需登录 + 所有权 + `session:share` 权限）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/share` | 扩展 `ShareCreate`，支持 `share_scope=project` |
| `GET` | `/api/share` | 列我创建的分享（不变，返回项新增 `share_scope`/`project_id`） |
| `GET` | `/api/share/project/{project_id}` | **新增**：列某项目的所有分享（仿 `list_session_shares`） |
| `DELETE` | `/api/share/{share_id}` | 不变 |

创建流程：

```
校验 session:share 权限
→ _validate_share_payload(data)
→ if scope==session: 校验会话所有权（现有）
  if scope==project: _validate_project_share(data, user)  # 含所有权+归属校验
→ 落库（project 分享写入 project_snapshot / session_ids）
→ 返回 SharedSessionResponse
```

### 公开接口（optional auth）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/share/public/{share_id}` | **统一入口**，按 `share_scope` 返回 `SharedContentResponse` 或 `SharedProjectContentResponse`（union response_model） |
| `GET` | `/api/share/public/{share_id}/sessions/{session_id}` | **新增**：项目分享的子会话事件，复用 `_build_session_content` |

#### 统一公开读（manifest 分流）

```python
@router.get("/public/{share_id}")
async def get_shared_content(share_id, session_skip=0, session_limit=SHARE_PROJECT_MANIFEST_DEFAULT,
                             event_limit=None, user=Depends(get_current_user_optional)):
    share = await ShareStorage().get_by_share_id(share_id)
    ...可见性校验...
    if share.share_scope == ShareScope.SESSION:
        return await _build_session_content(share, ...)         # 现有逻辑重构抽出
    return await _build_project_manifest(share, session_skip, session_limit)
```

`_build_project_manifest`：

- 解析成员：
  - `share_type=PARTIAL`：`session_ids = share.session_ids`（快照）
  - `share_type=FULL`：`session_ids = await list_ids_by_project(share.project_id, share.owner_id)`（实时）
- 批量取 `SessionManager().get_sessions(session_ids)`，分页 `session_skip/session_limit`。
- 批量取事件计数 `dual_writer.count_session_events(session_ids, completed_only=True)`（需新增，见下）。
- 裁剪安全字段（`id/name/agent_name/model/updated_at/event_count`），**绝不返回** `user_id` 或会话内部 metadata。
- 返回 `SharedProjectContentResponse`（`project` 取 `share.project_snapshot`，保证项目改名/删除后展示稳定；`sessions_total` 仅 live 模式有意义）。

#### 子会话事件接口（按需加载）

```python
@router.get("/public/{share_id}/sessions/{session_id}")
async def get_shared_session_in_project(share_id, session_id, event_limit=None,
                                        user=Depends(get_current_user_optional)):
    share = await ShareStorage().get_by_share_id(share_id)
    ...可见性校验...
    if share.share_scope != ShareScope.PROJECT:
        raise HTTPException(404)

    # 成员校验
    if share.share_type == ShareType.PARTIAL:
        allowed = set(share.session_ids or [])
    else:  # FULL live
        allowed = set(await list_ids_by_project(share.project_id, share.owner_id))
    if session_id not in allowed:
        raise HTTPException(404)

    session = await SessionManager().get_session(session_id)
    if not session:
        raise HTTPException(404, "原会话已不存在")
    return await _build_session_content(share, session=session, run_ids=None, ...)
```

> 子会话恒读**全量 completed 事件**（`run_ids=None`），与项目分享不做 run 级 partial 的非目标一致。

### 重构：抽取 `_build_session_content`

将现有 `get_shared_content` 中"取事件 + 裁剪安全字段 + 拼 owner + 附 team metadata"整段抽成 `_build_session_content(share, session, run_ids, event_limit)`，供 session-scope 公开读与项目子会话读共用，消除重复。

## 基础设施依赖

### `dual_writer.count_session_events`（新增）

为 manifest 提供每会话事件计数（"12 条消息"），需支持批量：

```python
async def count_session_events(
    self, session_ids: list[str], completed_only: bool = True
) -> dict[str, int]: ...
```

> 实现走与 `read_session_events` 相同的存储（事件/checkpoint 索引），仅返回计数，避免 manifest 把全量事件读进内存。
> 若 P3 前需先上线，可临时令 `event_count` 返回 `None`，前端不展示计数，后续补齐。

## SSR / SEO（[src/api/main.py](https://github.com/Yanyutin753/LambChat/blob/main/src/api/main.py) `serve_shared_page`）

`/shared/{share_id}` 内部调用统一公开读（`user=None`），按 `share_scope` 分流：

- `session` → 现有 `build_shared_page_seo`（会话卡）。
- `project` → **新增** `build_shared_project_seo`：项目卡（项目名 + 图标 + 会话数 + 首条会话预览），`indexable=False`。
- AUTHENTICATED 分享：SSR 固定 `user=None`，命走现有 error SEO 分支（"需要登录"占位卡），与现状一致；建议项目分享默认引导 public 可见性。

## 权限与安全

- **越权防护**：partial 项目分享创建时双重校验（项目属主 + `session_ids ⊆ 项目成员`）。
- **成员校验**：子会话事件接口按 share_type 决定成员来源（快照 `session_ids` / 实时 `list_ids_by_project`），均以 `share.owner_id` 为查询主体，与访问者身份无关。
- **字段裁剪**：manifest 与子会话响应沿用现有安全字段白名单，不泄露 `user_id`、原会话内部 metadata。
- **live 模式成本**：每次访问重查项目成员 + 批量计数；项目通常规模有限，可接受。大项目由 manifest 分页（`session_skip/session_limit`）兜底。

## 清理策略（项目/会话删除联动）

修改 [src/api/routes/project.py](https://github.com/Yanyutin753/LambChat/blob/main/src/api/routes/project.py) `delete_project`：

- **full（实时）项目分享**：项目删除后内容失效 → **删除**该项目的所有 full 分享记录（`delete_by_project` 中按 `share_type=full` 过滤）。
- **partial（快照）项目分享**：内容已冻结、`project_snapshot` 自包含 → **保留**，链接仍可用（展示冻结的项目名/图标）。

会话删除（项目内某会话被删）：

- partial 项目分享：该 `session_id` 在子会话接口的成员校验中命中 `get_session() is None` → 返回 404，manifest 展示时跳过；链接整体仍可用。
- full 项目分享：实时枚举自然不再包含该会话。

## 前端改动

### `frontend/src/services/api/share.ts`

- `create(data)` 已为通用入口，按 `share_scope` 传 `project_id` / `session_ids` 即可。
- `getSharedContent(shareId)` 返回 union；前端按 `share_scope` 分流渲染。
- 新增 `getSessionContentInProject(shareId, sessionId, eventLimit?)` → `GET /api/share/public/{shareId}/sessions/{sessionId}`。
- 新增 `listByProject(projectId)`。

### 新组件 `frontend/src/components/share/SharedProjectPage.tsx`

- 项目封面（图标 + 名称 + 分享者）+ 会话列表（名称 / agent / 模型 / 消息数 / 更新时间）。
- 点击会话 → 调 `getSessionContentInProject` 加载事件，**复用 `ChatMessage`** 渲染（与现有 `SharedPage` 一致）。
- 分页：列表底部"加载更多"驱动 `session_skip/session_limit`。

### `ShareDialog` 项目变体

- 入口：`SessionSidebar` 项目右键菜单 → "分享项目"。
- 选项复刻会话分享 UI：`full`（完整项目·实时）/ `partial`（部分会话·快照，多选会话）+ 可见性切换。
- 已有分享列表读 `listByProject(projectId)`。

### 路由

- `/shared/:shareId`：读到 `share_scope=project` 时渲染 `SharedProjectPage`，否则现有 `SharedPage`。
- `/shared/:shareId/:sessionId`（可选）：项目分享内深链到某会话。

## 向后兼容与迁移

- `share_scope` 默认 `SESSION` → **老文档零迁移**（`_build_shared_session` 兜底）。
- `session_id` 改为可选 → 老调用方仍传该字段，行为不变。
- 公开读返回 union → 老前端只认 session 形态，新增 `share_scope` 字段被忽略。
- `project_id` 稀疏索引 → 不影响老数据查询性能。
- 老 `share_id` token 与新 token 共存。

## 顺带修复的技术债务

> 本期不处理技术债务，以下问题留待后续单独清理：

- `DELETE /{share_id}` 路径参数实为 DB `_id`，命名有歧义。
- `ShareUpdate` schema 定义但无路由使用。
- 404 文案"已过期"但分享无过期机制。
- partial `run_ids` 创建时未校验归属。

## 实施阶段

| 阶段 | 内容 |
|---|---|
| **P1 后端骨架** | schema 扩展 + storage 扩展（含索引、`list_by_project`、`delete_by_project`）+ `_validate_share_payload`/`_validate_project_share` + 管理 `POST/GET` 路由 |
| **P2 公开读** | 抽取 `_build_session_content`；统一公开读 manifest 分流；子会话事件接口；union response_model |
| **P3 事件计数** | `dual_writer.count_session_events`（批量）；接入 manifest `event_count` |
| **P4 SSR/SEO** | `build_shared_project_seo` + `serve_shared_page` 分流 |
| **P5 前端** | `SharedProjectPage` + `ShareDialog` 项目变体 + 路由分流 + `share.ts` 扩展 |
| **P6 清理联动** | `delete_project` 联动清理（full 删除 / partial 保留） |

## 风险与取舍

- **实时（full）访问成本**：每次访问重查项目成员与计数。通过 manifest 分页与批量计数控制；若成为瓶颈，可对 live 分享的项目成员结果做短 TTL 缓存。
- **大项目响应体**：partial 由 `SHARE_PROJECT_SESSIONS_LIMIT=50` 限制；full 由 manifest 分页限制单次返回，`sessions_total` 暴露真实总量。
- **union response_model 的 OpenAPI 表达**：FastAPI 会生成 `oneOf`，文档可读性略降。若团队偏好，可拆为 `/public/s/{id}` 与 `/public/p/{id}` 两路由，代价是前端需探测类型（不推荐）。
- **快照陈旧**：partial 分享不反映项目后续变化。UI 明确提示"分享的是创建时选中的会话"；如需更新，删除旧分享重新创建即可。
- **项目删除后 partial 链接仍存活**：设计如此（快照自包含）。若希望统一失效，可在 `delete_project` 中改为删除全部项目分享——简单但牺牲快照价值，不推荐。

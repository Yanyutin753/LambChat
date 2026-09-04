# 记忆作用域（scope）与项目隔离设计

日期：2026-09-04
状态：已确认，实现中
前置文档：`2026-08-27-memory-system-enhancement-design.md`（A3a 已把 `context` 启用为检索过滤器；本文把"归属边界"正式化为独立维度，与 `context` 的"内容分类"语义分离）

## 背景

对照 openai/codex（`codex-rs`，commit ec84e69，2026-09-03）的世界状态注入与 memories 两阶段流水线，得到两条核心纪律：

1. **上下文必须类型化且归属于所属结构**：`cwd`/`workspace_roots` 是 `role=user` 的 `environments.environment_context` 片段，AGENTS.md 是 `agents_md.instructions` 片段——每个上下文片段有自己的 `content_item_kind`、role 和 marker，不与用户正文混淆；首次请求注入完整 snapshot，后续 turn 只注入 diff。
2. **记忆提取按会话独立、全局合并**：Phase 1 对空闲 rollout 做结构化提取（no-op 是合法结局），Phase 2 全局 consolidation；每个 workspace 有稳定基线，通过 diff 识别增删改。

LambChat 已对齐的部分（保持不动）：记忆正文永不进用户消息；导航索引只挂 `memory_recall` 工具描述且有 30 分钟会话快照；`access_count` 不进索引排序（KV 缓存纪律）；`source_refs` 经 `ConversationHistoryService` 授权校验；两阶段提取（extraction.py + compaction_agent）。

**缺口**：记忆只有 `user_id` 一个隔离维度。`project_id` 写进了 `sessions.metadata.project_id`（有索引），但 memory 写入、检索、索引全部无视它——A 项目的部署约束会泄漏进 B 项目的会话；自动提取产出的项目知识没有归属字段，事后无法回填。

## 目标 / 非目标

**目标**

- 同一用户的多项目记忆互不污染：项目记忆只在其归属项目的会话中可检索、可见于索引。
- 用户级长期偏好跨项目可见（现状保持）。
- `scope` 成为记忆文档的一等字段，`context` 回归纯内容分类。
- 索引字节由内容派生 revision，相同数据 → 相同字节（可断言、可观测），会话内前缀稳定性不回退。

**非目标**

- 不迁移存储（仍用现有 collection）；不重写检索算法；不引入 Codex 式本地 memory workspace 文件树。
- 不给 `memory_recall` 增加"跨项目检索"参数——默认隔离就是产品语义。
- 不引入独立 revision 计数器 collection（见"revision 设计"）。

## scope 模型

| scope | 语义 | project_id | 检索可见性 |
|---|---|---|---|
| `user` | 用户长期偏好、身份、知识 | 空 | 所有会话 |
| `project` | 项目架构、约束、部署、已确认决策 | 必填 | 仅该项目会话 |
| `reference` | 外部资料、链接、供应商 | 空（可选） | 所有会话（外部事实无项目边界） |

**关于 session scope 的决策（考虑后不落库）**：会话临时状态（当前分支、当前 bug、打开的文件）已有承载位——`turn_context`/`active_goal` 写时注入且随状态持久化，自动提取模板明确排除临时状态，`is_manual_memory_worthy` 拒绝瞬时内容。为它再加一个持久 scope 存储位会造成双写和边界混淆。Codex 的对应物（`WorldState` 的 snapshot/diff）本质也是"会话态不进持久记忆"。

**scope 与 context 的关系**：`scope` 回答"这条记忆属于谁"（归属边界），`context` 回答"这条记忆是什么类型的内容"（`project_constraint`/`user_identity`/`feedback_rule`…）。推导规则：`scope=project` 的记忆通常 `context` 以 `project_` 开头，但反之不自动成立——归属必须来自可靠的 `project_id`，不猜。

## project_id 传播链路

现状：`request.project_id` → `sessions.metadata.project_id`（`chat.py:235`），**不进入** agent 执行链（`_execute_agent_stream` 签名无此参数）。

设计：**memory 侧用 `session_id` 反查，不改 agent 执行链**。理由：

- agent stream 链路（chat route → task manager → arq 序列化 → agent.stream kwargs → nodes → middleware）穿透改动面大且触碰 arq 任务兼容性；
- `sessions.metadata.project_id` 是唯一权威源（会话归属可能被用户在会话中途改派，反查天然跟随）；
- memory 各触点已有 session_id：middleware 有、extraction 有 session_doc、memory tools 可从 `runtime.config.configurable.context`（FastAgentContext）拿。

新增 `src/infra/memory/scope.py`：

```python
async def resolve_session_project_id(session_id: str | None) -> str | None
```

- 查 `sessions` collection `metadata.project_id`（投影单字段，命中既有索引 `user_id+metadata.project_id`——按 session_id 反查走 `_id`/`session_id` 索引）。
- 进程内 TTL 缓存 60s（含负缓存：无 project 的会话也缓存，防止无项目用户每轮 retain/recall 都打 Mongo）。会话中途改派项目的可见性延迟 ≤60s，可接受（索引快照本身 30 分钟）。
- 任何异常 → 返回 None（降级为无项目行为，绝不阻塞）。

## 各模块变更

### P0 存储与写入（backend.py）

`retain()` 新增可选参数 `scope: str | None`、`project_id: str | None`：

- 校验：`scope` ∈ {user, project, reference}，非法值拒绝。
- 推导顺序（写入侧绝不猜测归属）：
  1. 显式 `scope=project` 且无 `project_id` → backend 拒绝（`success=False`，错误说明需要项目上下文）；`memory_retain` 工具层在此基础上先降级——无项目会话直接按自动推导存储（→ `user`）并在结果 note 里说明，避免 LLM 误传导致前端报错（2026-09-04 生产回归）；
  2. 显式 `project_id` 无 `scope` → `scope=project`；
  3. `scope` 未传：`context` 以 `project_` 开头 **且** 能解析到 `project_id` → `project`；否则 `user`。拿不到可靠 `project_id` 时项目类内容降级 `user`（与旧行为一致，不丢数据）。
- 新字段落库：`scope`、`project_id`（仅 project scope 时非空）。
- **scope 内去重**：`fetch_recent_memories` / `fetch_semantic_candidates` 增加边界——project 记忆只与同 `(user_id, scope, project_id)` 匹配，跨项目不合并、不互相覆盖。
- MongoDB 增加索引 `(user_id, scope, project_id)`。
- `delete` 不变（按 memory_id，与 scope 无关）。

### P1 检索硬过滤（search.py + vector_store.py）

`recall_memories()` 新增 `project_id: str | None`，构造 scope 子句注入**全部四条**查询路径（text_search / keyword_fallback / vector_search Mongo 链路 / recent_context_fallback）：

```python
def build_scope_clause(project_id: str | None) -> dict:
    visible = {"$in": [None, "user", "reference"]}
    if project_id:
        return {"$or": [{"scope": visible}, {"scope": "project", "project_id": project_id}]}
    return {"scope": visible}  # 无项目会话：看不到任何 project 记忆
```

- 无 `scope` 字段的旧数据命中 `None` → user 语义，向后兼容。
- Qdrant `index_search` payload 增加 `scope`/`project_id`，预过滤同语义。
- `$vectorSearch` 的 `$match` 与 Python 余弦兜底的 base 查询同步携带子句。
- `prioritize_sources` 排序键增加 scope 优先级：`project > user/reference`（同 source 同分时当前项目上下文优先）；`format_memory` 返回体新增 `scope`/`project_id` 字段。

### P2 索引与 revision（indexing.py + prompt_injection.py）

`build_memory_index(backend, user_id, project_id=None)`：

- 候选查询带 scope 子句（与 recall 同源函数，避免两处漂移）；Project 区块仅在项目会话出现。
- 索引头部带内容派生 revision：`compute_index_revision(docs) = sha1(sorted(memory_id + updated_at) + count)[:12]`。相同数据 → 相同 revision → 相同字节；任何写入/删除/合并改变候选集 → revision 变化。**不引入计数器 collection**：计数器需要跨副本原子递增 + 失效广播，而内容 hash 天然满足"相同数据 → 相同字节"，且快照键仍为 `(user_id, session_id)`（session 内 project 不变 → 前缀稳定，30 分钟 TTL 重建时若数据未变字节亦不变，KV 缓存安全）。
- middleware 构建：`MemoryRecallIndexMiddleware` 增加 `project_id` 参数，三个 agent 构建处经 `resolve_session_project_id(session_id)` 解析（会话内首构建时解析一次并随快照固化）。
- `<memory_index_context>` 框架文案不变（untrusted 包装保持）。

### P3 自动提取继承（extraction.py + 模板）

- `find_candidate_sessions` 投影增加 `metadata.project_id`。
- `extract_session_memory`：解析 session 的 `project_id`，retain 时传入；模板新增一节说明：项目相关内容标记归属（输出 `scope` 字段可选），**模板继续禁止**把临时状态存为长期记忆。
- `_fallback_index_fields` 的 context 兜底保持；scope 推导复用 P0 规则（拿不到 project_id 降级 user）。

### P4 工具层（tools.py + base.py）

- `base.py` 新增 `get_session_id_from_runtime(runtime)`（与 `get_user_id_from_runtime` 同风格，从 `configurable.context.session_id` 提取）。
- `memory_retain` 新增可选参数 `scope`（描述说明三种取值与默认继承当前会话项目）；retain 前经 `resolve_session_project_id` 补齐 project_id。
- `memory_recall` 不加新参数——scope 过滤由 runtime session 自动应用（描述更新说明项目隔离语义）。

### P5 迁移（scripts/backfill_memory_scope.py）

- 默认 dry-run：报告无 `scope` 字段的存量记忆分布（按 memory_type 统计、可回填数预估）。
- `--apply`：所有无 scope 记忆 → `scope=user`（安全默认，无归属猜测）。
- `--apply --from-source-sessions`：仅对 `source_refs` 能唯一定位到带 `project_id` 会话的记忆回填 `scope=project`（可追溯归属才回填；定位到多个不同项目会话的跳过并列出）。

## 兼容矩阵

| 场景 | 行为 |
|---|---|
| 旧记忆（无 scope 字段） | 视同 `user`，所有会话可见（现状） |
| 无项目会话 recall | 只见 user/reference（含旧数据），见不到任何 project 记忆 |
| 项目会话 recall | user + reference + 本项目 project |
| `memory_retain` 旧调用（不传 scope） | 推导：context=project_* 且会话有 project → project；否则 user |
| `scope=project` 但无 project_id（无项目会话手动指定） | 工具层降级存为 `user` 并带 note；backend 直连调用仍拒绝并说明原因 |
| 跨项目语义去重 | 互不匹配（各自演化，合并交给本项目内的 consolidation） |

## KV 缓存与 benchmark 验收

会话内多轮前缀稳定性是硬约束（前置文档 C1）。验收方式：

1. **pytest 钉死**：同 session 两次构建索引（数据未变，绕过快照）字节完全一致；revision 相同；数据变化后 revision 变化、字节变化。`access_count`/`accessed_at` 变化不影响索引字节（现有纪律扩展到 scope 字段）。
2. **本地 benchmark**（`scripts/benchmark_memory_scope.py`，独立 benchmark 库不碰开发数据）：
   - **recall 隔离质量**：真实 MongoDB 上构造 3 项目 × N 记忆 + 用户记忆，验证：项目会话内本项目命中率、跨项目泄漏率 = 0、用户记忆跨项目可见率 = 100%。
   - **多轮 KV 缓存率**：模拟 10 轮对话，每轮序列化 `(system + tools 描述 + 历史消息)` 为字节流，计算相邻轮次最长公共前缀占本轮总字节比例（≈ provider 前缀缓存命中率的下界估计）。对比三组：无记忆用户 / 项目用户稳定数据 / 中途写入记忆（下一 session 才生效——验证会话内快照不被写穿）。
3. 中途写记忆不破坏当前会话前缀（快照语义），只影响下一会话——benchmark 断言之一。

## 测试清单

- P0：retain scope 校验（非法值 / project 无 pid 拒绝 / context 推导 / 降级 user）；scope 内去重（跨项目不合并）。
- P1：scope 子句注入四条检索路径（FakeCollection 断言 query）；无项目会话看不到 project 记忆；项目会话可见本项目；`prioritize_sources` 项目优先。
- P2：索引 scope 过滤；revision 稳定性与敏感性；access stats 不影响索引。
- P3：extraction 继承 project_id；无项目会话降级。
- P4：runtime session 提取；retain 工具透传。
- 兼容：旧 schema 文档流经全链路不报错。

## 回滚

无新开关、纯增量字段：revert 代码即回滚，数据多出的 `scope`/`project_id` 字段对旧代码无害（未知字段忽略）。

## 决策记录

- **反查而非穿透传参**：见"project_id 传播链路"。
- **内容 hash revision 而非计数器**：见 P2；可观测性目标（"索引是否变了"）用 hash 即可满足，计数器的一致性成本不划算。
- **session scope 不落库**：见"scope 模型"。
- **recall 不加跨项目参数**：默认隔离是产品语义；确需跨项目共享的内容应该存为 `user` 或 `reference` scope。

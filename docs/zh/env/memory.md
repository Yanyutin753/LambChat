# 记忆系统配置

跨会话记忆系统设置。LambChat 使用原生 MongoDB 支持的记忆系统，支持嵌入语义搜索、查询时相关性注入、自进化教训蒸馏、可选 Qdrant 向量后端。

每个用户可在 **个人设置 → 偏好 → 跨会话记忆** 中自行开启/关闭（默认开启）。关闭后：不自动捕获、不注入索引/查询上下文、记忆工具不可用；面板手动管理不受限，数据保留。

## 主开关

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_MEMORY` | `false` | 启用跨会话记忆系统（服务器级总开关）。 |
| `ENABLE_MEMORY_VFS` | `false` | 启用 `/memories/working/` agent 自管理工作记忆层（多轮长任务笔记）。详见 VFS 工作记忆节。 |

## 嵌入设置

用于记忆的语义搜索。留空则使用纯文本模式（无嵌入）。

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `NATIVE_MEMORY_EMBEDDING_API_BASE` | _(空)_ | 否 | OpenAI 兼容的嵌入 API 基础 URL（**不带** `/v1`，代码自动拼接）。空 = 纯文本模式。 |
| `NATIVE_MEMORY_EMBEDDING_API_KEY` | _(空)_ | 是 | 嵌入 API 密钥。 |
| `NATIVE_MEMORY_EMBEDDING_MODEL` | `text-embedding-3-small` | 否 | 嵌入模型名称。 |
| `NATIVE_MEMORY_EMBEDDING_DIMENSIONS` | `1536` | 否 | 嵌入向量维度（须与模型匹配）。用于自动创建向量索引。 |

## 查询时相关性注入（A1）

开启后，每轮用户消息在**写入时**（非请求时）自动附加 top-K 相关记忆块。块随状态持久化，发送字节 = 持久化历史，provider prompt-cache 前缀跨轮连续（KV 缓存友好）。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `NATIVE_MEMORY_QUERY_CONTEXT_ENABLED` | `false` | 启用查询时相关性注入。默认关闭，灰度开启。 |
| `NATIVE_MEMORY_QUERY_CONTEXT_TOP_K` | `3` | 每轮注入的相关记忆条数上限。 |
| `NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS` | `1200` | 注入块字符预算。低于最小可渲染值时整个放弃。 |

## 自进化记忆

夜间离线反思管线：从差评/失败对话蒸馏行为教训（rule/why/how 三段式），存为 `feedback_rule` 记忆，下次相似任务自动注入。教训在记忆面板中透明可见可删可改。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `NATIVE_MEMORY_SELF_EVOLVE_ENABLED` | `false` | 启用自进化记忆管线（差评/失败信号 → LLM 蒸馏教训）。 |
| `NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT` | `3` | 每用户每晚教训生成上限。 |
| `NATIVE_MEMORY_SELF_EVOLVE_INTERVAL_SECONDS` | `43200` | 调度间隔秒（默认 12h）。 |

自进化护栏（借鉴 Codex/Claude Code）：写入只走离线管线（会话内不写教训）、严格 schema + 脱敏、排除可推导内容、纠正与正反馈同记（👍 1/5 采样防漂移）、30 天未召回的教训由压缩 agent 清退。

## 向量检索后端

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `NATIVE_MEMORY_VECTOR_BACKEND` | `mongo` | 否 | 向量检索后端：`mongo`（内置 $vectorSearch/余弦兜底）或 `qdrant`（专用向量库）。 |
| `NATIVE_MEMORY_QDRANT_URL` | `http://127.0.0.1:6333` | 否 | Qdrant 服务地址。 |
| `NATIVE_MEMORY_QDRANT_API_KEY` | _(空)_ | 是 | Qdrant API 密钥（无鉴权可留空）。 |

`mongo` 模式：MongoDB ≥8.2 原生支持 `$vectorSearch`（自动建索引）；低版本静默降级 Python 余弦兜底（每次扫最近 100 条）。

`qdrant` 模式：Mongo 保持唯一事实源，Qdrant 仅做 ANN 索引视图（可随时删库重建）。支持 type/context 精确过滤。任何 Qdrant 故障静默降级回 mongo 链路。

## 搜索与索引

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `NATIVE_MEMORY_INDEX_ENABLED` | `true` | 启用记忆搜索索引。 |
| `NATIVE_MEMORY_INDEX_CACHE_TTL` | `300` | 索引缓存 TTL（秒）。 |
| `NATIVE_MEMORY_APPEND_MAX_DETAILS` | `8` | 每次记忆追加的最大详情数。 |
| `NATIVE_MEMORY_MAX_TOKENS` | `2000` | 记忆内容的最大 token 数。 |
| `NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS` | `1200` | 内联记忆内容的最大字符数。 |

## 重排序

可选的重排序以提高记忆相关性。

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `NATIVE_MEMORY_RERANK_MODEL` | _(空)_ | 否 | 重排序模型名称。 |
| `NATIVE_MEMORY_RERANK_API_BASE` | _(空)_ | 否 | 重排序 API 基础 URL。 |
| `NATIVE_MEMORY_RERANK_API_KEY` | _(空)_ | 是 | 重排序 API 密钥。 |

## 存储与策略

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `NATIVE_MEMORY_MODEL` | _(空)_ | 否 | 用于记忆提取的管理员模型配置 ID。空 = `DEFAULT_MODEL_ID` / 默认模型。 |
| `NATIVE_MEMORY_COMPACTION_MODEL_ID` | _(空)_ | 否 | 后台记忆压缩 agent 使用的管理员模型配置 ID。空 = 默认模型。 |
| `NATIVE_MEMORY_STORE_NAMESPACE` | `memories` | 否 | LangGraph 存储命名空间。 |
| `NATIVE_MEMORY_STALENESS_DAYS` | `30` | 否 | 记忆被视为过期的天数。 |
| `NATIVE_MEMORY_PRUNE_THRESHOLD` | `90` | 否 | 裁剪阈值百分比。 |
| `NATIVE_MEMORY_RECALL_MIN_SCORE` | `0.3` | 否 | 召回记忆的最低相关性分数（0.0-1.0）。 |
| `NATIVE_MEMORY_AUTO_COMPACT_ENABLED` | `true` | 否 | 启用后台记忆压缩 agent。 |
| `NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD` | `40` | 否 | 每个用户触发自动压缩的记忆数量阈值。 |
| `NATIVE_MEMORY_AUTO_COMPACT_INTERVAL_SECONDS` | `43200` | 否 | 压缩 agent 的定时扫描间隔秒数。 |
| `NATIVE_MEMORY_AUTO_COMPACT_MIN_INTERVAL_SECONDS` | `900` | 否 | 同一用户两次压缩尝试之间的冷却秒数。 |
| `NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY` | `20` | 否 | 每用户每日自动记忆评估上限（0 = 不限）。 |

## VFS 工作记忆

`ENABLE_MEMORY_VFS=true` 时，`/memories/working/` 路径开放给 agent 作多轮长任务工作笔记（计划、中间结论、待验证假设）。持久性用户事实仍只允许通过 `memory_retain` 工具存储。VFS 文件存储在 MongoDB（`memories/{user_id}/vfs` 命名空间），不依赖沙箱。

## 生产点亮顺序

```bash
# 1. 总开关
ENABLE_MEMORY=true

# 2. 嵌入语义搜索（推荐硅基流动 bge-m3）
NATIVE_MEMORY_EMBEDDING_API_BASE=https://api.siliconflow.cn
NATIVE_MEMORY_EMBEDDING_API_KEY=sk-your-key
NATIVE_MEMORY_EMBEDDING_MODEL=BAAI/bge-m3
NATIVE_MEMORY_EMBEDDING_DIMENSIONS=1024

# 3. 记忆 LLM（可选，推荐轻量渠道如 glm-5.3-flash）
NATIVE_MEMORY_MODEL=glm-5.3-flash

# 4. 灰度开查询时注入（观察几天后）
NATIVE_MEMORY_QUERY_CONTEXT_ENABLED=true

# 5. 按需开自进化（需 ENABLE_SCHEDULED_TASK=true）
NATIVE_MEMORY_SELF_EVOLVE_ENABLED=true
```

## 示例（完整配置）

```bash
# 启用记忆 + 嵌入 + 注入 + 自进化
ENABLE_MEMORY=true
ENABLE_SCHEDULED_TASK=true

# 嵌入（硅基流动 bge-m3）
NATIVE_MEMORY_EMBEDDING_API_BASE=https://api.siliconflow.cn
NATIVE_MEMORY_EMBEDDING_API_KEY=sk-your-key
NATIVE_MEMORY_EMBEDDING_MODEL=BAAI/bge-m3
NATIVE_MEMORY_EMBEDDING_DIMENSIONS=1024

# 记忆 LLM（走已有快速渠道）
NATIVE_MEMORY_MODEL=glm-5.3-flash

# 查询时注入
NATIVE_MEMORY_QUERY_CONTEXT_ENABLED=true
NATIVE_MEMORY_QUERY_CONTEXT_TOP_K=3
NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS=1200

# 自进化
NATIVE_MEMORY_SELF_EVOLVE_ENABLED=true
NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT=3
```

# Trace 事件分片存储设计

日期：2026-06-30

## 背景

当前 `TraceStorage` 将同一个 `trace_id` 的事件聚合到 `traces` 集合的一条 MongoDB 文档中，事件写入通过 `$push` 追加到 `events` 数组，并用 `SESSION_MAX_EVENTS_PER_TRACE=50000` 控制单 trace 最多保留的事件数。

这个方案减少了文档数量，也方便按 trace 读取完整上下文。但它有一个结构性上限：MongoDB 单文档 BSON 最大 16MB。即使事件数量限制为 50000，如果单个事件的 `data` 很大，或者大量 chunk 合并前体积较大，单条 trace 文档仍然可能触碰 16MB 限制。事件压缩、合并和大字段截断只能降低概率，不能从数据结构上消除风险。

目标是在不把每个事件拆成一条独立文档的前提下，将单 trace 的事件数组拆成多个固定大小的分片文档。推荐每个分片最多存 5000 条事件，超过后写入下一条分片。

这里的 5000 只代表 MongoDB 单个分片文档的存储大小，不代表对外事件读取上限。`/events` 接口应该跨所有分片返回完整事件流，不能因为 chunk 大小是 5000 就只返回 5000 条。

这个改造必须向后兼容。已有 `traces.events` 旧文档不能要求一次性迁移后才能读取；新版本上线后也要允许灰度切换和安全回滚。

## 推荐方案

保留 `traces` 作为 trace 元数据集合，不再在主 trace 文档里保存完整 `events` 数组。新增 `trace_event_chunks` 集合保存事件分片：

```json
{
  "trace_id": "trace_xxx",
  "session_id": "session_xxx",
  "run_id": "run_xxx",
  "chunk_index": 0,
  "start_seq": 1,
  "end_seq": 5000,
  "event_count": 5000,
  "events": [
    {"seq": 1, "event_type": "message:chunk", "data": {}, "timestamp": "ISODate"},
    {"seq": 2, "event_type": "thinking", "data": {}, "timestamp": "ISODate"}
  ],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

主 `traces` 文档保留列表和状态查询需要的字段：

```json
{
  "trace_id": "trace_xxx",
  "session_id": "session_xxx",
  "run_id": "run_xxx",
  "agent_id": "agent_xxx",
  "user_id": "user_xxx",
  "event_count": 12345,
  "chunk_count": 3,
  "first_event_preview": {},
  "first_user_message_preview": {},
  "last_event_preview": {},
  "status": "running",
  "metadata": {},
  "started_at": "ISODate",
  "updated_at": "ISODate",
  "completed_at": null
}
```

这样主 trace 文档保持小而稳定，事件体积风险被限制在单个 chunk 文档中。每个 chunk 默认最多 5000 条事件，对普通事件足够减少文档数量；如果单个事件 `data` 极大，仍然要保留现有的大字段截断/外置机制，因为单个事件本身也可能接近 BSON 上限。

## 向后兼容要求

兼容目标：

- 旧 trace 可读：历史 `traces.events` 仍然能通过所有现有读取接口返回。
- 新 trace 可读：新写入的 chunk 格式对调用方保持同样的 `TraceStorage` 方法签名和事件返回结构。
- 混合数据可读：同一个环境可以同时存在旧格式 trace 和新格式 trace。
- `/events` 全量返回：会话事件接口默认不限制事件数量，必须跨所有 chunks 返回完整历史事件。
- 灰度可控：可以通过配置逐步启用 chunk 写入和 chunk 优先读取。
- 回滚可行：如果新版本回滚，已经写到 chunk 的新 trace 至少不能丢失；需要保留兼容读路径或短期双写策略。

建议新增两个开关：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_EVENT_CHUNK_STORAGE_ENABLED` | `false` 初始上线，稳定后改 `true` | 是否把新事件写入 `trace_event_chunks`。 |
| `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY` | `false` | chunk 写入开启后，是否短期同时写旧 `traces.events`，用于灰度和回滚窗口。 |

上线推荐顺序：

1. 先发布“读兼容”版本：代码能读 chunk，也能读旧 `traces.events`，但默认仍按旧格式写。
2. 开启后台迁移或小流量验证，把部分旧 trace 切成 chunk，确认读接口行为一致。
3. 开启 `SESSION_EVENT_CHUNK_STORAGE_ENABLED=true`，新 trace 写 chunk。
4. 如需回滚保障，短期打开 `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY=true`，但旧数组仍有 16MB 风险，只建议在低风险窗口使用。
5. 验证稳定后关闭双写，后台迁移旧数据并逐步清理主 trace 的 `events` 大字段。

## 写入规则

新增配置：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_EVENT_CHUNK_SIZE` | `5000` | 每个 trace event chunk 最多保存的事件数。 |
| `MONGODB_TRACE_EVENT_CHUNKS_COLLECTION` | `trace_event_chunks` | trace 事件分片集合名。 |

写入流程：

1. `SESSION_EVENT_CHUNK_STORAGE_ENABLED=false` 时，保持当前旧写入路径，不改变行为。
2. `SESSION_EVENT_CHUNK_STORAGE_ENABLED=true` 时，`create_trace()` 只创建 `traces` 元数据文档，`events` 初始化为空可以逐步废弃。
3. `DualEventWriter` 批量 flush 时按 `trace_id` 分组事件，并为每个 trace 原子预留连续 `seq` 区间。
4. 推荐用 `find_one_and_update({"trace_id": trace_id}, {"$inc": {"event_count": len(events)}})` 获取更新后的 `event_count`，再计算 `start_seq = new_event_count - len(events) + 1`。不要只在进程内读取旧 `event_count` 后计算尾部分片，否则多实例或重试场景可能写错 chunk。
5. 根据每个事件的 `seq` 计算 `chunk_index = (seq - 1) // SESSION_EVENT_CHUNK_SIZE`，把本批事件拆成多段，分别 `$push` 到对应分片。
6. 每次写 chunk 后同步更新 `traces.chunk_count`、`traces.updated_at`、`last_event_preview`。`event_count` 已在 seq 预留步骤原子递增，不能在 chunk 写入阶段重复 `$inc`。
7. 如果 `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY=true`，同一批事件继续写入旧 `traces.events`，但仍受 `SESSION_MAX_EVENTS_PER_TRACE` 和 MongoDB 16MB 限制。
8. terminal 事件（`done`、`complete`、`error`）继续触发立即 flush，保证完成状态前事件已落库。
9. 如果 chunk 写入失败但 `event_count` 已经递增，要记录错误并让调用方可重试；读侧不能根据 `event_count` 推断 chunk 一定完整，必须以实际 chunk 内容为准。

为避免并发写同一 trace 时分片错位，单进程内继续串行 flush，同一 trace 的 bulk operations 按 `seq` 顺序构造。跨进程正确性依赖 MongoDB 原子 seq 预留；如果未来允许多个 producer 长时间并发写同一 `trace_id`，再增加基于 `trace_id` 的 Redis 短锁或改成单 writer 调度。

## 索引

`traces` 保留现有索引：

- `trace_id` 唯一索引
- `(session_id, status, started_at)`
- `(session_id, run_id, status)`
- `(session_id, started_at)`
- `(status, metadata.merged)`

`trace_event_chunks` 新增索引：

- `(trace_id, chunk_index)` 唯一索引，用于按 trace 顺序读取和幂等 upsert。
- `(session_id, run_id, chunk_index)`，用于 run 事件读取。
- `(session_id, trace_started_at, chunk_index)`，用于 session 级事件读取并保持 run 开始时间顺序。
- 可选 `(trace_id, end_seq)`，用于从尾部找最新事件。

chunk 文档必须冗余 `trace_started_at`，否则 session 事件读取要么无法严格按 run 开始时间排序，要么必须 `$lookup` 主 trace，复杂度和成本都会上升。

## 读侧兼容

现有读接口保持方法签名不变，返回结构也保持不变。读侧统一走一个解析顺序：

1. 如果存在 chunk 文档，优先从 `trace_event_chunks` 读取。
2. 如果没有 chunk 文档，回退到旧 `traces.events`。
3. 如果同时存在 chunk 和旧 `traces.events`，以 chunk 为准，避免双写窗口返回重复事件。

各接口调整如下：

- `get_trace(trace_id, include_events=False)`：默认只读 `traces`；`include_events=True` 时聚合所有 chunk events 后附加到返回值。这个路径要继续谨慎使用。
- `get_trace_events(trace_id, event_types, max_events=None)`：把默认值改成 `None`。按 `chunk_index` 升序扫描 chunk，`$unwind` 后过滤。只有调用方显式传入 `max_events` 时才加 `$limit`。当前旧实现默认 `$limit=1000` 且最大 clamp 到 5000，必须在 chunk 读侧上线前改掉。
- `get_session_events(session_id, ..., max_events=None)`：先按 `traces.started_at` 找目标 trace/run，再按 chunk 顺序流式读取事件；或者直接用 chunk 上的冗余字段完成聚合。默认 `max_events=None` 表示不限制，`/events` 应使用这个默认行为，把所有事件发出去。
- `get_first_trace_event()`：读取 `chunk_index=0`，服务端 unwind 后 limit 1。
- `get_last_trace_event()`：优先读取最大 `chunk_index` 的 chunk，按 `seq` 或 `timestamp` 倒序 limit 1。
- `list_run_summaries()`：不再依赖主文档 `events.$elemMatch`，改为使用 `first_user_message_preview`。如果该 preview 缺失，再通过兼容读读取第一条 `user:message`。

建议优先在 `traces` 上同时维护 `first_event_preview` 和 `first_user_message_preview`。run 列表需要的是第一条用户消息，不一定等于 trace 的第一条事件。

旧格式回退必须保留到历史数据迁移完成并经过一个稳定版本后再考虑删除。删除前需要有迁移校验脚本证明 `traces.events` 已为空或已成功切分到 chunk。

`/events` 路由要求：

- 不设置默认 5000 上限，不使用 `SESSION_EVENT_CHUNK_SIZE` 作为读取限制。
- 如果 API 参数没有显式 `limit`，调用 `read_session_events(..., max_events=None)`。
- 如果未来要保护超大响应，应新增显式分页或游标接口，而不是静默截断 `/events`。
- 分享页、搜索回填、附件清理、状态探测等内部场景可以继续显式传 `max_events`，因为这些不是完整事件流交付。

## EventMerger 调整

当前 `EventMerger` 会投影完整 `events` 并把合并后的数组写回 trace 文档。分片后需要改为按 chunk 流式读取事件并写回分片：

1. 只扫描 `traces` 中 `status != running` 且 `metadata.merged != true` 的 trace 元数据。
2. 对单个 trace 先按读侧兼容规则取事件：有 chunk 读 chunk，没有 chunk 读旧 `traces.events`。
3. 执行现有 merge 逻辑。
4. 如果 chunk 写入已开启，合并结果按 `SESSION_EVENT_CHUNK_SIZE` 重新切分，替换该 trace 的全部 chunk。
5. 对旧格式 trace，在迁移期可以继续写回旧 `traces.events`；更推荐合并时顺带产出 chunk，并标记 `metadata.event_storage="chunked"`。
6. 更新 `traces.event_count`、`traces.chunk_count`、`metadata.merged`、`metadata.merged_at`。

这个实现简单可靠，但会在合并时重写该 trace 的 chunk。由于只处理已完成 trace，写入竞争风险较低。后续如果要减少重写成本，可以只合并可合并事件占比高的 trace，或增加 chunk 级 `merged` 标记。

## Usage Log 调整

当前 `_write_usage_log()` 会读取完整 trace 文档并让 `UsageStorage.upsert_usage_log()` 从 `events` 反向查找最后一个 `token:usage`。分片后建议改为：

1. `TraceStorage.complete_trace()` 或 `_write_usage_log()` 调用 `get_last_trace_event(trace_id, ["token:usage"])`。
2. 将 usage event data 与 trace 元数据组成轻量 `trace_doc`。
3. `UsageStorage` 增加 `upsert_usage_log_from_trace_metadata(trace_doc, usage_data)`，避免为了用量日志加载全部事件。

这样 usage 写入也不会受完整事件数组体积影响。

## 现有读取限制调整

当前代码里有两类限制要和 chunk 存储区分开：

- `SESSION_EVENT_CHUNK_SIZE=5000` 只控制单个 MongoDB chunk 文档中最多保存多少事件，不能被复用为读取上限。
- `TRACE_EVENTS_DEFAULT_LIMIT=1000` 和 `TRACE_EVENTS_READ_LIMIT=5000` 目前用于保护旧的 trace 事件查询。分片读上线后，`get_trace_events()` 和 `get_session_events()` 应统一采用 `max_events=None` 表示不限制；只有调用方显式传入限制时才 clamp 到 API 或内部场景允许的最大值。

`GET /sessions/{session_id}/events` 已经支持不传 `limit` 时使用 `max_events=None`，实现时要保证底层 `TraceStorage` 不再额外添加默认 `$limit`。

## 删除与迁移

删除逻辑需要同时删除主 trace 和 chunk：

- `delete_trace(trace_id)`：删除 `traces` 一条，同时 `delete_many({"trace_id": trace_id})` 删除 chunks。
- `delete_session_traces(session_id)`：先找出 session 下 trace_id，再批量删 chunks 和 traces。

迁移策略推荐分阶段：

1. 新增 chunk 集合、索引、配置和双读能力，默认仍旧格式写入。
2. 读接口优先读 chunk；对旧 trace，如果没有 chunk，则回退读取旧 `events` 数组。
3. 后台迁移旧 trace：按 `events` 每 5000 条切分写入 chunk，更新 `chunk_count`，保留旧 `events`。
4. 对迁移后的 trace 做抽样或全量校验：`event_count`、首尾事件、指定 event type 查询结果一致。
5. 新写入切到 `trace_event_chunks`，主 trace 继续保留小 preview 和计数字段。
6. 稳定运行后再清理旧 trace 文档里的 `events` 大字段。

兼容期内，读侧要支持两种格式：

- 新格式：`traces` 无完整 `events`，事件在 `trace_event_chunks`。
- 旧格式：`traces.events` 存在，chunk 不存在。
- 迁移中格式：`traces.events` 和 chunk 同时存在，读侧以 chunk 为准。

回滚策略：

- 如果还在双写窗口，回滚到旧版本后可以继续读 `traces.events`。
- 如果已经关闭双写，旧版本无法读取 chunk-only trace；因此生产回滚要么保留读 chunk 的补丁版本，要么先暂停写入并运行 chunk-to-legacy 回填脚本。
- 不建议长期依赖 chunk-to-legacy 回填，因为回填可能重新触发 16MB 单文档上限。

## 风险和边界

- 5000 条事件只解决“数组累计过大”的问题；如果单个事件 `data` 自身很大，仍可能让单个 chunk 超过 16MB。需要继续保留现有大字段截断，并考虑把超大 payload 外置到对象存储或独立 blob 集合。
- MongoDB `$push + $slice` 的“保留最后 N 条”语义在分片模型中要重新定义。如果仍要限制每 trace 最多 50000 条，可以最多保留 10 个 chunk，并删除最旧 chunk，同时更新 `dropped_event_count`。
- 聚合查询从单文档 `$unwind` 变成跨 chunk 扫描。`/events` 必须允许全量读取；其他内部扫描场景应显式传 `max_events` 或使用分页，避免误把完整事件交付和内部探测混在一起。
- EventMerger 重写 chunk 时要避免和 usage/log 写入互相假设事件位置，建议先完成 trace、写 usage，再做 merge；或让 usage 总是通过 event type 查询。
- `event_count` 原子预留后如果 chunk bulk write 部分失败，可能出现计数大于实际事件数。实现要么在失败时记录并重试，要么在恢复任务中按 chunk 实际内容校验修复。

## 测试建议

重点补以下测试：

- 写入 5001 条事件后生成两个 chunk，第一条 5000 条，第二条 1 条。
- 批量 flush 跨越多个 chunk 时，`seq` 连续且事件顺序不变。
- `get_trace_events()`、`get_session_events()` 在不传 `max_events` 时跨所有 chunks 全量返回。
- `GET /sessions/{session_id}/events` 不传 limit 时返回全部事件，不受 `SESSION_EVENT_CHUNK_SIZE=5000` 影响。
- `get_trace_events()`、`get_session_events()` 在显式传 `max_events` 时才应用限制，并正确应用 `event_types`。
- `get_last_trace_event()` 只读取尾部分片即可返回最后一个 matching event。
- `list_run_summaries()` 不加载完整事件数组。
- `complete_trace()` 能在分片事件中插入或追加缺失的 `token:usage`。
- `EventMerger` 合并完成 trace 后重新切分 chunk，并更新 `event_count/chunk_count/metadata.merged`。
- 删除 trace/session 时 chunk 同步删除。
- 旧格式 trace 没有 chunk 时，读侧能回退到旧 `events`。
- chunk 和旧 `events` 同时存在时，读侧只返回 chunk，不重复返回。
- `SESSION_EVENT_CHUNK_STORAGE_ENABLED=false` 时仍保持旧写入路径。
- `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY=true` 时新事件同时写入 chunk 和旧数组。

## 结论

推荐采用“主 trace 元数据 + trace event chunk 分片”的结构。它保留当前按 trace 聚合的业务模型，又把 MongoDB 16MB 单文档风险从“整个 trace”缩小到“单个 chunk”。默认每 chunk 5000 条事件只是存储分片大小，`/events` 仍然跨所有 chunks 全量返回事件。迁移路径是：先双读兼容，再切写入，最后后台迁移和清理旧大数组。

# 单个 Session 事件爆炸问题分析

## 问题根源

用户反馈：**内存大涨是因为一个 session 里面有很多很多事件**

### 发现的问题

#### 1. MongoDB events 数组无限增长 🔴

```python
# src/infra/session/dual_writer.py:208
"$push": {"events": {"$each": events}},  # 无限追加，没有任何限制！
```

**影响**:
- 单个 trace 文档的 events 数组可以无限增长
- MongoDB 单文档最大 16MB，超过会报错
- 即使不超过，大数组会导致：
  - 查询慢（需要加载整个文档）
  - 内存占用高（整个数组加载到内存）
  - 更新慢（需要重写整个文档）

#### 2. 事件类型分析

一次对话可能产生的事件：

```
用户消息: 1 个事件
Agent 思考: 10-50 个 thinking 事件
LLM 输出: 100-500 个 message:chunk 事件
工具调用: 每个工具 2 个事件（start + end）
子 Agent: 每个子 Agent 递归产生事件

总计: 一次对话可能产生 200-1000+ 个事件
```

#### 3. 长对话场景

```
10 轮对话 × 500 事件/轮 = 5000 个事件
50 轮对话 × 500 事件/轮 = 25000 个事件
100 轮对话 × 500 事件/轮 = 50000 个事件

每个事件约 1-2KB
50000 个事件 = 50-100MB per trace
```

**这就是内存爆炸的根本原因！**

## 解决方案

### 方案 1: 限制单个 trace 的事件数量（推荐）

使用 MongoDB 的 `$slice` 限制数组大小：

```python
# src/infra/session/dual_writer.py
operations.append(
    UpdateOne(
        {"trace_id": trace_id},
        {
            "$push": {
                "events": {
                    "$each": events,
                    "$slice": -10000  # 只保留最新的 10000 个事件
                }
            },
            "$inc": {"event_count": len(events)},
            "$set": {"updated_at": now},
            "$setOnInsert": {
                "session_id": session_id,
                "run_id": run_id or "",
                "status": "running",
                "started_at": now,
            },
        },
        upsert=True,
    )
)
```

**优点**:
- 自动限制数组大小
- 保留最新的事件
- 防止单文档过大

**缺点**:
- 旧事件会被丢弃
- event_count 会不准确（需要额外处理）

### 方案 2: 分片存储（更好）

将事件分散到多个文档：

```python
# 每 1000 个事件创建一个新的 trace 文档
trace_id = f"{base_trace_id}_{event_count // 1000}"
```

**优点**:
- 不丢失事件
- 每个文档大小可控
- 查询性能好

**缺点**:
- 实现复杂
- 需要修改查询逻辑

### 方案 3: EventMerger 更激进（临时方案）

```python
# 更频繁地合并事件
EVENT_MERGE_INTERVAL = 30  # 从 60 秒改为 30 秒
```

**优点**:
- 实现简单
- 减少事件数量

**缺点**:
- 只是缓解，不能根治
- 增加 CPU 开销

### 方案 4: 限制 session 轮次（配合方案 1）

```python
# src/kernel/config/base.py
SESSION_MAX_RUNS_PER_SESSION: int = 100  # 已有
SESSION_MAX_EVENTS_PER_TRACE: int = 10000  # 新增
```

## 立即修复

### 修复 1: 添加 $slice 限制

```python
# src/infra/session/dual_writer.py:208
"$push": {
    "events": {
        "$each": events,
        "$slice": -10000  # 只保留最新的 10000 个事件
    }
},
```

### 修复 2: 添加配置项

```python
# src/kernel/config/base.py
SESSION_MAX_EVENTS_PER_TRACE: int = 10000
```

### 修复 3: 添加监控

```python
# 在写入时检查事件数量
if event_count > SESSION_MAX_EVENTS_PER_TRACE * 0.8:
    logger.warning(
        f"Trace {trace_id} has {event_count} events "
        f"(80% of limit {SESSION_MAX_EVENTS_PER_TRACE})"
    )
```

## 内存占用估算

### 修复前（无限制）

```
单个 trace:
- 100 轮对话 × 500 事件/轮 = 50000 个事件
- 50000 × 2KB = 100MB per trace

10 个活跃 session:
- 10 × 100MB = 1GB

加上其他开销:
- 总计: 1.5-2GB
```

### 修复后（限制 10000 事件）

```
单个 trace:
- 最多 10000 个事件
- 10000 × 2KB = 20MB per trace

10 个活跃 session:
- 10 × 20MB = 200MB

加上其他开销:
- 总计: 500-700MB
```

**内存节省: 1-1.5GB**

## 检查当前状态

### 1. 查看最大的 trace

```bash
docker exec lambchat-mongodb mongosh --eval "
  db.traces.aggregate([
    { \$project: { trace_id: 1, event_count: 1, size: { \$bsonSize: '\$\$ROOT' } } },
    { \$sort: { event_count: -1 } },
    { \$limit: 10 }
  ]).forEach(printjson)
"
```

### 2. 查看事件数量分布

```bash
docker exec lambchat-mongodb mongosh --eval "
  db.traces.aggregate([
    { \$group: {
      _id: null,
      total: { \$sum: 1 },
      avg_events: { \$avg: '\$event_count' },
      max_events: { \$max: '\$event_count' },
      total_events: { \$sum: '\$event_count' }
    }}
  ]).forEach(printjson)
"
```

### 3. 查看大文档

```bash
docker exec lambchat-mongodb mongosh --eval "
  db.traces.find(
    { event_count: { \$gt: 5000 } },
    { trace_id: 1, session_id: 1, event_count: 1 }
  ).forEach(printjson)
"
```

## 紧急清理

如果已经有大量事件堆积：

```bash
# 1. 清理超过 10000 事件的 trace（保留最新 10000 个）
docker exec lambchat-mongodb mongosh --eval "
  db.traces.find({ event_count: { \$gt: 10000 } }).forEach(function(doc) {
    db.traces.updateOne(
      { _id: doc._id },
      {
        \$set: {
          events: doc.events.slice(-10000),
          event_count: 10000
        }
      }
    );
  });
"

# 2. 删除已完成且事件过多的旧 trace
docker exec lambchat-mongodb mongosh --eval "
  db.traces.deleteMany({
    status: 'completed',
    event_count: { \$gt: 10000 },
    completed_at: { \$lt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000) }
  })
"
```

## 监控指标

```bash
# 每小时检查一次
watch -n 3600 'docker exec lambchat-mongodb mongosh --eval "
  db.traces.aggregate([
    { \$group: {
      _id: null,
      max_events: { \$max: \"\$event_count\" },
      avg_events: { \$avg: \"\$event_count\" },
      over_5k: { \$sum: { \$cond: [{ \$gt: [\"\$event_count\", 5000] }, 1, 0] } },
      over_10k: { \$sum: { \$cond: [{ \$gt: [\"\$event_count\", 10000] }, 1, 0] } }
    }}
  ]).forEach(printjson)
"'
```

## 总结

**核心问题**: MongoDB events 数组无限增长

**影响**: 单个 trace 可达 50-100MB，导致内存爆炸

**解决方案**: 
1. 使用 `$slice` 限制为 10000 个事件
2. 添加配置项和监控
3. 清理已有的大文档

**预期效果**: 内存从 2.1GB 降低到 500-700MB

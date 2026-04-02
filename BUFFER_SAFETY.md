# MongoDB 缓冲区安全说明

## _MONGO_BUFFER_MAX 参数详解

### 作用
控制 MongoDB 写入缓冲区的最大事件数量，防止内存无限增长。

### 当前配置
```python
_MONGO_BUFFER_MAX = 50000  # 从 100000 降低到 50000
```

### 事件流程

```
用户请求 → 生成事件 → 写入缓冲区 → 批量写入 MongoDB
                           ↓
                    (每 200 条或 1 秒)
```

### 缓冲区状态

| 缓冲区大小 | 状态 | 行为 |
|-----------|------|------|
| 0 - 200 | 正常 | 每 1 秒或达到 200 条时写入 |
| 200 - 40000 | 正常 | 持续批量写入 |
| 40000 - 50000 | **警告** | 日志警告：MongoDB 可能变慢 |
| 50000+ | **危险** | 丢弃最旧的 25000 条事件 |

### 事件丢失的条件（必须同时满足）

1. ✅ MongoDB 响应慢（>1秒）或宕机
2. ✅ 缓冲区堆积超过 50000 条
3. ✅ 新事件继续产生

### 为什么不会轻易丢失事件

#### 1. 多层保护机制

```python
# 第一层：快速批量写入（每 200 条）
if len(buffer) >= 200:
    立即写入 MongoDB

# 第二层：定时刷新（每 1 秒）
每 1 秒自动刷新缓冲区

# 第三层：80% 警告
if len(buffer) >= 40000:
    logger.warning("缓冲区接近上限")

# 第四层：100% 丢弃
if len(buffer) >= 50000:
    logger.error("丢弃最旧的事件")
    丢弃 25000 条最旧事件
```

#### 2. 双写机制保护

```python
# Redis：立即写入（实时性）
await redis.xadd(stream_key, event)  # 不会丢失

# MongoDB：批量写入（持久化）
buffer.append(event)  # 可能在极端情况下丢失
```

**重要**：即使 MongoDB 缓冲区丢失事件，Redis 中的事件仍然存在（TTL 默认 30 分钟）。

#### 3. 计算缓冲区容量

假设每个事件平均 2KB：
- 50000 条事件 ≈ 100MB 内存
- 达到上限需要：50000 / 200 = 250 批次失败
- 时间估算：250 秒（4 分钟）MongoDB 完全无响应

### 监控和告警

#### 1. 日志监控

```bash
# 查看缓冲区警告
docker logs lambchat | grep "MongoDB buffer"

# 示例输出
# 警告（80%）：
MongoDB buffer at 40000/50000 (80%). Consider checking MongoDB performance.

# 错误（100%）：
MongoDB buffer exceeded 50000, dropped 25000 oldest entries. This indicates MongoDB is slow or down. Check MongoDB health!
```

#### 2. 实时监控

```bash
# 监控 MongoDB 性能
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().metrics"

# 监控容器内存
docker stats lambchat
```

### 调整建议

#### 场景 1：内存充足，MongoDB 可能不稳定
```python
_MONGO_BUFFER_MAX = 100000  # 恢复原值
```

#### 场景 2：内存紧张，MongoDB 稳定
```python
_MONGO_BUFFER_MAX = 20000  # 降低到 20000
```

#### 场景 3：当前配置（平衡）
```python
_MONGO_BUFFER_MAX = 50000  # 保持当前值
```

### 如何避免事件丢失

#### 1. 确保 MongoDB 健康

```bash
# 检查 MongoDB 状态
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().ok"

# 检查慢查询
docker exec lambchat-mongodb mongosh --eval "db.currentOp({secs_running: {$gt: 1}})"
```

#### 2. 优化 MongoDB 配置

```yaml
# docker-compose.yml
mongodb:
  command: mongod --wiredTigerCacheSizeGB 0.5
  deploy:
    resources:
      limits:
        memory: 1G  # 给 MongoDB 足够内存
```

#### 3. 定期清理旧数据

```javascript
// 在 MongoDB 中设置 TTL 索引
db.traces.createIndex(
  { "created_at": 1 },
  { expireAfterSeconds: 604800 }  // 7 天后自动删除
)
```

#### 4. 监控缓冲区大小

```python
# 添加 Prometheus 指标（可选）
from prometheus_client import Gauge

mongo_buffer_size = Gauge('mongo_buffer_size', 'MongoDB buffer size')
mongo_buffer_size.set(len(self._mongo_buffer))
```

### 应急恢复

如果发现事件丢失：

#### 1. 检查 Redis（事件可能还在）

```bash
# 查看 Redis 中的事件
docker exec lambchat-redis redis-cli XLEN "session:{session_id}:{run_id}"
```

#### 2. 从 Redis 恢复到 MongoDB

```python
# 手动触发刷新
await dual_writer.flush_mongo_buffer()
```

#### 3. 重启服务

```bash
docker-compose -f deploy/docker-compose.yml restart lambchat
```

### 总结

- **50000 是一个平衡值**：在内存和数据安全之间取得平衡
- **不会轻易丢失**：需要 MongoDB 持续 4+ 分钟无响应
- **有多层保护**：批量写入、定时刷新、警告日志、Redis 备份
- **可以调整**：根据实际内存和 MongoDB 稳定性调整

**建议**：保持当前的 50000，同时监控日志。如果看到警告，优先检查 MongoDB 性能。

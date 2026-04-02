# LambChat 内存泄漏修复方案

## 问题总结

当事件数量增多时，LambChat 出现内存泄漏，主要原因：

1. **AgentEventProcessor 清理不完整**：异常路径中可能不会调用 clear()
2. **EventMerger 合并间隔过长**：默认 5 分钟，导致事件堆积
3. **DualEventWriter 缓冲区过大**：100000 条事件可能占用大量内存
4. **Docker 未设置内存限制**：容器可以无限制使用内存

## 修复步骤

### 1. 修复 AgentEventProcessor 清理逻辑

**文件**: `src/agents/core/base.py`

在异常处理块中确保 clear() 被调用：

```python
# 第 363-376 行
except asyncio.CancelledError:
    # 任务被取消，yield 队列中剩余的事件（由 manager.py 保存）
    try:
        while not event_queue.empty():
            try:
                item_type, item_data = event_queue.get_nowait()
                if item_type == "event" and item_data:
                    # 使用 AgentEventProcessor 处理剩余事件
                    try:
                        await event_processor.process_event(item_data)
                    except Exception:
                        pass
            except asyncio.QueueEmpty:
                break
    finally:
        # 确保清理 event_processor
        event_processor.clear()
    raise
```

### 2. 优化 EventMerger 配置

**文件**: `deploy/docker-compose.yml`

添加环境变量，缩短合并间隔：

```yaml
environment:
  - EVENT_MERGE_INTERVAL=60  # 从 300 秒改为 60 秒
```

### 3. 减小 DualEventWriter 缓冲区

**文件**: `src/infra/session/dual_writer.py`

```python
# 第 32-34 行
_MONGO_BATCH_SIZE = 200  # 保持不变
_MONGO_BUFFER_MAX = 10000  # 从 100000 改为 10000
_TTL_SET_KEYS_MAX = 1000  # 从 10000 改为 1000
```

### 4. 添加 Docker 内存限制

**文件**: `deploy/docker-compose.yml`

为 lambchat 服务添加内存限制：

```yaml
lambchat:
  container_name: lambchat
  image: ghcr.io/yanyutin753/lambchat:latest
  restart: always
  deploy:
    resources:
      limits:
        memory: 2G  # 限制最大内存为 2GB
      reservations:
        memory: 512M  # 预留 512MB
  # ... 其他配置
```

### 5. 添加 MongoDB 和 Redis 内存限制

```yaml
redis:
  image: redis:alpine
  container_name: lambchat-redis
  restart: always
  command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
  # ... 其他配置

mongodb:
  image: mongo:8.2.5
  container_name: lambchat-mongodb
  restart: always
  command: mongod --wiredTigerCacheSizeGB 0.5
  # ... 其他配置
```

## 监控建议

### 1. 添加内存监控

在 Docker Compose 中添加监控：

```bash
# 查看容器内存使用
docker stats lambchat

# 查看详细内存信息
docker exec lambchat cat /proc/meminfo
```

### 2. 添加日志监控

检查以下日志：

```bash
# EventMerger 日志
docker logs lambchat | grep "EventMerger\|Merge batch"

# 内存相关日志
docker logs lambchat | grep "OOM\|memory\|buffer"
```

### 3. 定期清理

添加定时任务清理旧数据：

```python
# 在 MongoDB 中设置 TTL 索引
db.traces.createIndex(
  { "created_at": 1 },
  { expireAfterSeconds: 604800 }  # 7 天后自动删除
)
```

## 应急措施

如果内存仍然泄漏：

1. **重启容器**：
   ```bash
   docker-compose -f deploy/docker-compose.yml restart lambchat
   ```

2. **清理 MongoDB**：
   ```bash
   docker exec lambchat-mongodb mongosh --eval "db.traces.deleteMany({status: {$ne: 'running'}})"
   ```

3. **清理 Redis**：
   ```bash
   docker exec lambchat-redis redis-cli FLUSHDB
   ```

## 验证修复

1. 部署修复后，监控内存使用：
   ```bash
   watch -n 5 'docker stats --no-stream lambchat'
   ```

2. 检查事件合并是否正常：
   ```bash
   docker logs -f lambchat | grep "Merge batch completed"
   ```

3. 压力测试：发送大量消息，观察内存是否稳定

# LambChat 内存泄漏修复总结

## 已完成的修复

### 1. ✅ AgentEventProcessor 清理逻辑
**文件**: `src/agents/core/base.py:363-376`
**问题**: 异常路径中可能不会调用 `clear()`
**修复**: 添加 `finally` 块确保清理

### 2. ✅ MemorySaver TTL 清理
**文件**: `src/agents/core/base.py:164-210`
**问题**: MemorySaver 无限累积 checkpoint 数据
**修复**: 
- 添加后台清理任务，每小时清理一次
- 删除 1 小时前的旧 checkpoint
- 添加清理日志

### 3. ✅ LLM 模型缓存限制
**文件**: `src/infra/llm/client.py:119-211`
**问题**: 模型缓存无限增长
**修复**:
- 限制最多缓存 10 个模型实例
- LRU 淘汰策略
- 添加淘汰日志

### 4. ✅ DualEventWriter 缓冲区优化
**文件**: `src/infra/session/dual_writer.py:30-34`
**修复**:
- `_MONGO_BUFFER_MAX`: 100000 → 50000
- `_TTL_SET_KEYS_MAX`: 10000 → 5000
- 添加 80% 警告机制
- 改进错误日志

### 5. ✅ Docker 内存限制
**文件**: `deploy/docker-compose.yml`
**修复**:
- lambchat: 限制 2GB，预留 512MB
- Redis: 限制 256MB + LRU 淘汰
- MongoDB: WiredTiger 缓存 0.5GB
- 事件合并间隔: 300秒 → 60秒

## 内存泄漏根源

### 主要问题
1. **MemorySaver 无限累积** - 每个会话 1-5MB，1000 个会话 = 1-5GB
2. **AgentFactory 单例** - Agent 实例永不释放
3. **LLM 模型缓存** - 每个实例 10-50MB，无限增长
4. **AgentEventProcessor** - 异常时可能不清理

### 内存占用估算
```
修复前（1000 个会话）:
- MemorySaver: 1000 × 1MB = 1GB
- AgentEventProcessor: 1000 × 50KB = 50MB
- DualEventWriter: 100MB
- LLM 缓存: 5 × 30MB = 150MB
- 其他: 100MB
总计: ~1.4GB (500MB → 2.1GB)

修复后（1000 个会话）:
- MemorySaver: 最多 1 小时的数据 ≈ 100-200MB
- AgentEventProcessor: 正确清理 ≈ 0MB
- DualEventWriter: 50MB
- LLM 缓存: 最多 10 个实例 ≈ 300MB
- 其他: 100MB
总计: ~550-650MB
```

## 部署步骤

### 1. 检查当前状态
```bash
# 检查是否使用 MongoDB Checkpointer
docker logs lambchat 2>&1 | grep -E "MemorySaver|MongoDB checkpointer"

# 检查当前内存使用
docker stats --no-stream lambchat
```

### 2. 重新构建并部署
```bash
cd /home/yangyang/LambChat

# 停止服务
docker-compose -f deploy/docker-compose.yml down

# 重新构建（如果需要）
docker-compose -f deploy/docker-compose.yml build

# 启动服务
docker-compose -f deploy/docker-compose.yml up -d

# 查看日志
docker logs -f lambchat
```

### 3. 验证修复

#### 检查 MemorySaver 清理
```bash
# 应该看到类似的日志（每小时一次）
docker logs lambchat | grep "Cleaned.*old checkpoints"

# 示例输出:
# [Agent search] Cleaned 45 old checkpoints (total remaining: 123)
```

#### 检查 LLM 缓存淘汰
```bash
# 应该看到类似的日志（当缓存满时）
docker logs lambchat | grep "LLM cache full"

# 示例输出:
# LLM cache full (10), evicted oldest model
```

#### 检查 MongoDB 缓冲区
```bash
# 应该看到警告（如果缓冲区达到 80%）
docker logs lambchat | grep "MongoDB buffer"

# 正常情况下不应该看到警告
```

### 4. 监控内存

#### 实时监控
```bash
# 每 5 秒更新一次
watch -n 5 'docker stats --no-stream lambchat'
```

#### 长期监控
```bash
# 记录 24 小时的内存使用
while true; do
  echo "$(date '+%Y-%m-%d %H:%M:%S') $(docker stats --no-stream --format '{{.MemUsage}}' lambchat)" >> memory_log.txt
  sleep 300  # 每 5 分钟记录一次
done
```

## 预期效果

### 修复前
- 初始内存: 500MB
- 1000 个会话后: 2.1GB
- 增长率: 4.2x
- 问题: 内存持续增长，不会回收

### 修复后
- 初始内存: 500MB
- 1000 个会话后: 550-800MB
- 增长率: 1.1-1.6x
- 效果: 内存稳定，自动清理

## 监控指标

### 关键日志
```bash
# MemorySaver 清理
docker logs lambchat | grep "Cleaned.*old checkpoints"

# LLM 缓存淘汰
docker logs lambchat | grep "LLM cache"

# MongoDB 缓冲区警告
docker logs lambchat | grep "MongoDB buffer"

# AgentEventProcessor 清理
docker logs lambchat | grep "event_processor.clear"
```

### 性能指标
```bash
# 内存使用
docker stats --no-stream lambchat | awk '{print $4}'

# MongoDB checkpoint 数量
docker exec lambchat-mongodb mongosh --eval "db.checkpoints.countDocuments()"

# Redis 内存使用
docker exec lambchat-redis redis-cli INFO memory | grep used_memory_human
```

## 故障排查

### 问题 1: 仍然看到 "Using MemorySaver"
**原因**: MongoDB 连接失败
**解决**:
```bash
# 检查 MongoDB 状态
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().ok"

# 检查连接字符串
docker logs lambchat | grep "MongoDB"

# 重启 MongoDB
docker-compose -f deploy/docker-compose.yml restart mongodb
```

### 问题 2: 内存仍然增长
**原因**: 可能有其他泄漏源
**解决**:
```bash
# 检查清理日志
docker logs lambchat | grep -E "Cleaned|evicted|cleared"

# 如果没有看到清理日志，检查代码是否正确部署
docker exec lambchat cat /app/src/agents/core/base.py | grep "_cleanup_memory_saver"

# 重新构建镜像
docker-compose -f deploy/docker-compose.yml build --no-cache
```

### 问题 3: MongoDB 缓冲区警告
**原因**: MongoDB 响应慢
**解决**:
```bash
# 检查 MongoDB 性能
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().connections"

# 增加 MongoDB 内存
# 编辑 docker-compose.yml:
# mongodb:
#   command: mongod --wiredTigerCacheSizeGB 1.0  # 从 0.5 增加到 1.0
#   deploy:
#     resources:
#       limits:
#         memory: 2G  # 从 1G 增加到 2G
```

## 回滚方案

如果修复导致问题：

```bash
# 1. 停止服务
docker-compose -f deploy/docker-compose.yml down

# 2. 恢复代码
git checkout HEAD~1 src/agents/core/base.py
git checkout HEAD~1 src/infra/llm/client.py
git checkout HEAD~1 src/infra/session/dual_writer.py
git checkout HEAD~1 deploy/docker-compose.yml

# 3. 重新部署
docker-compose -f deploy/docker-compose.yml up -d --build
```

## 后续优化

### 1. 使用 MongoDB Checkpointer（推荐）
确保 MongoDB 连接正常，避免使用 MemorySaver

### 2. 添加 Prometheus 监控
```python
from prometheus_client import Gauge

memory_saver_size = Gauge('memory_saver_checkpoints', 'Number of checkpoints in MemorySaver')
llm_cache_size = Gauge('llm_cache_models', 'Number of cached LLM models')
```

### 3. 定期清理 MongoDB
```javascript
// 设置 TTL 索引
db.checkpoints.createIndex(
  { "ts": 1 },
  { expireAfterSeconds: 604800 }  // 7 天
)
```

## 文档

- [内存泄漏深度分析](MEMORY_LEAK_ANALYSIS.md)
- [缓冲区安全说明](BUFFER_SAFETY.md)
- [修复方案](memory_leak_fix.md)

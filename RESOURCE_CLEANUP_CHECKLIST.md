# 对话取消时的资源清理检查清单

## 问题

用户担心：**当对话被取消时，资源会不会没有被清理？**

这是一个非常重要的问题，因为：
1. 用户可能随时取消对话
2. 取消时可能有很多资源正在使用
3. 如果资源没有清理，会导致内存泄漏

## 资源清理检查

### ✅ 1. AgentEventProcessor（已修复）

**位置**: `src/agents/core/base.py:410-420, 422-439`

**清理机制**:
```python
try:
    # 处理事件
    await event_processor.process_event(item_data)
finally:
    # 注销并取消流任务
    self._stream_tasks.pop(presenter.run_id, None)
    if not stream_task.done():
        stream_task.cancel()
    # 清理 event_processor 内存
    event_processor.clear()  # ✅ 确保清理

except asyncio.CancelledError:
    try:
        # 处理剩余事件
    finally:
        event_processor.clear()  # ✅ 双重保险
    raise
```

**状态**: ✅ **已完善** - 使用双层 finally 块确保清理

---

### ✅ 2. Stream Task（已有）

**位置**: `src/agents/core/base.py:410-418`

**清理机制**:
```python
finally:
    # 注销并取消流任务
    self._stream_tasks.pop(presenter.run_id, None)
    if not stream_task.done():
        stream_task.cancel()
        try:
            await stream_task
        except (asyncio.CancelledError, TaskInterruptedError):
            pass
```

**状态**: ✅ **正常** - 取消并等待任务完成

---

### ✅ 3. Agent Close（已有）

**位置**: `src/api/routes/chat.py:57-61`

**清理机制**:
```python
except (asyncio.CancelledError, TaskInterruptedError):
    # 取消/中断时，调用 agent.close 清理资源
    if run_id:
        await agent.close(run_id)
    raise
```

**Agent.close 做了什么**:
```python
# src/agents/core/base.py:225-234
async def close(self, run_id: Optional[str] = None):
    if run_id is not None:
        # 取消特定的 stream_task
        task = self._stream_tasks.pop(run_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
```

**状态**: ✅ **正常** - 取消并清理任务

---

### ✅ 4. MCP 工具连接（自动清理）

**位置**: `src/infra/tool/mcp_pool.py:152-173`

**清理机制**:
```python
async def cleanup_expired_connections() -> int:
    """清理过期的连接，返回清理的数量"""
    expired_servers = [name for name, conn in _connection_pool.items() if conn.is_expired()]
    
    for server_name in expired_servers:
        pooled = _connection_pool.pop(server_name, None)
        if pooled:
            if hasattr(pooled.client, "close"):
                await pooled.client.close()
            elif hasattr(pooled.client, "__aexit__"):
                await pooled.client.__aexit__(None, None, None)
```

**触发**: 定期自动清理（每 N 次请求）

**状态**: ✅ **正常** - 自动清理过期连接

---

### ✅ 5. MCP 缓存（自动清理）

**位置**: `src/infra/tool/mcp_cache.py:67-77`

**清理机制**:
```python
def _cleanup_expired_cache() -> int:
    """清理过期的缓存条目"""
    expired_users = [user_id for user_id, entry in _tools_cache.items() if entry.is_expired()]
    for user_id in expired_users:
        entry = _tools_cache.pop(user_id, None)
        if entry and entry.client:
            asyncio.create_task(_close_client(entry.client))
```

**状态**: ✅ **正常** - 自动清理过期缓存

---

### ✅ 6. MCP Global 缓存（自动清理）

**位置**: `src/infra/tool/mcp_global.py:212-221`

**清理机制**:
```python
def _cleanup_expired_entries() -> int:
    """清理过期的缓存条目"""
    expired_users = [user_id for user_id, entry in _global_entries.items() if entry.is_expired()]
    for user_id in expired_users:
        entry = _global_entries.pop(user_id, None)
        if entry:
            task = asyncio.create_task(entry.manager.close())
```

**状态**: ✅ **正常** - 自动清理过期条目

---

### ✅ 7. Event Queue（已有限制）

**位置**: `src/agents/core/base.py:343`

**保护机制**:
```python
event_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
```

**说明**: 限制队列大小，防止消费者慢时内存无限增长

**状态**: ✅ **正常** - 有大小限制

---

### ✅ 8. LLM 模型缓存（已修复）

**位置**: `src/infra/llm/client.py:199-211`

**清理机制**:
```python
max_cache_size = LLMClient._get_max_cache_size()
if len(LLMClient._model_cache) >= max_cache_size:
    # LRU 淘汰
    oldest_key = next(iter(LLMClient._model_cache))
    del LLMClient._model_cache[oldest_key]
```

**状态**: ✅ **已修复** - LRU 淘汰，限制 50 个实例

---

### ⚠️ 9. HTTP 连接池（需要检查）

**问题**: LLM 客户端（ChatAnthropic, ChatOpenAI）内部使用 httpx，可能有连接池

**检查**:
```python
# ChatAnthropic 和 ChatOpenAI 使用 httpx.AsyncClient
# 这些客户端在 LLMClient._model_cache 中缓存
# 当缓存淘汰时，旧的客户端会被删除
# 但是 httpx.AsyncClient 的连接池可能不会立即关闭
```

**潜在问题**: 
- 如果 LLM 客户端没有正确关闭，连接池可能泄漏
- 每个客户端可能有 10-100 个连接

**建议**: 添加显式关闭

---

### ⚠️ 10. Sandbox Session（需要检查）

**位置**: `src/infra/sandbox/session_manager.py`

**需要检查**: 
- Sandbox session 是否在对话取消时正确清理
- 是否有超时机制

---

## 潜在问题和建议

### 🔴 问题 1: LLM 客户端连接池可能泄漏

**位置**: `src/infra/llm/client.py:199-211`

**问题**:
```python
# 当淘汰旧的模型实例时
oldest_key = next(iter(LLMClient._model_cache))
del LLMClient._model_cache[oldest_key]  # 只是删除引用，没有关闭连接
```

**建议修复**:
```python
# 淘汰时显式关闭
if len(LLMClient._model_cache) >= max_cache_size:
    oldest_key = next(iter(LLMClient._model_cache))
    oldest_model = LLMClient._model_cache[oldest_key]
    
    # 尝试关闭连接
    try:
        if hasattr(oldest_model, 'client') and hasattr(oldest_model.client, 'aclose'):
            await oldest_model.client.aclose()
    except Exception as e:
        logger.debug(f"Failed to close LLM client: {e}")
    
    del LLMClient._model_cache[oldest_key]
```

---

### 🟡 问题 2: Sandbox Session 清理不明确

**需要检查**:
1. Sandbox session 是否有超时机制
2. 对话取消时是否清理 sandbox
3. 是否有孤儿 sandbox 进程

**建议**: 添加定期清理和超时机制

---

## 测试场景

### 场景 1: 用户取消对话

```python
# 1. 用户发起对话
# 2. LLM 正在生成响应
# 3. 用户点击取消
# 4. 检查资源是否清理

预期:
- ✅ AgentEventProcessor.clear() 被调用
- ✅ stream_task 被取消
- ✅ event_queue 被清空
- ⚠️ LLM HTTP 连接是否关闭？
```

### 场景 2: 长时间运行后取消

```python
# 1. 用户发起对话
# 2. Agent 调用多个工具
# 3. MCP 连接建立
# 4. 用户取消
# 5. 检查资源是否清理

预期:
- ✅ MCP 连接会在过期后自动清理
- ✅ 工具缓存会自动清理
- ✅ Event processor 清理
```

### 场景 3: 多次取消

```python
# 1. 用户发起对话 A
# 2. 取消
# 3. 用户发起对话 B
# 4. 取消
# 5. 重复 100 次
# 6. 检查内存是否增长

预期:
- ✅ 内存应该稳定
- ⚠️ 需要验证 LLM 连接池是否泄漏
```

---

## 监控命令

### 1. 检查资源清理日志

```bash
# AgentEventProcessor 清理
docker logs lambchat | grep "event_processor.clear"

# Stream task 取消
docker logs lambchat | grep "Cancelled stream task"

# MCP 连接清理
docker logs lambchat | grep "Cleaned up.*connections"

# LLM 缓存淘汰
docker logs lambchat | grep "LLM cache full"
```

### 2. 检查内存增长

```bash
# 监控内存
watch -n 1 'docker stats --no-stream lambchat'

# 多次取消对话后，内存应该稳定
```

### 3. 检查连接数

```bash
# 检查 TCP 连接数
docker exec lambchat netstat -an | grep ESTABLISHED | wc -l

# 多次取消后，连接数应该稳定
```

---

## 总结

### ✅ 已经做得很好的地方

1. **AgentEventProcessor** - 双层 finally 块确保清理
2. **Stream Task** - 正确取消和等待
3. **MCP 连接** - 自动清理过期连接
4. **Event Queue** - 有大小限制
5. **LLM 缓存** - LRU 淘汰

### ⚠️ 需要改进的地方

1. **LLM 客户端连接池** - 淘汰时应该显式关闭
2. **Sandbox Session** - 需要检查清理机制

### 🎯 建议

1. **立即修复**: LLM 客户端连接池关闭
2. **验证**: Sandbox session 清理机制
3. **测试**: 多次取消对话，监控内存和连接数
4. **监控**: 添加资源清理的日志和指标

---

## 优先级

1. 🔴 **高优先级**: 修复 LLM 客户端连接池泄漏
2. 🟡 **中优先级**: 验证 Sandbox session 清理
3. 🟢 **低优先级**: 添加更多监控日志

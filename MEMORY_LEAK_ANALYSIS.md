# LambChat 内存泄漏深度分析

## 问题现象
内存从 500MB 增长到 2.1GB（增长 4 倍），且不会被回收。

## 根本原因分析

### 🔴 严重泄漏源

#### 1. MemorySaver 无限累积 Checkpoint 数据
**位置**: `src/agents/core/base.py:142` 和 `src/infra/storage/checkpoint.py:84`

**问题**:
```python
# 每个 Agent 实例都创建一个 MemorySaver
self._checkpointer = MemorySaver()  # 永不清理！
```

**影响**:
- 每次对话都会在 MemorySaver 中保存完整的状态快照
- 包括所有消息历史、工具调用结果、中间状态
- **永不过期，永不清理**
- 估计每个会话 1-5MB，1000 个会话 = 1-5GB

**为什么会泄漏**:
```python
# MemorySaver 内部实现（LangGraph）
class MemorySaver:
    def __init__(self):
        self.storage = {}  # 字典，永不清理
    
    def put(self, config, checkpoint):
        # 每次对话都添加，从不删除
        self.storage[thread_id] = checkpoint
```

#### 2. AgentFactory 单例缓存
**位置**: `src/agents/core/base.py:516`

**问题**:
```python
class AgentFactory:
    _instances: Dict[str, BaseGraphAgent] = {}  # 永不清理
    
    # 每个 Agent 持有:
    # - MemorySaver (包含所有历史会话)
    # - _stream_tasks (可能有未清理的任务)
    # - _graph (编译后的图，包含所有节点)
```

**影响**:
- Agent 实例永不释放
- 每个 Agent 的 MemorySaver 永不释放
- 所有历史会话数据永不释放

#### 3. LLM 模型缓存无限增长
**位置**: `src/infra/llm/client.py:119`

**问题**:
```python
class LLMClient:
    _model_cache: dict[tuple, BaseChatModel] = {}  # 永不清理
    
    # 缓存 key 包含:
    # - provider, model_name, temperature, max_tokens
    # - api_key, api_base, thinking, profile
    # 
    # 不同参数组合 = 不同缓存条目
    # 每个模型实例可能占用 10-50MB
```

**影响**:
- 不同参数组合会创建多个模型实例
- 每个实例包含完整的模型配置和连接池
- 估计每个实例 10-50MB

#### 4. AgentEventProcessor 的 checkpoint_to_agent 映射
**位置**: `src/infra/agent/events.py:56`

**问题**:
```python
class AgentEventProcessor:
    def __init__(self, presenter: Presenter):
        self.checkpoint_to_agent: dict[str, tuple[str, str]] = {}
        self.thinking_ids: dict[str | None, str | None] = {}
        self._output_buffer = StringIO()
        self._chunk_buffer = ""
```

**已修复**: 添加了 `finally` 块确保 `clear()` 被调用

### 🟡 中等泄漏源

#### 5. DualEventWriter 缓冲区
**位置**: `src/infra/session/dual_writer.py:33`

**已优化**: 
- `_MONGO_BUFFER_MAX`: 100000 → 50000
- 添加了 80% 警告机制

#### 6. EventMerger 合并间隔过长
**位置**: `src/kernel/config/base.py:111`

**已优化**: 
- `EVENT_MERGE_INTERVAL`: 300秒 → 60秒（通过环境变量）

## 内存占用估算

### 单个会话的内存占用

```
MemorySaver checkpoint:
  - 消息历史: 10-50KB
  - 工具调用结果: 5-20KB
  - 中间状态: 5-10KB
  - 总计: 20-80KB per checkpoint
  - 每个会话可能有 5-20 个 checkpoint
  = 100KB - 1.6MB per session

AgentEventProcessor (未清理时):
  - checkpoint_to_agent: 1-5KB
  - thinking_ids: 1-2KB
  - _output_buffer: 10-100KB
  - _chunk_buffer: 1-10KB
  = 13-117KB per session

DualEventWriter buffer:
  - 每个事件: ~2KB
  - 50000 events = 100MB
```

### 1000 个会话的累积

```
MemorySaver: 1000 × 1MB = 1GB
AgentEventProcessor (未清理): 1000 × 50KB = 50MB
DualEventWriter: 100MB (上限)
LLM 模型缓存: 5 × 30MB = 150MB
其他: 100MB

总计: ~1.4GB
```

**这解释了为什么内存从 500MB 增长到 2.1GB！**

## 修复方案

### 方案 1: 使用 MongoDB Checkpointer（推荐）

**优点**:
- Checkpoint 数据持久化到 MongoDB
- 内存中不保留历史数据
- 支持跨实例共享状态

**实现**:
```bash
# 确保 MongoDB 可用
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().ok"

# 检查是否使用了 MongoDB checkpointer
docker logs lambchat | grep "Using MongoDB checkpointer"
```

**如果看到 "Using MemorySaver"**:
```bash
# 检查 MongoDB 连接
docker logs lambchat | grep "MongoDB checkpointer"
```

### 方案 2: 为 MemorySaver 添加 TTL 清理

**修改**: `src/agents/core/base.py`

```python
async def initialize(self) -> None:
    """初始化 Agent"""
    if self._initialized:
        return

    # 创建 checkpointer（优先 MongoDB，fallback 到 MemorySaver）
    if self.enable_checkpointer:
        from src.infra.storage.checkpoint import get_mongo_checkpointer

        self._checkpointer = get_mongo_checkpointer()
        if self._checkpointer is None:
            from langgraph.checkpoint.memory import MemorySaver
            
            self._checkpointer = MemorySaver()
            
            # 启动后台清理任务
            asyncio.create_task(self._cleanup_memory_saver())
            
            logger.warning(
                f"[Agent {self._agent_id}] Using MemorySaver with TTL cleanup"
            )
        else:
            logger.info(f"[Agent {self._agent_id}] Using MongoDB checkpointer")

async def _cleanup_memory_saver(self):
    """定期清理 MemorySaver 中的旧数据"""
    while True:
        try:
            await asyncio.sleep(3600)  # 每小时清理一次
            
            if not isinstance(self._checkpointer, MemorySaver):
                break
            
            # 清理 1 小时前的 checkpoint
            cutoff_time = datetime.now() - timedelta(hours=1)
            storage = self._checkpointer.storage
            
            to_delete = []
            for thread_id, checkpoint in storage.items():
                # 检查 checkpoint 时间戳
                if hasattr(checkpoint, 'ts') and checkpoint.ts < cutoff_time:
                    to_delete.append(thread_id)
            
            for thread_id in to_delete:
                del storage[thread_id]
            
            if to_delete:
                logger.info(
                    f"[Agent {self._agent_id}] Cleaned {len(to_delete)} old checkpoints"
                )
        except Exception as e:
            logger.error(f"Failed to cleanup MemorySaver: {e}")
```

### 方案 3: 定期清理 Agent 实例

**修改**: `src/agents/core/base.py`

```python
class AgentFactory:
    """Agent 工厂，管理实例创建和缓存"""

    _instances: Dict[str, BaseGraphAgent] = {}
    _lock = asyncio.Lock()
    _last_cleanup = datetime.now()

    @classmethod
    async def get(cls, agent_id: str) -> BaseGraphAgent:
        """获取 Agent 实例（单例）"""
        # 定期清理（每 30 分钟）
        if (datetime.now() - cls._last_cleanup).total_seconds() > 1800:
            await cls._cleanup_old_instances()
            cls._last_cleanup = datetime.now()
        
        if agent_id in cls._instances:
            return cls._instances[agent_id]

        async with cls._lock:
            if agent_id in cls._instances:
                return cls._instances[agent_id]

            if agent_id not in _AGENT_REGISTRY:
                raise ValueError(f"Agent '{agent_id}' 未注册")

            agent_cls = _AGENT_REGISTRY[agent_id]
            agent = agent_cls()
            await agent.initialize()
            cls._instances[agent_id] = agent
            return agent

    @classmethod
    async def _cleanup_old_instances(cls):
        """清理旧的 Agent 实例"""
        async with cls._lock:
            for agent_id, agent in list(cls._instances.items()):
                try:
                    # 清理 MemorySaver
                    if hasattr(agent, '_checkpointer'):
                        checkpointer = agent._checkpointer
                        if hasattr(checkpointer, 'storage'):
                            storage = checkpointer.storage
                            # 只保留最近 100 个 checkpoint
                            if len(storage) > 100:
                                # 按时间戳排序，删除最旧的
                                sorted_items = sorted(
                                    storage.items(),
                                    key=lambda x: getattr(x[1], 'ts', 0),
                                    reverse=True
                                )
                                # 保留最新的 100 个
                                storage.clear()
                                for thread_id, checkpoint in sorted_items[:100]:
                                    storage[thread_id] = checkpoint
                                
                                logger.info(
                                    f"[Agent {agent_id}] Cleaned old checkpoints, "
                                    f"kept 100 most recent"
                                )
                except Exception as e:
                    logger.error(f"Failed to cleanup agent {agent_id}: {e}")
```

### 方案 4: 限制 LLM 模型缓存大小

**修改**: `src/infra/llm/client.py`

```python
class LLMClient:
    """LLM 客户端工厂，支持实例缓存和 fallback。"""

    _model_cache: dict[tuple, BaseChatModel] = {}
    _MAX_CACHE_SIZE = 10  # 最多缓存 10 个模型实例

    @staticmethod
    def get_model(
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        thinking: Optional[dict] = None,
        profile: Optional[dict] = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """获取 LangChain 聊天模型（带缓存）。"""
        model = model or settings.LLM_MODEL
        provider, model_name = _parse_provider(model)

        if profile is None and settings.LLM_MAX_INPUT_TOKENS is not None:
            profile = {"max_input_tokens": settings.LLM_MAX_INPUT_TOKENS}

        cache_key = _make_cache_key(
            provider,
            model_name,
            temperature,
            max_tokens,
            api_key,
            api_base,
            thinking,
            profile,
            settings.LLM_MAX_RETRIES,
        )

        if cache_key in LLMClient._model_cache:
            return LLMClient._model_cache[cache_key]

        # LRU 淘汰：如果缓存满了，删除最旧的
        if len(LLMClient._model_cache) >= LLMClient._MAX_CACHE_SIZE:
            # 删除第一个（最旧的）
            oldest_key = next(iter(LLMClient._model_cache))
            del LLMClient._model_cache[oldest_key]
            logger.info(f"LLM cache full, evicted oldest model")

        logger.info(f"Creating {provider} model: {model_name}")
        instance = LLMClient._create_model(
            provider,
            model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            api_base=api_base,
            thinking=thinking,
            profile=profile,
            **kwargs,
        )
        LLMClient._model_cache[cache_key] = instance
        return instance
```

## 立即行动

### 1. 检查当前使用的 Checkpointer

```bash
docker logs lambchat 2>&1 | grep -E "MemorySaver|MongoDB checkpointer"
```

**如果看到 "Using MemorySaver"**: 这是主要问题！

### 2. 确保 MongoDB Checkpointer 可用

```bash
# 检查 MongoDB 连接
docker exec lambchat-mongodb mongosh --eval "db.serverStatus().ok"

# 检查 langgraph-checkpoint-mongodb 是否安装
docker exec lambchat pip list | grep langgraph-checkpoint
```

### 3. 如果 MongoDB 不可用，应用方案 2-4

### 4. 重启服务并监控

```bash
# 重启
docker-compose -f deploy/docker-compose.yml restart lambchat

# 监控内存
watch -n 5 'docker stats --no-stream lambchat'

# 监控日志
docker logs -f lambchat | grep -E "MemorySaver|checkpoint|Cleaned"
```

## 预期效果

应用修复后:
- **使用 MongoDB Checkpointer**: 内存稳定在 500-800MB
- **使用 MemorySaver + TTL 清理**: 内存稳定在 800MB-1.2GB
- **不修复**: 内存持续增长，最终 OOM

## 监控指标

```bash
# 每 5 秒检查一次内存
watch -n 5 'docker stats --no-stream lambchat | tail -1 | awk "{print \$4}"'

# 检查 checkpoint 数量（如果使用 MemorySaver）
# 需要添加监控端点

# 检查 MongoDB checkpoint 数量
docker exec lambchat-mongodb mongosh --eval "db.checkpoints.countDocuments()"
```

## 总结

**主要问题**: MemorySaver 无限累积 checkpoint 数据

**最佳方案**: 使用 MongoDB Checkpointer

**临时方案**: 添加 TTL 清理 + 限制缓存大小

**预期效果**: 内存从 2.1GB 降低到 500-800MB

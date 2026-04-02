# LLM 模型缓存配置说明

## 问题背景

用户提出了一个很好的问题：如果限制为 10 个 BaseChatModel 实例，当有更多用户或参数组合时会怎样？

## 澄清误解

### LLMClient 是单例 ✅
```python
@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()  # 只有一个 LLMClient 实例
```

### 但缓存的是 BaseChatModel 实例（多个）
```python
class LLMClient:
    _model_cache: dict[tuple, BaseChatModel] = {}  # 类变量，缓存多个模型实例
```

## 实际使用场景分析

### 当前架构（共享 API Key）

从代码分析，所有用户共享同一个 `settings.LLM_API_KEY`，主要的参数组合来自：

1. **Agent 节点**: `(model, temperature, max_tokens)` = `(settings.LLM_MODEL, settings.LLM_TEMPERATURE, settings.LLM_MAX_TOKENS)`
2. **生成标题**: `(title_model, default_temp, 100)`
3. **Memory**: `(model, 0.1, max_tokens)`
4. **Middleware**: `(settings.LLM_MODEL, 0.3, 1500)`

**实际缓存数量**: 约 4-6 个实例

### 未来可能的场景

如果支持以下功能，缓存需求会增加：

1. **多租户**: 每个用户/组织有自己的 API key
   - 100 个用户 × 4 种参数组合 = 400 个实例
   
2. **动态参数**: 用户可以在前端选择不同的 temperature
   - 10 种 temperature × 其他参数 = 更多实例
   
3. **多模型**: 用户可以选择不同的模型
   - 5 种模型 × 其他参数 = 更多实例

## 解决方案

### 1. 可配置的缓存大小

**新增配置项**: `LLM_MODEL_CACHE_SIZE`

```python
# src/kernel/config/base.py
LLM_MODEL_CACHE_SIZE: int = 50  # 默认 50 个实例
```

### 2. 环境变量配置

```yaml
# docker-compose.yml
environment:
  - LLM_MODEL_CACHE_SIZE=50  # 可根据实际需求调整
```

### 3. 内存占用估算

| 缓存大小 | 内存占用 | 适用场景 |
|---------|---------|---------|
| 10 | 100-300MB | 单租户，固定参数 |
| 50 | 500MB-1.5GB | 多用户，少量参数变化（默认） |
| 100 | 1-3GB | 多租户，多参数组合 |
| 200 | 2-6GB | 大规模多租户 |

### 4. LRU 淘汰策略

当缓存满时，自动删除最旧的实例：

```python
if len(LLMClient._model_cache) >= max_cache_size:
    oldest_key = next(iter(LLMClient._model_cache))
    del LLMClient._model_cache[oldest_key]
    logger.info(f"LLM cache full ({max_cache_size}), evicted oldest model")
```

## 配置建议

### 场景 1: 单租户，固定参数（当前）
```bash
LLM_MODEL_CACHE_SIZE=10
```
- 内存占用: ~100-300MB
- 适用: 所有用户共享 API key，参数固定

### 场景 2: 多用户，少量参数变化（推荐）
```bash
LLM_MODEL_CACHE_SIZE=50  # 默认值
```
- 内存占用: ~500MB-1.5GB
- 适用: 多用户，但参数组合有限

### 场景 3: 多租户，多参数组合
```bash
LLM_MODEL_CACHE_SIZE=100
```
- 内存占用: ~1-3GB
- 适用: 每个用户有自己的 API key，或支持动态参数

### 场景 4: 大规模部署
```bash
LLM_MODEL_CACHE_SIZE=200
```
- 内存占用: ~2-6GB
- 适用: 大量用户，多种模型和参数组合

## 监控和调优

### 1. 查看缓存使用情况

```bash
# 查看缓存淘汰日志
docker logs lambchat | grep "LLM cache full"

# 如果频繁看到淘汰日志，说明缓存太小
```

### 2. 调整缓存大小

```bash
# 方法 1: 环境变量
export LLM_MODEL_CACHE_SIZE=100
docker-compose -f deploy/docker-compose.yml up -d

# 方法 2: 修改 docker-compose.yml
# environment:
#   - LLM_MODEL_CACHE_SIZE=100
```

### 3. 监控内存使用

```bash
# 实时监控
docker stats lambchat

# 如果内存持续增长，可能需要减小缓存
```

## 性能影响

### 缓存命中（快）
```
用户请求 → 查找缓存 → 返回已有实例
耗时: <1ms
```

### 缓存未命中（慢）
```
用户请求 → 创建新实例 → 建立连接 → 返回
耗时: 100-500ms
```

### 缓存淘汰（中等）
```
用户请求 → 删除最旧实例 → 创建新实例 → 返回
耗时: 100-500ms
```

## 最佳实践

### 1. 根据实际使用调整

```bash
# 启动后观察 1-2 天
docker logs lambchat | grep "LLM cache" | tail -20

# 如果看到频繁淘汰，增加缓存
# 如果内存占用过高，减小缓存
```

### 2. 平衡内存和性能

```
缓存太小 → 频繁创建/销毁 → 性能下降
缓存太大 → 内存占用高 → 可能 OOM
```

### 3. 推荐配置

```bash
# 小型部署（<100 用户）
LLM_MODEL_CACHE_SIZE=50

# 中型部署（100-1000 用户）
LLM_MODEL_CACHE_SIZE=100

# 大型部署（>1000 用户）
LLM_MODEL_CACHE_SIZE=200
```

## 总结

- **默认值 50**: 平衡内存和性能，适合大多数场景
- **可配置**: 通过环境变量灵活调整
- **LRU 淘汰**: 自动管理，防止无限增长
- **监控日志**: 根据实际使用调优

感谢用户的细心发现，这个改进让系统更加灵活和可扩展！

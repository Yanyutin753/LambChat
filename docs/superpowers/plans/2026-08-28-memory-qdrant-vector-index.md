# 记忆系统 Qdrant 向量索引层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给原生记忆系统接 Qdrant 作为专用 ANN 向量索引层（选型定案：Qdrant 单容器/嵌入式，轻量；Milvus standalone 需 etcd+MinIO 拓扑，单机 15G 内存不合身），Mongo 仍是唯一事实源，默认关闭零行为变化。

**Architecture:** 新增 `vector_store.py`（QdrantVectorIndex，写通/删除/检索三口）挂在 `MemoryBackend` 内；`search.py vector_search()` 增加分流：backend=qdrant 时 ANN 查 ids+score → Mongo 按 id 水合 → 复用既有 format/RRF。任何 Qdrant 故障静默降级回既有链路（$vectorSearch→余弦）。

**Tech Stack:** qdrant-client>=1.14（1.19，支持 `:memory:` 嵌入式与 AsyncQdrantClient）/ pymongo / 既有 settings 模式。

**Spec:** 本文档（自含设计；上承 `2026-08-27-memory-system-enhancement-design.md` 的 A3 分层路线与 2026-08-28 用户拍板：规模化接专门向量库）。

## Global Constraints

- **KV 缓存纪律不变**（本改动不触 prompt/消息链路）
- **Mongo 唯一事实源**：Qdrant 只是索引视图，可随时删库重建（backfill）
- 一切新行为默认关闭：`NATIVE_MEMORY_VECTOR_BACKEND` 默认 `"mongo"`（现行为）
- 测试零外部依赖：Qdrant 用 `:memory:` 嵌入式；CI 不需要容器
- settings 模式：base.py + _definitions_extra.py + i18n×5 + parity 测试
- 后端测试：`uv run pytest <path> -v`；提交信息 `feat(memory): ...` 中文

## 设计要点

**数据模型**（单 collection `native_memories`）：
- point id：memory_id（UUID hex → UUID）
- vector：embedding（维度 = NATIVE_MEMORY_EMBEDDING_DIMENSIONS，cosine）
- payload：`{user_id, memory_type, context, updated_at}`（检索过滤用，最小集）

**一致性顺序**：写=先 Mongo 后 Qdrant upsert；删=先 Mongo 后 Qdrant delete。漂移=漏出旧记忆（无害），backfill 修复。**降级链**：qdrant 异常 → log warning → 走既有 $vectorSearch/余弦路径（绝不阻塞主链路）。

**接线点**：`backend.retain()` 嵌入算完后写通；`backend.delete()` 删 Mongo 成功后删 Qdrant；`search.py vector_search()` 分流。`recall_memories` 及以上零改动。

**Task 1** 测试先行 `tests/infra/memory/native/test_vector_store.py`：collection 创建（维度/距离）/ 写检索回环 / user 隔离 / type+context 过滤 / 删除 / 故障返回 None
**Task 2** 实现 `src/infra/memory/client/native/vector_store.py`：QdrantVectorIndex + `get_vector_index()` 惰性单例（读设置；`:memory:` 支持测试注入）
**Task 3** 设置三件套：`NATIVE_MEMORY_VECTOR_BACKEND`（默认 mongo）、`NATIVE_MEMORY_QDRANT_URL`（默认 http://127.0.0.1:6333）、`NATIVE_MEMORY_QDRANT_API_KEY`（敏感）+ i18n + parity
**Task 4** 接线：retain 写通 / delete 删 / vector_search 分流水合（TDD：fake index 注入）
**Task 5** backfill 函数 + 测试（Mongo 存量 embedding 灌入 Qdrant，幂等 upsert）
**Task 6** 本地集成实测：`:memory:` 全链路 retain→recall + 降级演练；全量 pytest + lint + mypy

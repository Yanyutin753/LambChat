# Checkpoint 保留策略设计（2026-09-21 现状盘点）

## 现状（2026-09-21 实测）

- checkpointer = PG（`lamb-agent` 库），总 6.1GB：blobs 4.5G / writes 1.3G / checkpoints 224M
- 分布高度头部化：top 12 线程 ≈ 2.7GB（重会话每 step 写增量 blob，单条可达数百 KB~MB）
- 孤儿已清零：64 个已删会话遗留线程（~1MB）已用 `delete_checkpoints_for_thread` 清除
- 会话删除路径**已正确级联**清理 PG 线程（`SessionManager.delete_session`）
- 磁盘余量 314GB（35% 用量）——**不紧迫**
- 增长率参考：主要来自重会话（ginko 型），常态增速待 Grafana `LambChat PostgreSQL` 看板（db_size 面板）长期观察

## 约束（为什么不能随便删）

1. `fork from checkpoint` 是产品功能：session.checkpoints（用户锚定点）+ 任意历史 checkpoint
   都可能被用于 fork——**删了就永久失去对应 fork 点**
2. langgraph PG saver 的 blob 是按 version 的增量：最新状态 = 沿 parent 链折叠，
   **不支持删中间版本**（会断链）。官方只提供 `adelete_thread`（整线程删除）
3. 用户锚定 checkpoint（`SessionCheckpoint`）引用 PG 状态，TTL 必须豁免有线程锚点的会话

## 方案（按推荐排序）

### 方案 A：只监控不删（当前采用）
- Grafana `LambChat PostgreSQL` 看板盯 `pg_database_size_bytes` 增速
- patrol.sh 第 8 段每次巡检输出 db_size / dead_tup / seq_scan 突变
- 阈值参考：db_size > 30GB 或月增速 > 5GB 时再评估方案 B

### 方案 B：线程级 TTL（需产品确认后做成 PR）
- 规则：会话最后活跃 > 90 天 且 无用户锚定 checkpoint → 删整个 PG 线程
  （会话消息/trace 在 Mongo 仍完整可看，只失去老分支 resume/fork）
- 实现：arq 周期任务，遍历 `sessions.updated_at` 过期集合，
  查 `session_checkpoints` 无锚定 → `delete_checkpoints_for_thread`
- 配置：`CHECKPOINT_RETENTION_DAYS`（默认 0=关），system_settings 可调
- 测试：锚定豁免 / TTL 边界 / 与 delete_session 幂等共存

### 方案 C：磁盘扩容，无视增长
- 314GB 余量按当前增速可撑数年，成本为零；缺点是 dead_tup/膨胀会缓慢拖慢查询

## 已知无关项
- `checkpoint_blobs` 历史 2729 次顺序扫描：实测当前零增长（历史累积，建索引/诊断查询所致）
- autovacuum 正常（dead_tup 8.5k，占比极小）

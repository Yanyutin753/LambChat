# Agent 定时任务技术方案

本文档基于 APScheduler 设计 LambChat 的进程内定时任务系统。系统已在生产环境中运行，当前承载的核心任务是 Memory Compaction（记忆压缩）。本文档同时描述现有实现与后续扩展方向。

## 1. 设计目标

| 目标 | 说明 | 状态 |
| --- | --- | --- |
| 进程内调度 | 任务在主进程内异步执行，无需额外 Worker 进程 | ✅ 已实现 |
| 间隔任务 | 支持固定间隔或动态间隔的周期性任务 | ✅ 已实现 |
| 动态配置 | interval 和 enabled 支持运行时动态调整，无需重启 | ✅ 已实现 |
| Cron 任务 | 支持 cron 表达式的定时调度 | 🔜 规划中 |
| 手动触发 | 支持 API 或管理端立即执行某个任务 | ✅ 已实现 (`run_job_now`) |
| 任务持久化 | 任务配置和执行记录落库，重启后恢复 | 🔜 规划中 |
| 失败重试 | 任务执行失败后自动重试 | 🔜 规划中 |
| 多实例协调 | 多进程部署下通过 Redis 分布式锁防止重复执行 | ✅ 已实现（Memory Compaction 场景） |

## 2. 技术选型

### 2.1 为什么选择 APScheduler

| 方案 | 适用场景 | 与 LambChat 的匹配度 |
| --- | --- | --- |
| **APScheduler (当前)** | 进程内调度，轻量级，无外部依赖 | ✅ 高 — LambChat 是单进程应用，定时任务数量有限 |
| ff-arq / arq + Redis | 分布式任务队列，需要 Worker 进程和 Redis | ❌ 过重 — 引入额外进程和 Redis 队列依赖 |
| Celery | 大规模分布式任务队列 | ❌ 过重 — 同上 |
| asyncio.create_task + 自研 | 完全自控 | ⚠️ 需要自行实现 cron、重试、持久化等能力 |

**核心决策**：LambChat 的定时任务（Memory Compaction、后续的 Knowledge Base Sync 等）属于**低频、少量、进程内**的场景。APScheduler 提供了 interval / cron / date 三种触发器，支持任务持久化和重试，是当前阶段最合适的选择。

### 2.2 依赖

```text
apscheduler>=3.10           # 核心调度器（已引入）
redis                       # 分布式锁协调（已有依赖，非调度必须）
```

## 3. 总体架构

```text
┌─────────────────────────────────────────────────┐
│ LambChat Main Process                           │
│                                                 │
│  ┌──────────────┐     ┌──────────────────────┐  │
│  │ FastAPI App  │────▶│ RuntimeScheduler      │  │
│  │ / Admin UI   │     │ (APScheduler Facade)  │  │
│  └──────────────┘     │                       │  │
│                       │  ┌─ memory.compaction  │  │
│                       │  ├─ kb.sync (future)   │  │
│                       │  └─ report.daily (fut) │  │
│                       └──────────┬────────────┘  │
│                                  │               │
│                    ┌─────────────┼────────────┐  │
│                    ▼             ▼             ▼  │
│             ┌──────────┐ ┌──────────┐ ┌──────┐   │
│             │ Handler  │ │ Handler  │ │ ...  │   │
│             │ (async)  │ │ (async)  │ │      │   │
│             └────┬─────┘ └────┬─────┘ └──────┘   │
│                  │            │                    │
│                  ▼            ▼                    │
│          ┌──────────────────────────┐             │
│          │ Infra Services           │             │
│          │ LLM / DB / Redis / MCP   │             │
│          └──────────────────────────┘             │
└─────────────────────────────────────────────────┘
```

**与旧方案的关键差异**：不使用 Redis Queue 作为任务队列，不使用独立 Worker 进程。所有任务在主进程的 asyncio 事件循环中执行。对于需要多实例协调的场景（如 Memory Compaction 的周期扫描），通过 Redis 分布式锁实现。

## 4. 核心模块

### 4.1 ScheduledJob — 任务定义

```python
# src/infra/scheduler/runtime.py


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """A managed interval task."""

    id: str  # 任务唯一标识
    interval_seconds: int | Callable[[], int]  # 间隔秒数，支持动态
    handler: Callable[[], Awaitable[Any]]  # 异步执行函数
    enabled: bool | Callable[[], bool] = True  # 开关，支持动态
    name: str | None = None  # 显示名称
    max_instances: int = 1  # 最大并发实例
    coalesce: bool = True  # 错过的执行是否合并
    run_on_start: bool = False  # 启动时是否立即执行一次
```

**设计要点**：

- `frozen=True` 保证注册后不可变，避免运行时被意外修改。
- `interval_seconds` 和 `enabled` 支持传入 callable，允许任务根据运行时配置动态调整。每次执行结束后，调度器会检查 interval 是否变化并自动 reschedule。
- `handler` 是无参异步函数。需要参数的任务通过闭包或工厂函数捕获上下文。

### 4.2 RuntimeScheduler — 调度器

```python
# src/infra/scheduler/runtime.py


class RuntimeScheduler:
    """Small APScheduler facade for LambChat runtime services."""

    def register_interval_job(self, job: ScheduledJob) -> None:
        """注册或替换一个间隔任务。"""

    def start(self) -> None:
        """启动 APScheduler，添加所有已注册的任务。"""

    async def stop(self) -> None:
        """停止 APScheduler，不等待正在执行的任务。"""

    async def run_job_now(self, job_id: str) -> Any:
        """立即执行某个任务（主要用于测试和管理接口）。"""
```

**单例访问**：

```python
from src.infra.scheduler import get_runtime_scheduler

scheduler = get_runtime_scheduler()  # 进程内唯一实例
```

### 4.3 执行生命周期

```text
register_interval_job(job)
        │
        ▼
  start() 启动 APScheduler
        │
        ▼
  IntervalTrigger 触发
        │
        ▼
  _run_job(job)
    ├── _resolve_enabled → False? → 跳过，返回 {"skipped": True, "reason": "disabled"}
    ├── _resolve_enabled → True  → 执行 handler()
    │   ├── 成功 → 返回结果
    │   └── 异常 → 记录日志，抛出异常
    └── _refresh_interval_if_needed → 检查并更新间隔
```

### 4.4 动态配置刷新

调度器在每次任务执行完成后检查 interval 是否变化：

```python
def _refresh_interval_if_needed(self, job: ScheduledJob) -> None:
    next_interval = self._resolve_interval_seconds(job)
    current_interval = self._scheduled_intervals.get(job.id)
    if current_interval == next_interval:
        return
    self._scheduler.reschedule_job(
        job.id,
        trigger=IntervalTrigger(seconds=next_interval),
    )
    self._scheduled_intervals[job.id] = next_interval
```

这使得通过管理接口修改配置后，调度间隔会在下一次执行后自动生效，无需重启服务。

## 5. 现有任务：Memory Compaction

### 5.1 注册

```python
# src/infra/memory/tools.py


def start_memory_compaction_agent() -> None:
    if not settings.ENABLE_MEMORY:
        return

    agent = get_memory_compaction_agent()
    get_runtime_scheduler().register_interval_job(
        ScheduledJob(
            id="memory.compaction",
            name="Memory compaction",
            interval_seconds=agent.get_periodic_interval_seconds,  # callable: 动态间隔
            enabled=lambda: bool(settings.ENABLE_MEMORY) and agent.is_periodic_enabled(),
            handler=run_scheduled_memory_compaction,
        )
    )
```

### 5.2 Handler

```python
async def run_scheduled_memory_compaction() -> dict:
    backend = await _get_backend()
    if backend is None:
        return {"checked": 0, "triggered": 0, "skipped": 1, "reason": "backend_unavailable"}
    return await get_memory_compaction_agent().run_periodic_once(backend)
```

### 5.3 执行逻辑

`MemoryCompactionAgent.run_periodic_once()` 的核心流程：

```text
1. 获取分布式扫描锁 acquire_compaction_scan_lock（Redis，TTL = interval_seconds）
   └── 锁获取失败 → 跳过（说明其他实例正在执行）
2. 通过 MongoDB 聚合查询，找出 automatic 记忆数 ≥ threshold 的用户（最多 100 个）
3. 对每个用户：
   ├── 检查 Redis cooldown（默认 15 分钟内不重复）
   ├── 获取用户级 consolidation_lock
   ├── 调用 DeepAgent 执行压缩（合并/删除冗余记忆）
   └── 释放锁，标记 cooldown
```

### 5.4 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_MEMORY` | `False` | Memory 功能总开关 |
| `NATIVE_MEMORY_AUTO_COMPACT_ENABLED` | `True` | 压缩开关 |
| `NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD` | `40` | 触发压缩的最小记忆条数 |
| `NATIVE_MEMORY_AUTO_COMPACT_INTERVAL_SECONDS` | `43200` | 周期扫描间隔（12 小时） |
| `NATIVE_MEMORY_AUTO_COMPACT_MIN_INTERVAL_SECONDS` | `900` | 用户级冷却时间（15 分钟） |

### 5.5 生命周期

```python
# src/infra/runtime_services.py


async def start_runtime_services():
    ...
    start_memory_compaction_agent()  # 注册 job
    get_runtime_scheduler().start()  # 启动调度器
    ...


async def stop_runtime_services():
    ...
    await get_runtime_scheduler().stop()  # 停止调度器
    await memory_pubsub.stop_listener()
    await memory_shutdown()
    ...
```

## 6. 多实例部署下的协调

LambChat 可能以多进程方式部署（如 Uvicorn workers）。对于需要全局唯一执行的任务，调度器本身不做跨进程协调，而是将协调职责下放到具体任务的 handler 中。

### 6.1 推荐模式：分布式锁 + 幂等

以 Memory Compaction 为参考实现：

```text
进程 A: APScheduler 触发 → handler → acquire_scan_lock(Redis, TTL=interval) → 成功 → 执行
进程 B: APScheduler 触发 → handler → acquire_scan_lock(Redis, TTL=interval) → 失败 → 跳过
```

**关键点**：

- 每个进程的 APScheduler 都会触发，但只有获得锁的进程执行。
- 锁 TTL 设置为 `interval_seconds`，确保一个周期内只有一个实例执行。
- 对于用户级操作，额外使用 per-user cooldown 防止频繁执行。

### 6.2 各任务的协调策略

| 任务类型 | 协调方式 | 说明 |
| --- | --- | --- |
| Memory Compaction 周期扫描 | Redis scan_lock + per-user cooldown | 已实现 |
| Memory Compaction 写后触发 | Redis per-user lock + cooldown | 已实现（非调度器任务） |
| 知识库同步（未来） | Redis task_lock 或 DB 幂等键 | 规划中 |
| 日报生成（未来） | DB 幂等键（日期维度） | 规划中 |

## 7. 扩展计划

### 7.1 Cron 触发器支持

当前 `ScheduledJob` 仅支持 `IntervalTrigger`。后续可扩展支持 `CronTrigger`：

```python
@dataclass(frozen=True, slots=True)
class ScheduledJob:
    id: str
    trigger: IntervalTrigger | CronTrigger  # 通用触发器
    handler: Callable[[], Awaitable[Any]]
    enabled: bool | Callable[[], bool] = True
    ...
```

注册接口对应调整：

```python
def register_job(self, job: ScheduledJob) -> None:
    """注册任务，支持 interval 和 cron 两种触发类型。"""
```

### 7.2 任务持久化

APScheduler 原生支持 MongoDB / SQLAlchemy / Redis 等 JobStore。启用后任务配置可以在进程重启后自动恢复：

```python
from apscheduler.jobstores.mongodb import MongoDBJobStore

jobstore = MongoDBJobStore(
    host=settings.MONGODB_URI,
    database=settings.MONGODB_DATABASE,
    collection="apscheduler_jobs",
)
scheduler = AsyncIOScheduler(
    jobstores={"default": jobstore},
    timezone="UTC",
)
```

**适用场景**：当任务由用户动态创建（如"每周一 9 点执行 X Agent"），需要持久化而非代码硬编码时启用。

### 7.3 执行记录与重试

当前任务执行结果仅通过日志记录。后续可增加：

```python
@dataclass
class JobExecution:
    job_id: str
    run_id: str  # UUID
    status: str  # pending / running / success / failed
    started_at: datetime
    finished_at: datetime | None
    result: Any | None
    error_message: str | None
    retry_count: int = 0
```

重试策略：

```python
@dataclass(frozen=True, slots=True)
class ScheduledJob:
    ...
    max_retries: int = 0  # 最大重试次数
    retry_delay_seconds: int = 60  # 重试间隔
    retryable_exceptions: tuple[type[Exception], ...] | None = None
```

### 7.4 更多内置任务

| 任务 ID | 说明 | 触发类型 | 协调方式 |
| --- | --- | --- | --- |
| `memory.compaction` | 记忆压缩周期扫描 | interval | Redis scan_lock |
| `memory.compaction.write-back` | 写后触发压缩 | 事件（非调度） | Redis per-user lock |
| `kb.sync` | 知识库增量同步 | interval / cron | Redis task_lock |
| `report.daily` | 每日运行报告 | cron | DB 幂等键 |
| `agent.health_check` | Agent 健康检查 | interval | Redis task_lock |

## 8. 监控与日志

### 8.1 日志规范

所有调度器操作和任务执行都通过 `src.infra.logging` 记录，包含以下上下文：

```text
[Scheduler] registered job {job_id} interval={interval}s run_on_start={bool}
[Scheduler] started with {count} jobs
[Scheduler] scheduled job {job_id} every {interval}s
[Scheduler] job {job_id} failed: {error}
[Scheduler] stopped
```

任务 handler 内部应记录：

```text
[Memory] compaction scan: checked={count} triggered={count} skipped={count}
```

### 8.2 推荐监控指标

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `scheduler_job_total` | Counter | 任务触发总次数 |
| `scheduler_job_success_total` | Counter | 成功次数 |
| `scheduler_job_failed_total` | Counter | 失败次数 |
| `scheduler_job_skipped_total` | Counter | 跳过次数（disabled / lock 失败） |
| `scheduler_job_duration_seconds` | Histogram | 执行耗时 |
| `scheduler_job_interval_seconds` | Gauge | 当前间隔配置 |

### 8.3 告警规则

- 同一任务连续失败 ≥ 3 次。
- 单次执行耗时超过预期阈值。
- 定时任务超过 2 个周期未触发。
- 分布式锁获取失败率持续升高。

## 9. 目录结构

```text
src/infra/scheduler/
  __init__.py              # 导出 RuntimeScheduler, ScheduledJob, get_runtime_scheduler
  runtime.py               # 调度器核心实现

src/infra/memory/
  tools.py                 # start_memory_compaction_agent(), run_scheduled_memory_compaction()
  compaction_agent.py      # MemoryCompactionAgent — 压缩逻辑
  distributed.py           # Redis 分布式锁与协调

src/infra/
  runtime_services.py      # 启停编排

tests/infra/
  test_scheduler_runtime.py  # 调度器单元测试
```

后续扩展时按职责拆分：

```text
src/infra/scheduler/
  runtime.py               # RuntimeScheduler
  models.py                # ScheduledJob, JobExecution 等数据模型
  registry.py              # 所有任务的注册入口（替代散落在各模块的注册代码）
```

## 10. 与旧方案的对比

| 维度 | 旧方案 (ff-arq) | 新方案 (APScheduler) |
| --- | --- | --- |
| 架构 | Redis Queue + Worker 独立进程 | 进程内 asyncio 调度 |
| 部署 | api + worker + redis 三个进程 | 单进程（可选多 worker） |
| 依赖 | Redis（必须） | Redis（仅多实例协调时需要） |
| 复杂度 | 高 — 需要管理 Worker 生命周期 | 低 — 随主进程启停 |
| 扩展性 | 横向扩展 Worker 承载任务量 | 横向扩展通过分布式锁协调 |
| 适用场景 | 高频、大量、长耗时任务 | 低频、少量、进程内任务 |
| 任务持久化 | Redis 天然支持 | 需配置 APScheduler JobStore |
| 失败重试 | 队列内置 | 需在 handler 或调度器层实现 |

**结论**：LambChat 的定时任务规模（目前 1 个，规划中 3-5 个）不需要引入分布式任务队列的复杂度。APScheduler + Redis 分布式锁的组合在当前阶段提供足够的能力，且与现有代码架构一致。如果未来任务量增长到需要独立 Worker 承载的水平，可以平滑迁移到 ff-arq 方案。

## 11. 落地阶段

### 11.1 第一阶段：已实现 ✅

- APScheduler `RuntimeScheduler` 核心调度器。
- `ScheduledJob` 支持 interval 触发、动态 interval、动态 enabled。
- Memory Compaction 周期任务注册与执行。
- Redis 分布式锁协调多实例。
- 启停生命周期管理。

### 11.2 第二阶段：调度增强 🔜

- 支持 CronTrigger 触发器。
- `ScheduledJob` 统一 `trigger` 字段。
- 更多内置任务（kb.sync、report.daily 等）。
- 任务注册表（registry）统一管理。

### 11.3 第三阶段：可观测性 🔜

- 执行记录落库（`JobExecution` 模型）。
- Prometheus 监控指标。
- 任务失败重试机制。
- 管理接口（API 查看任务状态、手动触发）。

### 11.4 第四阶段：按需扩展

- APScheduler JobStore 持久化（支持用户动态创建任务）。
- 任务超时与限流。
- 告警集成。

---

## 12. 动态定时任务开发执行计划

### 12.1 目标概述

在现有 `RuntimeScheduler` 基础上，实现**用户可通过 API 动态创建、管理和执行定时任务**的完整能力：

- 用户创建定时任务（如"每周一 9 点用 Agent X 生成周报"），配置持久化到 MongoDB。
- 服务重启后自动恢复所有活跃任务。
- 每次执行的结果和状态被记录，可查询历史。
- 多实例部署下通过 Redis 分布式锁防重复。

### 12.2 整体数据流

```text
┌──────────────────────────────────────────────────────────────────┐
│ 用户 / 管理后台                                                   │
│  POST /api/scheduled-tasks   ← 创建任务                          │
│  POST /api/scheduled-tasks/{id}/run  ← 手动触发                  │
└───────────┬──────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│ ScheduledTaskService            │
│  1. 校验参数                     │
│  2. 写入 MongoDB                │
│  3. 注册到 RuntimeScheduler     │
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│ RuntimeScheduler (APScheduler)  │
│  CronTrigger / IntervalTrigger  │
│  到点触发 handler                │
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│ ScheduledTaskRunner             │
│  1. 获取分布式锁                  │
│  2. 创建执行记录                  │
│  3. 调用 BackgroundTaskManager  │
│  4. 记录执行结果                  │
└─────────────────────────────────┘
```

### 12.3 开发阶段与文件清单

```text
新增文件：
  src/kernel/schemas/scheduled_task.py    # 数据模型定义
  src/infra/scheduler/storage.py          # MongoDB 持久化
  src/infra/scheduler/service.py          # 业务逻辑层
  src/infra/scheduler/runner.py           # 任务执行引擎
  src/infra/scheduler/locks.py            # Redis 分布式锁
  src/api/routes/scheduled_task.py        # API 路由
  tests/infra/scheduler/
    test_storage.py
    test_service.py
    test_runner.py
    test_api.py

修改文件：
  src/infra/scheduler/runtime.py          # 扩展 Scheduler 支持 cron 和动态注册/注销
  src/infra/scheduler/__init__.py         # 导出新符号
  src/infra/runtime_services.py           # 启动时加载持久化任务
  src/api/main.py                         # 注册路由
```

---

### Step 1：数据模型定义

**文件**：`src/kernel/schemas/scheduled_task.py`

遵循项目现有的 Pydantic schema 模式（参考 `kernel/schemas/agent.py`）。

```python
"""Scheduled task schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class TriggerType(str, Enum):
    INTERVAL = "interval"
    CRON = "cron"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


# ── 触发配置 ──────────────────────────────────────


class IntervalTriggerConfig(BaseModel):
    """固定间隔触发。"""

    seconds: int = Field(..., ge=1, description="间隔秒数")


class CronTriggerConfig(BaseModel):
    """Cron 表达式触发，字段含义与标准 cron 一致。"""

    year: str | None = Field(None)
    month: str | None = Field(None)
    day: str | None = Field(None)
    week: str | None = Field(None)
    day_of_week: str | None = Field(None)
    hour: str | None = Field("0")
    minute: str | None = Field("0")
    second: str | None = Field("0")


# ── 任务模型 ──────────────────────────────────────


class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求。"""

    name: str = Field(..., min_length=1, max_length=200)
    agent_id: str = Field(..., min_length=1)
    trigger_type: TriggerType
    trigger_config: dict  # IntervalTriggerConfig | CronTriggerConfig
    input_payload: dict = Field(default_factory=dict, description="Agent 输入参数")
    description: str | None = Field(None, max_length=2000)
    enabled: bool = Field(True)
    run_on_start: bool = Field(False)
    max_retries: int = Field(0, ge=0, le=10)
    timeout_seconds: int = Field(600, ge=10, le=3600)


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    trigger_config: dict | None = None
    input_payload: dict | None = None
    description: str | None = None
    enabled: bool | None = None
    run_on_start: bool | None = None
    max_retries: int | None = Field(None, ge=0, le=10)
    timeout_seconds: int | None = Field(None, ge=10, le=3600)


class ScheduledTask(BaseModel):
    """MongoDB 持久化的完整任务文档。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    name: str
    description: str | None = None
    agent_id: str
    trigger_type: TriggerType
    trigger_config: dict
    input_payload: dict
    status: TaskStatus = TaskStatus.ACTIVE
    enabled: bool = True
    run_on_start: bool = False
    max_retries: int = 0
    timeout_seconds: int = 600
    owner_id: str = Field(..., description="创建者 user_id")
    last_run_at: datetime | None = None
    last_run_status: RunStatus | None = None
    last_run_id: str | None = None
    total_runs: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── 执行记录模型 ──────────────────────────────────


class TaskRunRecord(BaseModel):
    """单次执行记录。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id", description="run_id (UUID)")
    task_id: str
    agent_id: str
    trigger_type: str = Field("cron", description="触发方式: cron / interval / manual")
    status: RunStatus = RunStatus.PENDING
    input_snapshot: dict = Field(default_factory=dict)
    output_result: Any | None = None
    error_message: str | None = None
    retry_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None


# ── API 响应 ──────────────────────────────────────


class ScheduledTaskResponse(BaseModel):
    id: str
    name: str
    description: str | None
    agent_id: str
    trigger_type: TriggerType
    trigger_config: dict
    input_payload: dict
    status: TaskStatus
    enabled: bool
    run_on_start: bool
    max_retries: int
    timeout_seconds: int
    owner_id: str
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    total_runs: int
    created_at: datetime | None
    updated_at: datetime | None


class TaskRunResponse(BaseModel):
    id: str
    task_id: str
    agent_id: str
    trigger_type: str
    status: RunStatus
    input_snapshot: dict
    output_result: Any | None
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime | None


class TaskRunListResponse(BaseModel):
    items: list[TaskRunResponse]
    total: int
```

**交付标准**：
- ✅ Schema 可通过 Pydantic 校验
- ✅ `trigger_config` 使用 `dict` 存放，在 Service 层根据 `trigger_type` 做具体校验
- ✅ 与项目现有 schema 风格一致（`populate_by_name=True`、`Field(...)` 描述）

---

### Step 2：MongoDB 持久化层

**文件**：`src/infra/scheduler/storage.py`

遵循项目现有的 Storage 模式（参考 `infra/agent/config_storage.py`）。

```python
"""MongoDB storage for scheduled tasks and run records."""

from __future__ import annotations

from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.scheduled_task import (
    RunStatus,
    ScheduledTask,
    TaskRunRecord,
    TaskStatus,
)

logger = get_logger(__name__)

_COLL_TASKS = "scheduled_tasks"
_COLL_RUNS = "task_run_records"


class ScheduledTaskStorage:
    """MongoDB CRUD for scheduled task definitions."""

    def __init__(self) -> None:
        self._collections: dict[str, Any] = {}

    def _get_collection(self, name: str):
        if name not in self._collections:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collections[name] = db[name]
        return self._collections[name]

    async def ensure_indexes(self) -> None:
        c_tasks = self._get_collection(_COLL_TASKS)
        await c_tasks.create_index("owner_id")
        await c_tasks.create_index("status")
        await c_tasks.create_index([("status", 1), ("enabled", 1)])

        c_runs = self._get_collection(_COLL_RUNS)
        await c_runs.create_index("task_id")
        await c_runs.create_index("status")
        await c_runs.create_index("started_at")

    # ── Task CRUD ──────────────────────────────────

    async def create_task(self, task: ScheduledTask) -> ScheduledTask:
        doc = task.model_dump(by_alias=True)
        await self._get_collection(_COLL_TASKS).insert_one(doc)
        return task

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        doc = await self._get_collection(_COLL_TASKS).find_one({"_id": task_id})
        if not doc:
            return None
        return ScheduledTask(**doc)

    async def list_tasks(
        self,
        owner_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[ScheduledTask]:
        query: dict[str, Any] = {}
        if owner_id:
            query["owner_id"] = owner_id
        if status:
            query["status"] = status
        cursor = self._get_collection(_COLL_TASKS).find(query).sort("created_at", -1)
        return [ScheduledTask(**doc) async for doc in cursor]

    async def list_active_tasks(self) -> list[ScheduledTask]:
        """获取所有活跃且启用的任务（启动时加载用）。"""
        cursor = self._get_collection(_COLL_TASKS).find(
            {
                "status": TaskStatus.ACTIVE,
                "enabled": True,
            }
        )
        return [ScheduledTask(**doc) async for doc in cursor]

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        updates["updated_at"] = utc_now()
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {"$set": updates},
        )
        return result.modified_count > 0

    async def delete_task(self, task_id: str) -> bool:
        # 软删除：标记 status 为 deleted
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {"$set": {"status": TaskStatus.DELETED, "updated_at": utc_now()}},
        )
        return result.modified_count > 0

    async def update_task_run_stats(self, task_id: str, run_id: str, run_status: RunStatus) -> None:
        """任务执行完成后更新任务级统计。"""
        now = utc_now()
        await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {
                "$set": {
                    "last_run_at": now,
                    "last_run_status": run_status,
                    "last_run_id": run_id,
                    "updated_at": now,
                },
                "$inc": {"total_runs": 1},
            },
        )

    # ── Run Records ────────────────────────────────

    async def create_run(self, record: TaskRunRecord) -> TaskRunRecord:
        doc = record.model_dump(by_alias=True)
        await self._get_collection(_COLL_RUNS).insert_one(doc)
        return record

    async def get_run(self, run_id: str) -> Optional[TaskRunRecord]:
        doc = await self._get_collection(_COLL_RUNS).find_one({"_id": run_id})
        if not doc:
            return None
        return TaskRunRecord(**doc)

    async def update_run(self, run_id: str, updates: dict[str, Any]) -> bool:
        result = await self._get_collection(_COLL_RUNS).update_one(
            {"_id": run_id},
            {"$set": updates},
        )
        return result.modified_count > 0

    async def list_runs(
        self,
        task_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TaskRunRecord], int]:
        query = {"task_id": task_id}
        total = await self._get_collection(_COLL_RUNS).count_documents(query)
        cursor = (
            self._get_collection(_COLL_RUNS)
            .find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        records = [TaskRunRecord(**doc) async for doc in cursor]
        return records, total


# ── 单例 ──────────────────────────────────────────

_storage: Optional[ScheduledTaskStorage] = None


def get_scheduled_task_storage() -> ScheduledTaskStorage:
    global _storage
    if _storage is None:
        _storage = ScheduledTaskStorage()
    return _storage
```

**交付标准**：
- ✅ 遵循项目 Storage 模式（lazy collection、module singleton）
- ✅ 任务使用软删除（status=deleted），不做物理删除
- ✅ 执行记录支持分页查询
- ✅ `ensure_indexes()` 在 lifespan 中调用

---

### Step 3：扩展 RuntimeScheduler

**文件**：修改 `src/infra/scheduler/runtime.py`

当前 `RuntimeScheduler` 仅支持 `IntervalTrigger`，需要扩展以支持 `CronTrigger` 和动态注销。

#### 3.1 扩展 ScheduledJob

```python
# 在 runtime.py 中修改 ScheduledJob

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """A managed scheduled task."""

    id: str
    trigger: BaseTrigger | Callable[[], BaseTrigger]  # 新增：通用触发器
    handler: Callable[[], Awaitable[Any]]
    enabled: EnabledValue = True
    name: str | None = None
    max_instances: int = 1
    coalesce: bool = True
    run_on_start: bool = False

    # 兼容旧接口
    @classmethod
    def from_interval(
        cls,
        id: str,
        interval_seconds: IntervalValue,
        handler: Callable[[], Awaitable[Any]],
        **kwargs,
    ) -> "ScheduledJob":
        """从间隔秒数创建（兼容现有注册方式）。"""
        if callable(interval_seconds):
            trigger_fn = lambda: IntervalTrigger(  # noqa: E731
                seconds=max(1, int(interval_seconds()))
            )
            return cls(id=id, trigger=trigger_fn, handler=handler, **kwargs)
        return cls(
            id=id,
            trigger=IntervalTrigger(seconds=max(1, int(interval_seconds))),
            handler=handler,
            **kwargs,
        )
```

#### 3.2 扩展 RuntimeScheduler 方法

```python
class RuntimeScheduler:
    # ... 现有代码 ...

    # ── 兼容旧接口 ──

    def register_interval_job(self, job: "ScheduledJob") -> None:
        """兼容旧接口，委托给 register_job。"""
        self.register_job(job)

    # ── 新增方法 ──

    def register_job(self, job: ScheduledJob) -> None:
        """注册或替换一个任务（支持 interval 和 cron）。"""
        if not job.id:
            raise ValueError("scheduled job id is required")
        self._jobs[job.id] = job
        logger.info(
            "[Scheduler] registered job %s trigger=%s run_on_start=%s",
            job.id,
            type(job.trigger).__name__,
            job.run_on_start,
        )
        if self._scheduler is not None:
            self._add_or_replace_job(job)

    def unregister_job(self, job_id: str) -> None:
        """注销并移除一个任务。"""
        self._jobs.pop(job_id, None)
        self._scheduled_intervals.pop(job_id, None)
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(job_id)
            except JobLookupError:
                pass
        logger.info("[Scheduler] unregistered job %s", job_id)

    def has_job(self, job_id: str) -> bool:
        return job_id in self._jobs

    # ── 内部方法修改 ──

    def _resolve_trigger(self, job: ScheduledJob) -> BaseTrigger:
        """解析触发器，支持 callable 和静态值。"""
        trigger = job.trigger
        if callable(trigger):
            return trigger()
        return trigger

    def _add_or_replace_job(self, job: ScheduledJob) -> None:
        if self._scheduler is None:
            return
        trigger = self._resolve_trigger(job)
        self._scheduler.add_job(
            self._make_job_runner(job.id),
            trigger=trigger,
            id=job.id,
            name=job.name or job.id,
            replace_existing=True,
            coalesce=job.coalesce,
            max_instances=job.max_instances,
            **({"next_run_time": utc_now()} if job.run_on_start else {}),
        )
        logger.info(
            "[Scheduler] scheduled job %s with trigger=%s%s",
            job.id,
            type(trigger).__name__,
            " starting now" if job.run_on_start else "",
        )

    async def _run_job(self, job: ScheduledJob) -> Any:
        try:
            if not self._resolve_enabled(job):
                return {"skipped": True, "reason": "disabled"}
            result = await job.handler()
            return result
        except Exception as exc:
            logger.warning("[Scheduler] job %s failed: %s", job.id, exc)
            raise
        finally:
            self._refresh_trigger_if_needed(job)

    def _refresh_trigger_if_needed(self, job: ScheduledJob) -> None:
        """如果 trigger 是 callable，检查是否需要 reschedule。"""
        if self._scheduler is None:
            return
        if not callable(job.trigger):
            return
        # 只对 interval 类 callable 做动态刷新（cron 一般不需要）
        new_trigger = job.trigger()
        if isinstance(new_trigger, IntervalTrigger):
            # IntervalTrigger 的 interval 检测比较复杂，用简单方案
            self._scheduler.reschedule_job(job.id, trigger=new_trigger)
```

#### 3.3 更新 `__init__.py` 导出

```python
# src/infra/scheduler/__init__.py
from src.infra.scheduler.runtime import (
    RuntimeScheduler,
    ScheduledJob,
    get_runtime_scheduler,
)

__all__ = ["RuntimeScheduler", "ScheduledJob", "get_runtime_scheduler"]
```

#### 3.4 迁移现有 Memory Compaction 注册

```python
# src/infra/memory/tools.py — 修改 start_memory_compaction_agent


def start_memory_compaction_agent() -> None:
    """Register periodic memory compaction checks."""
    if not settings.ENABLE_MEMORY:
        return
    agent = get_memory_compaction_agent()
    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="memory.compaction",
            name="Memory compaction",
            interval_seconds=agent.get_periodic_interval_seconds,
            enabled=lambda: bool(settings.ENABLE_MEMORY) and agent.is_periodic_enabled(),
            handler=run_scheduled_memory_compaction,
        )
    )
```

**交付标准**：
- ✅ `ScheduledJob` 支持 `IntervalTrigger` 和 `CronTrigger`
- ✅ `register_interval_job` 向后兼容
- ✅ 新增 `unregister_job`、`has_job`
- ✅ Memory Compaction 注册方式平滑迁移，无需改动行为
- ✅ 现有 `test_scheduler_runtime.py` 全部通过

---

### Step 4：Redis 分布式锁

**文件**：`src/infra/scheduler/locks.py`

复用项目现有的 Redis 基础设施（参考 `infra/memory/distributed.py`）。

```python
"""Distributed locks for scheduled task execution."""

from __future__ import annotations

import uuid
from typing import Optional

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)

_LOCK_PREFIX = "scheduler:task_lock:"
_LOCK_TTL = 600  # 10 分钟默认 TTL


async def acquire_task_lock(
    task_id: str,
    run_id: str,
    ttl: int = _LOCK_TTL,
) -> Optional[str]:
    """
    尝试获取任务执行锁。

    返回 token（成功）或 None（失败，说明其他实例正在执行）。
    使用 SET NX EX 实现。
    """
    redis = get_redis()
    lock_key = f"{_LOCK_PREFIX}{task_id}"
    token = f"{run_id}:{uuid.uuid4().hex[:8]}"
    acquired = await redis.set(lock_key, token, nx=True, ex=ttl)
    if acquired:
        logger.debug("[Scheduler] acquired lock for task %s, run %s", task_id, run_id)
        return token
    logger.debug("[Scheduler] lock contested for task %s, skipping", task_id)
    return None


async def release_task_lock(task_id: str, token: str) -> None:
    """
    释放任务执行锁（仅当 token 匹配时才释放，防止误删其他实例的锁）。
    使用 Lua 脚本保证原子性。
    """
    redis = get_redis()
    lock_key = f"{_LOCK_PREFIX}{task_id}"
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    await redis.eval(lua, 1, lock_key, token)


async def extend_task_lock(task_id: str, token: str, extra_seconds: int = 300) -> bool:
    """延长锁 TTL，用于长时间执行的任务。"""
    redis = get_redis()
    lock_key = f"{_LOCK_PREFIX}{task_id}"
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    result = await redis.eval(lua, 1, lock_key, token, str(extra_seconds))
    return bool(result)
```

**交付标准**：
- ✅ 使用 SET NX EX 原子获取锁
- ✅ Lua 脚本原子释放（compare-and-delete）
- ✅ 支持锁续期（长任务场景）

---

### Step 5：任务执行引擎

**文件**：`src/infra/scheduler/runner.py`

这是核心模块——将 "APScheduler 触发" 和 "Agent 实际执行" 连接起来。

```python
"""Scheduled task execution engine."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.scheduler.locks import acquire_task_lock, release_task_lock
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.task.manager import get_task_manager
from src.infra.task.status import TaskStatus
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.scheduled_task import (
    RunStatus,
    ScheduledTask,
    TaskRunRecord,
)

logger = get_logger(__name__)


class ScheduledTaskRunner:
    """执行一个定时任务：获取锁 → 创建记录 → 执行 Agent → 记录结果。"""

    async def run(self, task_id: str, trigger_type: str = "cron") -> dict:
        """
        定时/手动触发入口。

        Returns: {"run_id": str, "status": str, ...}
        """
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            logger.warning("[Runner] task %s not found, skipping", task_id)
            return {"skipped": True, "reason": "task_not_found"}

        if not task.enabled or task.status != "active":
            return {"skipped": True, "reason": "disabled"}

        run_id = str(uuid.uuid4())

        # 1. 获取分布式锁（多实例防重复）
        lock_token = await acquire_task_lock(task_id, run_id, ttl=task.timeout_seconds)
        if lock_token is None:
            return {"skipped": True, "reason": "lock_contended", "run_id": run_id}

        # 2. 创建执行记录
        now = utc_now()
        record = TaskRunRecord(
            _id=run_id,
            task_id=task_id,
            agent_id=task.agent_id,
            trigger_type=trigger_type,
            status=RunStatus.PENDING,
            input_snapshot=task.input_payload,
            started_at=now,
            created_at=now,
        )
        await storage.create_run(record)

        # 3. 执行
        try:
            await storage.update_run(run_id, {"status": RunStatus.RUNNING})
            result = await self._execute_agent(task, run_id)

            finished = utc_now()
            duration = int((finished - now).total_seconds() * 1000)
            await storage.update_run(
                run_id,
                {
                    "status": RunStatus.SUCCESS,
                    "output_result": result,
                    "finished_at": finished,
                    "duration_ms": duration,
                },
            )
            await storage.update_task_run_stats(task_id, run_id, RunStatus.SUCCESS)
            return {"run_id": run_id, "status": "success", "result": result}

        except Exception as exc:
            finished = utc_now()
            duration = int((finished - now).total_seconds() * 1000)
            await storage.update_run(
                run_id,
                {
                    "status": RunStatus.FAILED,
                    "error_message": str(exc),
                    "finished_at": finished,
                    "duration_ms": duration,
                },
            )
            await storage.update_task_run_stats(task_id, run_id, RunStatus.FAILED)
            logger.exception("[Runner] task %s run %s failed", task_id, run_id)
            raise

        finally:
            await release_task_lock(task_id, lock_token)

    async def _execute_agent(self, task: ScheduledTask, run_id: str) -> dict:
        """
        调用 BackgroundTaskManager 执行 Agent。

        复用现有任务执行管线，在专用 session 中运行。
        """
        task_manager = get_task_manager()

        # 为定时任务创建专用 session
        session_id = f"sch_{task.id}_{run_id[:8]}"

        message = task.input_payload.get("message", "")
        if not message and task.input_payload.get("prompt"):
            message = task.input_payload["prompt"]

        _, trace_id = await task_manager.submit(
            session_id=session_id,
            agent_id=task.agent_id,
            message=message,
            user_id=task.owner_id,
            executor=None,  # 使用默认 executor
            disabled_tools=task.input_payload.get("disabled_tools"),
            agent_options=task.input_payload.get("agent_options"),
        )

        # 等待执行完成（简化方案：轮询状态）
        result = await self._wait_for_completion(task_manager, session_id, task.timeout_seconds)
        return result

    async def _wait_for_completion(
        self,
        task_manager,
        session_id: str,
        timeout_seconds: int,
    ) -> dict:
        """轮询等待任务完成（后续可优化为 event-based）。"""
        import asyncio

        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            status = await task_manager.get_status(session_id)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return {"session_status": status}
            await asyncio.sleep(2)

        return {"session_status": "timeout"}


# ── 单例 ──────────────────────────────────────────

_runner: Optional[ScheduledTaskRunner] = None


def get_scheduled_task_runner() -> ScheduledTaskRunner:
    global _runner
    if _runner is None:
        _runner = ScheduledTaskRunner()
    return _runner
```

**关于 Agent 执行方式的说明**：

当前方案通过 `BackgroundTaskManager.submit()` 复用现有执行管线。这意味着定时任务的 Agent 走的是和用户聊天相同的执行路径（session → agent graph → LLM → tools → 结果）。后续可考虑增加一个轻量级的 headless 执行路径，跳过 session/UI 相关的逻辑。

**交付标准**：
- ✅ 分布式锁 → 创建记录 → 执行 → 记录结果 → 释放锁
- ✅ 执行异常不影响后续调度
- ✅ 执行记录包含耗时统计
- ✅ 复用现有 `BackgroundTaskManager` 执行管线

---

### Step 6：业务逻辑层

**文件**：`src/infra/scheduler/service.py`

Service 层负责：校验 → 持久化 → 注册/注销调度器。是 API 和底层之间的桥梁。

```python
"""Scheduled task business logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.infra.logging import get_logger
from src.infra.scheduler.runtime import ScheduledJob, get_runtime_scheduler
from src.infra.scheduler.runner import get_scheduled_task_runner
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.scheduled_task import (
    CronTriggerConfig,
    IntervalTriggerConfig,
    RunStatus,
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
    TaskRunResponse,
    TaskStatus,
    TriggerType,
)

logger = get_logger(__name__)


class ScheduledTaskService:
    # ── CRUD ───────────────────────────────────────

    async def create_task(
        self,
        request: ScheduledTaskCreate,
        owner_id: str,
    ) -> ScheduledTask:
        """创建定时任务：校验 → 入库 → 注册调度器。"""
        # 1. 校验触发器配置
        trigger = self._build_trigger(request.trigger_type, request.trigger_config)

        # 2. 构建持久化文档
        now = utc_now()
        task_id = str(uuid4())
        task = ScheduledTask(
            _id=task_id,
            name=request.name,
            description=request.description,
            agent_id=request.agent_id,
            trigger_type=request.trigger_type,
            trigger_config=request.trigger_config,
            input_payload=request.input_payload,
            status=TaskStatus.ACTIVE,
            enabled=request.enabled,
            run_on_start=request.run_on_start,
            max_retries=request.max_retries,
            timeout_seconds=request.timeout_seconds,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )

        # 3. 入库
        storage = get_scheduled_task_storage()
        await storage.create_task(task)

        # 4. 注册到调度器
        self._register_to_scheduler(task)

        logger.info("[Service] created task %s for agent %s", task_id, request.agent_id)
        return task

    async def update_task(
        self, task_id: str, request: ScheduledTaskUpdate
    ) -> Optional[ScheduledTask]:
        """更新任务配置。"""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None

        updates: dict[str, Any] = {}
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                updates[field] = value

        if not updates:
            return task

        await storage.update_task(task_id, updates)

        # 重新加载并刷新调度器
        updated_task = await storage.get_task(task_id)
        if updated_task and updated_task.enabled and updated_task.status == TaskStatus.ACTIVE:
            self._register_to_scheduler(updated_task)
        else:
            get_runtime_scheduler().unregister_job(task_id)

        return updated_task

    async def pause_task(self, task_id: str) -> Optional[ScheduledTask]:
        """暂停任务：从调度器移除但保留配置。"""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None
        await storage.update_task(task_id, {"status": TaskStatus.PAUSED})
        get_runtime_scheduler().unregister_job(task_id)
        return await storage.get_task(task_id)

    async def resume_task(self, task_id: str) -> Optional[ScheduledTask]:
        """恢复任务：重新注册到调度器。"""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None
        await storage.update_task(task_id, {"status": TaskStatus.ACTIVE, "enabled": True})
        updated = await storage.get_task(task_id)
        if updated:
            self._register_to_scheduler(updated)
        return updated

    async def delete_task(self, task_id: str) -> bool:
        """软删除任务。"""
        get_runtime_scheduler().unregister_job(task_id)
        storage = get_scheduled_task_storage()
        return await storage.delete_task(task_id)

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return await get_scheduled_task_storage().get_task(task_id)

    async def list_tasks(
        self,
        owner_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[ScheduledTask]:
        return await get_scheduled_task_storage().list_tasks(owner_id=owner_id, status=status)

    # ── 执行 ───────────────────────────────────────

    async def run_task_now(self, task_id: str) -> dict:
        """手动触发任务执行。"""
        runner = get_scheduled_task_runner()
        return await runner.run(task_id, trigger_type="manual")

    async def get_task_runs(
        self, task_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list, int]:
        storage = get_scheduled_task_storage()
        records, total = await storage.list_runs(task_id, limit, offset)
        return [
            TaskRunResponse(
                id=r.id,
                task_id=r.task_id,
                agent_id=r.agent_id,
                trigger_type=r.trigger_type,
                status=r.status,
                input_snapshot=r.input_snapshot,
                output_result=r.output_result,
                error_message=r.error_message,
                retry_count=r.retry_count,
                started_at=r.started_at,
                finished_at=r.finished_at,
                duration_ms=r.duration_ms,
                created_at=r.created_at,
            )
            for r in records
        ], total

    # ── 启动加载 ────────────────────────────────────

    async def load_persisted_tasks(self) -> int:
        """启动时从 DB 加载所有活跃任务到调度器。"""
        storage = get_scheduled_task_storage()
        tasks = await storage.list_active_tasks()
        for task in tasks:
            self._register_to_scheduler(task)
        logger.info("[Service] loaded %d persisted tasks", len(tasks))
        return len(tasks)

    # ── 内部方法 ────────────────────────────────────

    def _register_to_scheduler(self, task: ScheduledTask) -> None:
        """将持久化任务注册到 APScheduler。"""
        trigger = self._build_trigger(task.trigger_type, task.trigger_config)
        runner = get_scheduled_task_runner()

        job = ScheduledJob(
            id=task.id,
            name=task.name,
            trigger=trigger,
            handler=lambda tid=task.id: runner.run(tid, trigger_type=task.trigger_type.value),
            enabled=task.enabled,
            run_on_start=task.run_on_start,
            max_instances=1,
            coalesce=True,
        )
        get_runtime_scheduler().register_job(job)

    @staticmethod
    def _build_trigger(trigger_type: TriggerType, config: dict) -> BaseTrigger:
        """根据配置构建 APScheduler Trigger。"""
        if trigger_type == TriggerType.INTERVAL:
            cfg = IntervalTriggerConfig(**config)
            return IntervalTrigger(seconds=cfg.seconds)
        elif trigger_type == TriggerType.CRON:
            cfg = CronTriggerConfig(**config)
            return CronTrigger(
                year=cfg.year,
                month=cfg.month,
                day=cfg.day,
                week=cfg.week,
                day_of_week=cfg.day_of_week,
                hour=cfg.hour,
                minute=cfg.minute,
                second=cfg.second,
                timezone="UTC",
            )
        else:
            raise ValueError(f"unsupported trigger type: {trigger_type}")
```

**交付标准**：
- ✅ 创建任务时同步注册到调度器
- ✅ 更新/暂停/恢复/删除时同步操作调度器
- ✅ 启动时从 DB 加载所有活跃任务
- ✅ 校验触发器配置合法性

---

### Step 7：API 路由

**文件**：`src/api/routes/scheduled_task.py`

遵循项目现有路由模式（参考 `api/routes/settings.py`）。

```python
"""Scheduled task API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_current_user_required
from src.infra.scheduler.service import ScheduledTaskService
from src.kernel.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
    TaskRunListResponse,
    TaskRunResponse,
    TaskStatus,
)

router = APIRouter()


def _to_response(task) -> ScheduledTaskResponse:
    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        agent_id=task.agent_id,
        trigger_type=task.trigger_type,
        trigger_config=task.trigger_config,
        input_payload=task.input_payload,
        status=task.status,
        enabled=task.enabled,
        run_on_start=task.run_on_start,
        max_retries=task.max_retries,
        timeout_seconds=task.timeout_seconds,
        owner_id=task.owner_id,
        last_run_at=task.last_run_at,
        last_run_status=task.last_run_status,
        total_runs=task.total_runs,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _get_service() -> ScheduledTaskService:
    return ScheduledTaskService()


@router.post("/", response_model=ScheduledTaskResponse, status_code=201)
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.create_task(body, owner_id=user.user_id)
    return _to_response(task)


@router.get("/", response_model=list[ScheduledTaskResponse])
async def list_scheduled_tasks(
    status: TaskStatus | None = None,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    tasks = await service.list_tasks(owner_id=user.user_id, status=status)
    return [_to_response(t) for t in tasks]


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: str,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_response(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: str,
    body: ScheduledTaskUpdate,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await service.update_task(task_id, body)
    return _to_response(updated)


@router.post("/{task_id}/pause", response_model=ScheduledTaskResponse)
async def pause_scheduled_task(
    task_id: str,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await service.pause_task(task_id)
    return _to_response(updated)


@router.post("/{task_id}/resume", response_model=ScheduledTaskResponse)
async def resume_scheduled_task(
    task_id: str,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = await service.resume_task(task_id)
    return _to_response(updated)


@router.delete("/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    await service.delete_task(task_id)


@router.post("/{task_id}/run", response_model=TaskRunResponse)
async def run_scheduled_task_now(
    task_id: str,
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await service.run_task_now(task_id)
    return result


@router.get("/{task_id}/runs", response_model=TaskRunListResponse)
async def list_task_runs(
    task_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_required),
    service: ScheduledTaskService = Depends(_get_service),
):
    task = await service.get_task(task_id)
    if task is None or task.owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    runs, total = await service.get_task_runs(task_id, limit, offset)
    return TaskRunListResponse(items=runs, total=total)
```

#### 注册路由到 main.py

在 `src/api/main.py` 中添加：

```python
from src.api.routes import scheduled_task

app.include_router(
    scheduled_task.router,
    prefix="/api/scheduled-tasks",
    tags=["Scheduled Tasks"],
)
```

**交付标准**：
- ✅ 完整的 CRUD + 手动触发 + 执行历史查询
- ✅ 权限校验：用户只能操作自己的任务
- ✅ 与项目现有路由风格一致

---

### Step 8：运行时集成

**文件**：修改 `src/infra/runtime_services.py`

#### 8.1 启动时加载持久化任务

```python
# src/infra/runtime_services.py

from src.infra.scheduler.service import ScheduledTaskService
from src.infra.scheduler.storage import get_scheduled_task_storage


async def start_runtime_services():
    ...
    # 现有代码：注册 memory compaction
    start_memory_compaction_agent()

    # 新增：加载持久化的动态任务
    storage = get_scheduled_task_storage()
    await storage.ensure_indexes()
    service = ScheduledTaskService()
    await service.load_persisted_tasks()

    # 现有代码：启动调度器
    get_runtime_scheduler().start()
    ...
```

#### 8.2 在 main.py lifespan 中初始化索引

在 `src/api/main.py` 的 `lifespan()` 函数中，与其他 storage 的 `ensure_indexes()` 一起调用：

```python
# 在 lifespan startup 阶段，storage indexes 初始化的位置
from src.infra.scheduler.storage import get_scheduled_task_storage

await get_scheduled_task_storage().ensure_indexes()
```

**交付标准**：
- ✅ 服务启动时自动加载并注册所有活跃任务
- ✅ MongoDB 索引在 lifespan 中创建
- ✅ 调度器停止逻辑不受影响

---

### Step 9：测试计划

**目录**：`tests/infra/scheduler/`

| 测试文件 | 覆盖内容 |
| --- | --- |
| `test_storage.py` | MongoDB CRUD：创建、查询、更新、软删除、执行记录、分页 |
| `test_service.py` | 业务逻辑：创建→注册、更新→重新注册、暂停→注销、恢复→重新注册、触发器校验 |
| `test_runner.py` | 执行引擎：分布式锁获取/释放、执行记录状态流转、超时处理、异常处理 |
| `test_api.py` | API 集成：CRUD 接口、权限校验（只能操作自己的任务）、手动触发、执行历史 |

**关键测试用例**：

```python
# test_service.py


async def test_create_interval_task_registers_to_scheduler():
    """创建 interval 任务后应同时注册到 APScheduler。"""
    service = ScheduledTaskService()
    task = await service.create_task(
        ScheduledTaskCreate(
            name="Test Task",
            agent_id="test_agent",
            trigger_type=TriggerType.INTERVAL,
            trigger_config={"seconds": 300},
            input_payload={"message": "hello"},
        ),
        owner_id="user_001",
    )
    assert get_runtime_scheduler().has_job(task.id)


async def test_pause_task_removes_from_scheduler():
    """暂停任务后应从 APScheduler 移除。"""
    # 创建 → 暂停 → 验证 scheduler 中不存在
    ...


async def test_load_persisted_tasks_on_startup():
    """启动时能正确加载 DB 中的活跃任务。"""
    # 插入 3 个活跃任务 + 1 个暂停任务 → 加载 → 验证只有 3 个注册到 scheduler
    ...


async def test_cron_trigger_validation():
    """Cron 触发器配置校验。"""
    # 合法配置 → 成功
    # 非法 cron 字段 → ValueError
    ...


# test_runner.py


async def test_runner_acquires_and_releases_lock():
    """执行前后分布式锁正确获取和释放。"""
    ...


async def test_runner_records_execution_result():
    """执行结果正确写入 task_run_records。"""
    ...


async def test_runner_skips_when_lock_contended():
    """锁被占用时跳过执行。"""
    ...
```

**交付标准**：
- ✅ 核心路径测试覆盖
- ✅ 可在 CI 中运行（mock MongoDB / Redis）

---

### 12.4 开发顺序与依赖关系

```text
Step 1: Schema ──────────────────────────── 无依赖，可独立开发
   │
   ▼
Step 2: Storage ─────────────────────────── 依赖 Step 1 (Schema)
   │
   ▼
Step 3: 扩展 Scheduler ─────────────────── 无依赖，可并行开发
   │
   ▼
Step 4: 分布式锁 ───────────────────────── 无依赖，可并行开发
   │
   ├─────────────────────────────────────────┐
   ▼                                         ▼
Step 5: Runner ──── 依赖 Step 2, 4       Step 9: 测试（逐步补充）
   │
   ▼
Step 6: Service ─── 依赖 Step 1-5
   │
   ▼
Step 7: API ─────── 依赖 Step 6
   │
   ▼
Step 8: 运行时集成 ── 依赖 Step 6, 7
```

**建议开发节奏**：

| 批次 | 内容 | 预估工作量 |
| --- | --- | --- |
| **第一批** | Step 1 (Schema) + Step 3 (Scheduler 扩展) + Step 4 (锁) | 0.5 天 |
| **第二批** | Step 2 (Storage) + Step 5 (Runner) | 1 天 |
| **第三批** | Step 6 (Service) + Step 7 (API) | 1 天 |
| **第四批** | Step 8 (集成) + Step 9 (测试) + 联调 | 1 天 |

总计约 **3-4 个工作日**。

### 12.5 API 接口总览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/scheduled-tasks` | 创建定时任务 |
| `GET` | `/api/scheduled-tasks` | 列出当前用户的任务 |
| `GET` | `/api/scheduled-tasks/{id}` | 获取任务详情 |
| `PUT` | `/api/scheduled-tasks/{id}` | 更新任务配置 |
| `POST` | `/api/scheduled-tasks/{id}/pause` | 暂停任务 |
| `POST` | `/api/scheduled-tasks/{id}/resume` | 恢复任务 |
| `DELETE` | `/api/scheduled-tasks/{id}` | 删除任务 |
| `POST` | `/api/scheduled-tasks/{id}/run` | 手动触发执行 |
| `GET` | `/api/scheduled-tasks/{id}/runs` | 查看执行历史 |

### 12.6 创建任务示例

#### 每小时执行一次

```json
POST /api/scheduled-tasks
{
  "name": "每小时知识库同步",
  "agent_id": "kb_sync_agent",
  "trigger_type": "interval",
  "trigger_config": { "seconds": 3600 },
  "input_payload": {
    "message": "检查并同步所有知识库的增量更新"
  }
}
```

#### 每周一早上 9 点执行

```json
POST /api/scheduled-tasks
{
  "name": "每周运营周报",
  "agent_id": "report_agent",
  "trigger_type": "cron",
  "trigger_config": {
    "day_of_week": "mon",
    "hour": "9",
    "minute": "0"
  },
  "input_payload": {
    "message": "生成本周运营数据报告"
  }
}
```

#### 每天固定时间检查

```json
POST /api/scheduled-tasks
{
  "name": "每日健康检查",
  "agent_id": "health_agent",
  "trigger_type": "cron",
  "trigger_config": {
    "hour": "8,20",
    "minute": "0"
  },
  "input_payload": {
    "message": "检查所有服务的运行状态并生成报告"
  },
  "timeout_seconds": 300
}
```

### 12.7 后续优化方向

本计划交付后，以下能力可按需迭代：

| 方向 | 说明 | 优先级 |
| --- | --- | --- |
| Headless 执行 | 跳过 session/UI，直接执行 Agent graph，减少开销 | P1 |
| 事件触发 | 任务不仅支持 cron/interval，还支持业务事件（新消息、新文件） | P1 |
| 失败重试 | 在 Runner 中增加 retry 逻辑，基于 `max_retries` 配置 | P1 |
| WebSocket 推送 | 任务执行状态变化时通过 WebSocket 通知前端 | P2 |
| Admin API | 管理员查看所有用户的任务、强制暂停/删除 | P2 |
| 执行结果通知 | 任务完成后通过飞书/邮件/通知渠道推送结果 | P3 |
| 任务模板 | 预定义常用任务模板，用户一键创建 | P3 |

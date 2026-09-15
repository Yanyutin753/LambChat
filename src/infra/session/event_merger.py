"""
Event Merger - 事件合并器

定期合并 trace 中的流式事件，减少事件数量，提升前后端性能。

合并策略:
- message:chunk 相邻合并；thinking 按 thinking_id、tool:args:chunk 按
  tool_call_id 分组归并到首现位置（并行子代理/并行工具调用的增量在
  事件流里交错，只按连续性合并对它们无效）
- 分组键与前端 part 路由语义一致，由 history_compaction 共享核心实现
- 不可合并的事件（如 tool:start）保持原位
- 合并后的事件标记为 merged=True，并记录 merged_count、started_at、ended_at
- 只合并 metadata.merged != True 的已完成 trace（status != "running"）

分布式支持:
- 使用 Redis SET NX EX 原子操作获取分布式锁，UUID 标识锁持有者
- 使用 Lua 脚本释放锁，确保只有持有锁的实例才能释放，避免误删
- 锁超时时间为合并间隔的 2 倍，防止死锁
- 使用 asyncio.timeout 防止单次合并操作超时（4 分钟）

批量处理:
- 每批最多处理 500 个 trace，使用投影查询减少数据传输
- 单批内并发合并（Semaphore 限制并发数为 10）
- 使用 pymongo bulk_write 批量写入，减少 DB 往返
"""

import asyncio
from typing import Any, Dict, List, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

logger = get_logger(__name__)

# 可合并的事件类型（实际分组/身份判定在 history_compaction 核心内）
MERGEABLE_EVENT_TYPES = frozenset(["message:chunk", "thinking", "tool:args:chunk"])

# 合并策略版本：旧版只做连续合并，交错流（并行子代理 thinking）收缩失败
# 也会标记 metadata.merged=True——按策略版本重新入队，让存量自愈
_MERGE_STRATEGY_GROUPED = "grouped"

# Redis 分布式锁配置
MERGE_LOCK_KEY = "event_merger:lock"

# 单次合并超时时间（秒）
MERGE_TIMEOUT = 120.0

# 每批处理的 trace 数量
BATCH_SIZE = 100

# 单批内并发合并的最大 trace 数量
_MERGE_CONCURRENCY = 3
_MERGE_TERMINAL_STATUSES = ("completed", "error")
_ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
_TRACE_EVENT_REVISION_FIELD = "event_revision"


def _get_merge_interval() -> float:
    """获取合并间隔"""
    return settings.EVENT_MERGE_INTERVAL


def _get_lock_timeout() -> int:
    """获取锁超时时间（合并间隔的 2 倍）"""
    return int(_get_merge_interval() * 2)


def _get_merge_timeout() -> float:
    return max(float(getattr(settings, "EVENT_MERGE_TIMEOUT_SECONDS", MERGE_TIMEOUT) or 0), 1.0)


def _get_immediate_merge_debounce_seconds() -> float:
    return max(
        float(getattr(settings, "EVENT_MERGE_IMMEDIATE_DEBOUNCE_SECONDS", 2.0) or 0),
        0.0,
    )


def _get_merge_batch_size() -> int:
    return max(int(getattr(settings, "EVENT_MERGE_BATCH_SIZE", BATCH_SIZE) or 0), 1)


def _get_merge_concurrency() -> int:
    return max(int(getattr(settings, "EVENT_MERGE_CONCURRENCY", _MERGE_CONCURRENCY) or 0), 1)


def _get_merge_max_events_per_trace() -> int:
    return max(int(getattr(settings, "EVENT_MERGE_MAX_EVENTS_PER_TRACE", 50000) or 0), 1)


class EventMerger:
    """
    事件合并器

    定期扫描已完成的 trace，合并连续的流式事件。
    支持分布式环境，使用 Redis 分布式锁。

    特性:
    - 非阻塞设计，不影响主事件循环
    - 超时保护，防止卡死
    - 批量处理，避免长时间占用资源
    - 分布式锁，确保只有一个实例执行合并
    """

    def __init__(self, trace_storage):
        self.trace_storage = trace_storage
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._merge_once_task: Optional[asyncio.Task] = None
        self._redis = None
        self._lock_value: Optional[str] = None  # 锁的唯一标识

    def start(self):
        """启动后台合并任务"""
        if self._running:
            return
        self._running = True
        if self._redis is None:
            # Use an isolated Redis pool for merger locks so background
            # lock traffic does not contend with long-lived shared listeners.
            self._redis = create_redis_client(isolated_pool=True)
        self._task = asyncio.create_task(self._merge_loop())
        self._task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        logger.info("EventMerger started with distributed lock support")

    async def stop(self):
        """停止后台合并任务，等待当前操作完成"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._merge_once_task and not self._merge_once_task.done():
            self._merge_once_task.cancel()
            try:
                await self._merge_once_task
            except asyncio.CancelledError:
                pass
        self._merge_once_task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("EventMerger stopped")

    def schedule_merge_once(self) -> None:
        """Request an immediate one-shot merge without blocking the caller."""
        if self._merge_once_task is not None and not self._merge_once_task.done():
            return
        self._merge_once_task = asyncio.create_task(self._debounced_merge_once())
        self._merge_once_task.add_done_callback(self._on_merge_once_task_done)

    def _on_merge_once_task_done(self, task: asyncio.Task) -> None:
        if self._merge_once_task is task:
            self._merge_once_task = None
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.warning("Immediate event merge failed: %s", exc)

    async def _debounced_merge_once(self) -> None:
        delay = _get_immediate_merge_debounce_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self.merge_once()

    async def merge_once(self) -> None:
        """Run one merge pass if this instance can acquire the distributed lock."""
        if not settings.ENABLE_EVENT_MERGER:
            return
        if not await self._acquire_lock():
            return
        try:
            merge_timeout = _get_merge_timeout()
            async with asyncio.timeout(merge_timeout):
                await self._merge_completed_traces()
        except TimeoutError:
            logger.warning(
                f"Immediate merge operation timed out after {merge_timeout}s, will retry later"
            )
        finally:
            await self._release_lock()

    async def _merge_loop(self):
        """后台合并循环 - 非阻塞设计，首次立即执行"""
        while self._running:
            try:
                await self.merge_once()

                # 等待到下一个合并时间点（放到循环末尾，首次立即执行）
                await asyncio.sleep(_get_merge_interval())
            except asyncio.CancelledError:
                logger.info("EventMerger loop cancelled, shutting down gracefully")
                break
            except Exception as e:
                logger.error(f"EventMerger loop error: {e}", exc_info=True)
                # 发生错误后等待一段时间再继续
                await asyncio.sleep(60)

    async def _acquire_lock(self) -> bool:
        """
        获取分布式锁

        使用 SET NX EX 原子操作获取锁，并生成唯一的锁标识。
        这样可以确保只有持有锁的实例才能释放锁。
        """
        if not self._redis:
            self._redis = create_redis_client(isolated_pool=True)

        try:
            import uuid

            # 生成唯一的锁标识
            self._lock_value = str(uuid.uuid4())

            # 使用 SET NX EX 原子操作获取锁
            result = await self._redis.set(
                MERGE_LOCK_KEY,
                self._lock_value,
                ex=_get_lock_timeout(),
                nx=True,
            )

            if result:
                logger.debug(f"Acquired merge lock with value: {self._lock_value[:8]}...")
                return True
            else:
                logger.debug("Lock already held by another instance")
                return False

        except Exception as e:
            logger.warning(f"Failed to acquire lock: {e}")
            return False

    async def _release_lock(self):
        """
        释放分布式锁

        使用 Lua 脚本确保只有持有锁的实例才能释放锁，避免误删其他实例的锁。
        """
        if not self._redis or not self._lock_value:
            return

        try:
            # 使用 Lua 脚本原子性地检查并删除锁
            # 只有当锁的值匹配时才删除
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            # 执行 Lua 脚本
            result = await self._redis.eval(lua_script, 1, MERGE_LOCK_KEY, self._lock_value)  # type: ignore[misc]

            if result == 1:
                logger.debug(f"Released merge lock with value: {self._lock_value[:8]}...")
            else:
                logger.debug("Lock was already released or taken by another instance")

            self._lock_value = None

        except Exception as e:
            logger.warning(f"Failed to release lock: {e}")
            self._lock_value = None

    async def _merge_completed_traces(self):
        """
        合并已完成的 traces - 批量处理，避免阻塞

        使用批量处理策略：
        1. 每批最多处理 BATCH_SIZE 个 trace
        2. 每批之间 yield 控制权，避免阻塞事件循环
        3. 使用 asyncio.gather 并发处理单个 trace
        4. 使用 bulk_write 批量写入数据库，减少 DB 往返
        """
        try:
            collection = self.trace_storage.collection
            recover_replacements = getattr(
                self.trace_storage,
                "recover_incomplete_chunk_replacements",
                None,
            )
            if callable(recover_replacements):
                await recover_replacements()

            # 查询最近完成的 traces（未合并的）
            # 使用投影减少数据传输
            batch_size = _get_merge_batch_size()
            max_events_per_trace = _get_merge_max_events_per_trace()
            cursor = collection.find(
                {
                    "status": {"$in": list(_MERGE_TERMINAL_STATUSES)},
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                    # （同一 dict 只能有一个 $or 键，两组条件用 $and 组合）
                    "$and": [
                        # 未合并过，或由旧策略标记过（交错流未被真正合掉）
                        {
                            "$or": [
                                {"metadata.merged": {"$ne": True}},
                                {"metadata.merge_strategy": {"$ne": _MERGE_STRATEGY_GROUPED}},
                            ]
                        },
                        {
                            "$or": [
                                {"event_count": {"$lte": max_events_per_trace}},
                                {"event_count": {"$exists": False}},
                            ]
                        },
                    ],
                },
                {
                    "_id": 1,
                    "trace_id": 1,
                    "session_id": 1,
                    "run_id": 1,
                    "started_at": 1,
                    "status": 1,
                    "updated_at": 1,
                    "event_count": 1,
                    _TRACE_EVENT_REVISION_FIELD: 1,
                    "metadata": 1,
                },
            ).limit(batch_size)

            trace_batch: list[dict[str, Any]] = []
            total_found = 0
            total_modified = 0
            total_merged = 0
            total_skipped = 0
            total_errors = 0
            process_batch_size = _get_merge_concurrency()

            async for trace in cursor:
                total_found += 1
                trace_batch.append(trace)
                if len(trace_batch) >= process_batch_size:
                    modified, merged, skipped, errors = await self._merge_trace_batch(
                        collection,
                        trace_batch,
                        concurrency=process_batch_size,
                    )
                    total_modified += modified
                    total_merged += merged
                    total_skipped += skipped
                    total_errors += errors
                    trace_batch.clear()
                    await asyncio.sleep(0)

            if trace_batch:
                modified, merged, skipped, errors = await self._merge_trace_batch(
                    collection,
                    trace_batch,
                    concurrency=process_batch_size,
                )
                total_modified += modified
                total_merged += merged
                total_skipped += skipped
                total_errors += errors
                trace_batch.clear()

            if not total_found:
                logger.debug("No traces to merge")
                return

            logger.info(
                "Merge batch completed: %s found, %s modified, %s merged, %s skipped, %s failed",
                total_found,
                total_modified,
                total_merged,
                total_skipped,
                total_errors,
            )

        except Exception as e:
            logger.error(f"Failed to merge completed traces: {e}", exc_info=True)

    async def _merge_trace_batch(
        self,
        collection: Any,
        traces: list[dict[str, Any]],
        *,
        concurrency: int,
    ) -> tuple[int, int, int, int]:
        if not traces:
            return 0, 0, 0, 0

        # 并发合并事件（纯 CPU，不涉及 IO），但只创建固定数量 worker。
        # 避免 backlog 较大时为整批 trace 一次性创建大量 coroutine。
        results = await self._process_trace_merges_bounded(
            traces,
            concurrency=concurrency,
        )

        try:
            # 收集 bulk_write 操作
            from pymongo import UpdateOne

            now = utc_now()
            operations = []
            merged_count = 0
            directly_modified_count = 0
            skipped_count = 0
            error_count = 0

            for r in results:
                if isinstance(r, BaseException):
                    error_count += 1
                    logger.warning(f"Failed to merge trace: {r}")
                    continue
                if r is None:
                    # events 为空的 trace 也需要标记为 merged，避免重复扫描
                    skipped_count += 1
                    continue

                trace_id, original_events, merged_events, trace_doc = (
                    r if len(r) == 4 else (r[0], r[1], r[2], {"trace_id": r[0]})
                )
                update_fields: Dict[str, Any] = {
                    "metadata.merged": True,
                    "metadata.merged_at": now,
                    "metadata.merge_strategy": _MERGE_STRATEGY_GROUPED,
                    "updated_at": now,
                }
                if len(merged_events) < len(original_events):
                    if getattr(settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False):
                        replaced = await self.trace_storage.replace_trace_events_with_chunks(
                            trace_doc,
                            merged_events,
                            parent_updates={
                                "metadata.merged": True,
                                "metadata.merged_at": now,
                                "metadata.merge_strategy": _MERGE_STRATEGY_GROUPED,
                            },
                        )
                        if not replaced:
                            skipped_count += 1
                            continue
                        directly_modified_count += 1
                        merged_count += 1
                        continue
                    else:
                        update_fields["events"] = merged_events
                        update_fields["event_count"] = len(merged_events)
                    merged_count += 1
                else:
                    skipped_count += 1

                update_query: Dict[str, Any] = {
                    "trace_id": trace_id,
                    "status": {"$in": list(_MERGE_TERMINAL_STATUSES)},
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                }
                if trace_doc.get("_id") is not None:
                    update_query["_id"] = trace_doc["_id"]
                if trace_doc.get("updated_at") is not None:
                    update_query["updated_at"] = trace_doc["updated_at"]
                operations.append(
                    UpdateOne(
                        update_query,
                        {
                            "$inc": {_TRACE_EVENT_REVISION_FIELD: 1},
                            "$set": update_fields,
                        },
                    )
                )

            if operations:
                bulk_result = await collection.bulk_write(operations, ordered=False)
                return (
                    directly_modified_count + bulk_result.modified_count,
                    merged_count,
                    skipped_count,
                    error_count,
                )
            return directly_modified_count, merged_count, skipped_count, error_count
        except Exception as e:
            logger.error(f"Failed to write merged traces: {e}", exc_info=True)
            return 0, 0, 0, len(traces)

    async def _process_trace_merges_bounded(
        self,
        traces: list[dict[str, Any]],
        *,
        concurrency: int,
    ) -> list[Any]:
        results: list[Any] = []
        next_index = 0
        lock = asyncio.Lock()
        worker_count = min(max(concurrency, 1), len(traces))

        async def _worker() -> None:
            nonlocal next_index
            while True:
                async with lock:
                    if next_index >= len(traces):
                        return
                    trace = traces[next_index]
                    next_index += 1
                try:
                    trace_id = trace.get("trace_id")
                    events = trace.get("events", [])
                    if (
                        not events
                        and trace_id
                        and hasattr(
                            self.trace_storage,
                            "read_trace_events_compat",
                        )
                    ):
                        events = await self.trace_storage.read_trace_events_compat(trace_id)
                    if not events:
                        results.append((trace_id, [], [], trace))
                        continue
                    merged_events = await run_blocking_io(self._merge_events, events)
                    results.append((trace_id, events, merged_events, trace))
                except Exception as exc:
                    results.append(exc)

        if worker_count:
            await asyncio.gather(*(_worker() for _ in range(worker_count)))
        return results

    def _merge_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并事件列表（委托 history_compaction 的共享核心）

        策略:
        - message:chunk / 无块标识旧数据：相邻同身份合并
        - thinking 按 thinking_id、tool:args:chunk 按 tool_call_id 分组归并
          到首现位置——并行子代理/并行工具调用的增量在流里交错，只按
          连续性合并对它们完全无效（生产实测单 run 1.7 万条 thinking
          事件因此未被合掉）。分组键与前端 part 路由语义一致，等价性
          由读取侧 compact_history_events 的真实数据回归保障
        - 归并目标标记 merged/merged_count/started_at/ended_at
        - 不可合并的事件（如 tool:start）保持原位
        """
        if not events:
            return []

        from src.infra.session.history_compaction import compact_history_events

        return compact_history_events(events, mark_merges=True)


# Singleton
_event_merger: Optional[EventMerger] = None


def get_event_merger(trace_storage) -> EventMerger:
    """获取 EventMerger 单例"""
    global _event_merger
    if _event_merger is None:
        _event_merger = EventMerger(trace_storage)
    return _event_merger


async def close_event_merger() -> None:
    """Stop and release the singleton EventMerger without creating it."""
    global _event_merger
    merger = _event_merger
    _event_merger = None
    if merger is not None:
        await merger.stop()

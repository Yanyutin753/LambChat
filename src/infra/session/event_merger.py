"""
Event Merger - 事件合并器

定期合并 trace 中的流式事件，减少事件数量，提升前后端性能。

合并策略:
- 按 (event_type, agent_id, depth, thinking_id, text_id) 合并连续的可合并事件（message:chunk, thinking）
- 只合并连续同 key 事件，避免把后续文本提前到中间的 tool/thinking 事件之前
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

# 可合并的事件类型
MERGEABLE_EVENT_TYPES = frozenset(["message:chunk", "thinking"])

# Redis 分布式锁配置
MERGE_LOCK_KEY = "event_merger:lock"

# 单次合并超时时间（秒）
MERGE_TIMEOUT = 120.0

# 每批处理的 trace 数量
BATCH_SIZE = 100

# 单批内并发合并的最大 trace 数量
_MERGE_CONCURRENCY = 3


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

            # 查询最近完成的 traces（未合并的）
            # 使用投影减少数据传输
            batch_size = _get_merge_batch_size()
            max_events_per_trace = _get_merge_max_events_per_trace()
            cursor = collection.find(
                {
                    "status": {"$ne": "running"},
                    "metadata.merged": {"$ne": True},
                    "$or": [
                        {"event_count": {"$lte": max_events_per_trace}},
                        {"event_count": {"$exists": False}},
                    ],
                },
                {
                    "trace_id": 1,
                    "session_id": 1,
                    "run_id": 1,
                    "started_at": 1,
                    "event_count": 1,
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
                    "updated_at": now,
                }
                if len(merged_events) < len(original_events):
                    if getattr(settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False):
                        await self.trace_storage.replace_trace_events_with_chunks(
                            trace_doc,
                            merged_events,
                        )
                    else:
                        update_fields["events"] = merged_events
                        update_fields["event_count"] = len(merged_events)
                    merged_count += 1
                else:
                    skipped_count += 1

                operations.append(UpdateOne({"trace_id": trace_id}, {"$set": update_fields}))

            if operations:
                bulk_result = await collection.bulk_write(operations, ordered=False)
                return bulk_result.modified_count, merged_count, skipped_count, error_count
            return 0, merged_count, skipped_count, error_count
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
        合并事件列表

        策略:
        - 按 (event_type, agent_id, depth, thinking_id, text_id) 合并连续的可合并事件
        - 保留原始时间线：遇到不可合并事件或 key 变化就结束当前合并段
        - 不可合并的事件（如 tool:start）保持原位
        """
        if not events:
            return []

        mergeable = MERGEABLE_EVENT_TYPES
        merged: list[Dict[str, Any]] = []
        current_key: Optional[tuple[Any, Any, Any, Any, Any]] = None
        current_group: list[Dict[str, Any]] = []

        def merge_key(event: Dict[str, Any]) -> Optional[tuple[Any, Any, Any, Any, Any]]:
            event_type = event.get("event_type")
            if event_type not in mergeable:
                return None
            data = event.get("data", {})
            return (
                event_type,
                data.get("agent_id"),
                data.get("depth"),
                data.get("thinking_id"),
                data.get("text_id"),
            )

        def flush_group() -> None:
            nonlocal current_key, current_group
            if current_group:
                merged.append(self._merge_group(current_group))
            current_key = None
            current_group = []

        for event in events:
            key = merge_key(event)
            if key is None:
                flush_group()
                merged.append(event)
                continue
            if current_group and key != current_key:
                flush_group()
            current_key = key
            current_group.append(event)

        flush_group()
        return merged

    def _merge_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        合并一组事件

        Args:
            group: 相同类型的连续事件列表

        Returns:
            合并后的事件
        """
        if len(group) == 1:
            return group[0]

        # 提取公共字段
        first = group[0]
        last = group[-1]
        event_type = first.get("event_type")
        first_data = first.get("data", {})

        # 合并 content（避免创建中间列表）
        parts: list[str] = []
        for event in group:
            data = event.get("data", {})
            content = data.get("content")
            if content:
                parts.append(content)

        # 构建合并后的事件
        merged_data = first_data.copy()
        merged_data["content"] = "".join(parts)
        merged_data["merged"] = True
        merged_data["merged_count"] = len(group)
        merged_data["started_at"] = first.get("timestamp")
        merged_data["ended_at"] = last.get("timestamp")

        return {
            "event_type": event_type,
            "data": merged_data,
            "timestamp": first.get("timestamp"),  # 使用第一个事件的时间戳
        }


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

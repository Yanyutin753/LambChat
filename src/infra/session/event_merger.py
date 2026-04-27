"""
Event Merger - 事件合并器

定期合并 trace 中的流式事件，减少事件数量，提升前后端性能。

合并策略:
- 按 (event_type, agent_id, depth, thinking_id, text_id) 分组合并可合并事件（message:chunk, thinking）
- 相同 key 的事件无论是否连续都会合并，支持并发子 agent 交叉事件场景
- 合并后的事件出现在该 key 首次出现的位置，不可合并的事件（如 tool:start）保持原位
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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client
from src.kernel.config import settings

logger = get_logger(__name__)

# 可合并的事件类型
MERGEABLE_EVENT_TYPES = frozenset(["message:chunk", "thinking"])

# Redis 分布式锁配置
MERGE_LOCK_KEY = "event_merger:lock"

# 单次合并超时时间（秒）- 设置为 4 分钟，留 1 分钟缓冲
MERGE_TIMEOUT = 240.0

# 每批处理的 trace 数量
BATCH_SIZE = 500

# 单批内并发合并的最大 trace 数量
_MERGE_CONCURRENCY = 10


def _get_merge_interval() -> float:
    """获取合并间隔"""
    return settings.EVENT_MERGE_INTERVAL


def _get_lock_timeout() -> int:
    """获取锁超时时间（合并间隔的 2 倍）"""
    return int(_get_merge_interval() * 2)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("EventMerger stopped")

    async def _merge_loop(self):
        """后台合并循环 - 非阻塞设计，首次立即执行"""
        while self._running:
            try:
                # 尝试获取分布式锁
                if await self._acquire_lock():
                    try:
                        # 使用 asyncio.timeout 防止合并操作超时
                        async with asyncio.timeout(MERGE_TIMEOUT):
                            await self._merge_completed_traces()
                    except TimeoutError:
                        logger.warning(
                            f"Merge operation timed out after {MERGE_TIMEOUT}s, will retry next round"
                        )
                    except Exception as e:
                        logger.error(f"Merge operation failed: {e}", exc_info=True)
                    finally:
                        # 确保释放锁
                        await self._release_lock()
                else:
                    logger.debug(
                        "Failed to acquire merge lock (another instance is merging), skipping this round"
                    )

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
            cursor = collection.find(
                {
                    "status": {"$ne": "running"},
                    "metadata.merged": {"$ne": True},
                },
                {"trace_id": 1, "events": 1},
            ).limit(BATCH_SIZE)

            traces = await cursor.to_list(length=BATCH_SIZE)

            if not traces:
                logger.debug("No traces to merge")
                return

            logger.info(f"Found {len(traces)} traces to merge")

            # 并发合并事件（纯 CPU，不涉及 IO）
            sem = asyncio.Semaphore(_MERGE_CONCURRENCY)

            async def _process(trace):
                async with sem:
                    trace_id = trace.get("trace_id")
                    events = trace.get("events", [])
                    if not events:
                        return (trace_id, [], [])
                    return (trace_id, events, self._merge_events(events))

            results = await asyncio.gather(*[_process(t) for t in traces], return_exceptions=True)

            # 收集 bulk_write 操作
            from pymongo import UpdateOne

            now = _utc_now()
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

                trace_id, original_events, merged_events = r
                update_fields: Dict[str, Any] = {
                    "metadata.merged": True,
                    "metadata.merged_at": now,
                    "updated_at": now,
                }
                if len(merged_events) < len(original_events):
                    update_fields["events"] = merged_events
                    update_fields["event_count"] = len(merged_events)
                    merged_count += 1
                else:
                    skipped_count += 1

                operations.append(UpdateOne({"trace_id": trace_id}, {"$set": update_fields}))

            if operations:
                bulk_result = await collection.bulk_write(operations, ordered=False)
                logger.info(
                    f"Merge batch completed: {bulk_result.modified_count} modified, "
                    f"{merged_count} merged, {skipped_count} skipped, {error_count} failed"
                )

        except Exception as e:
            logger.error(f"Failed to merge completed traces: {e}", exc_info=True)

    def _merge_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并事件列表

        策略:
        - 按 (event_type, agent_id, depth, thinking_id, text_id) 分组合并可合并事件
        - 相同 key 的事件无论是否连续都会合并（支持并发子 agent 交叉事件）
        - 保留原始顺序：合并后的事件出现在该 key 首次出现的位置
        - 不可合并的事件（如 tool:start）保持原位
        """
        if not events:
            return []

        # 第一轮：按 key 分组所有可合并事件，同时缓存 key 映射避免重复计算
        groups: dict[tuple[Any, Any, Any, Any, Any], List[Dict[str, Any]]] = {}
        key_cache: dict[
            int, Optional[tuple[Any, Any, Any, Any, Any]]
        ] = {}  # id(event) -> merge key or None
        mergeable = MERGEABLE_EVENT_TYPES

        for event in events:
            event_type = event.get("event_type")
            if event_type in mergeable:
                data = event.get("data", {})
                key = (
                    event_type,
                    data.get("agent_id"),
                    data.get("depth"),
                    data.get("thinking_id"),
                    data.get("text_id"),
                )
                key_cache[id(event)] = key
                group = groups.get(key)
                if group is None:
                    groups[key] = [event]
                else:
                    group.append(event)
            else:
                key_cache[id(event)] = None

        # 第二轮：按原始顺序输出，同 key 只在首次出现时输出合并结果
        merged = []
        seen_keys: set[tuple] = set()

        for event in events:
            cached_key = key_cache[id(event)]
            if cached_key is not None and cached_key not in seen_keys:
                seen_keys.add(cached_key)
                merged.append(self._merge_group(groups[cached_key]))
            elif cached_key is None:
                merged.append(event)

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

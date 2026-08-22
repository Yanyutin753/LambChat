"""Codex 式运行中插话（steer）消息队列。

使用 Redis 列表（多 worker 共享、带 24 小时 TTL）；默认 Redis 不可用时
直接失败，避免分布式部署静默降级为进程内队列。显式传入 ``redis=None``
时才启用带锁的进程内实现（用于本地开发和单元测试）。消息由
``SteerMiddleware`` 在下一次模型调用时取出注入并持久化到图状态。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from src.infra.logging import get_logger

logger = get_logger(__name__)
_UNSET = object()


@dataclass(slots=True, frozen=True)
class SteerItem:
    """Identity-bearing steer payload used across API, queue, and SSE."""

    id: str
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SteerQueue:
    """按会话隔离的插话消息队列（FIFO）。"""

    def __init__(self, redis: Any = _UNSET) -> None:
        self._pending: Dict[str, List[SteerItem]] = {}
        self._lock = asyncio.Lock()
        self._redis = None if redis is _UNSET else redis
        self._redis_disabled = redis is None
        self._redis_loop: asyncio.AbstractEventLoop | None = None
        self._lease_tokens: Dict[str, str] = {}

    def _key(self, session_id: str) -> str:
        return f"lambchat:steer:{session_id}"

    def _inflight_key(self, session_id: str) -> str:
        return f"{self._key(session_id)}:inflight"

    def _lease_key(self, session_id: str) -> str:
        return f"{self._key(session_id)}:lease"

    @staticmethod
    def _encode(item: SteerItem) -> str:
        return json.dumps(
            {
                "id": item.id,
                "content": item.content,
                "attachments": item.attachments,
                "created_at": item.created_at.isoformat(),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _decode(raw: str) -> SteerItem:
        value = json.loads(raw)
        return SteerItem(
            id=str(value["id"]),
            content=str(value["content"]),
            attachments=list(value.get("attachments") or []),
            created_at=datetime.fromisoformat(value["created_at"]),
        )

    async def _redis_or_none(self) -> Any | None:
        if self._redis_disabled:
            return None
        current_loop = asyncio.get_running_loop()
        if (
            self._redis is not None
            and self._redis_loop is not None
            and self._redis_loop is not current_loop
        ):
            # Async Redis connections are loop-bound; this also keeps tests
            # and short-lived worker loops from reusing a closed connection.
            self._redis = None
            self._lease_tokens.clear()
        if self._redis is not None:
            return self._redis
        try:
            from src.infra.storage.redis import create_redis_client

            client = create_redis_client(isolated_pool=True)
            await client.ping()
            self._redis = client
            self._redis_loop = current_loop
            return client
        except Exception as exc:
            if not self._redis_disabled:
                raise RuntimeError("SteerQueue requires Redis for distributed operation") from exc
            return None

    async def enqueue(self, session_id: str, message: str) -> int:
        """入队一条插话消息，返回该会话当前排队数。"""
        return await self.enqueue_item(
            session_id, SteerItem(id=f"steer-{uuid4().hex}", content=message)
        )

    async def enqueue_item(self, session_id: str, item: SteerItem) -> int:
        """入队；同一 ID 重试时保持幂等，不会重复注入。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                encoded = self._encode(item)
                result = await redis.eval(
                    """
                    local entries = redis.call('LRANGE', KEYS[1], 0, -1)
                    local inflight = redis.call('LRANGE', KEYS[2], 0, -1)
                    for _, raw in ipairs(inflight) do
                      local ok, value = pcall(cjson.decode, raw)
                      if ok and value['id'] == ARGV[1] then
                        return #entries
                      end
                    end
                    for _, raw in ipairs(entries) do
                      local ok, value = pcall(cjson.decode, raw)
                      if ok and value['id'] == ARGV[1] then
                        return #entries
                      end
                    end
                    redis.call('RPUSH', KEYS[1], ARGV[2])
                    redis.call('EXPIRE', KEYS[1], ARGV[3])
                    return #entries + 1
                    """,
                    2,
                    key,
                    self._inflight_key(session_id),
                    item.id,
                    encoded,
                    "86400",
                )
                return int(result)
            except Exception:
                logger.warning("[Steer] Redis enqueue failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            queue = self._pending.setdefault(session_id, [])
            if any(existing.id == item.id for existing in queue):
                return len(queue)
            queue.append(item)
            logger.info("[Steer] session=%s queued message (%d pending)", session_id, len(queue))
            return len(queue)

    async def drain(self, session_id: str) -> List[str]:
        """取出并清空该会话的全部排队消息（FIFO）。"""
        items = await self.drain_items(session_id)
        # Legacy callers treat drain as consume-and-ack. The middleware uses
        # drain_items directly so it can requeue on model failure.
        await self.ack_items(session_id)
        return [item.content for item in items]

    async def drain_items(self, session_id: str) -> List[SteerItem]:
        """取出带 ID 的消息；领取与清空在同一锁内完成。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                token = self._lease_tokens.get(session_id) or uuid4().hex
                raw_items = await redis.eval(
                    """
                    local pending = redis.call('EXISTS', KEYS[1])
                    local inflight = redis.call('EXISTS', KEYS[2])
                    local owner = redis.call('GET', KEYS[3])
                    if pending == 0 and inflight == 0 then
                      return {}
                    end
                    if owner and owner ~= ARGV[2] then
                      return {}
                    end
                    if not owner then
                      redis.call('SET', KEYS[3], ARGV[2], 'EX', ARGV[1])
                    else
                      redis.call('EXPIRE', KEYS[3], ARGV[1])
                    end
                    if inflight == 0 and pending == 1 then
                      redis.call('RENAME', KEYS[1], KEYS[2])
                      redis.call('EXPIRE', KEYS[2], ARGV[1])
                    end
                    local result = {ARGV[2]}
                    for _, raw in ipairs(redis.call('LRANGE', KEYS[2], 0, -1)) do
                      table.insert(result, raw)
                    end
                    return result
                    """,
                    3,
                    self._key(session_id),
                    self._inflight_key(session_id),
                    self._lease_key(session_id),
                    "3600",
                    token,
                )
                if not raw_items:
                    return []
                self._lease_tokens[session_id] = str(raw_items[0])
                messages = [self._decode(raw) for raw in raw_items[1:]]
                if messages:
                    logger.info(
                        "[Steer] session=%s draining %d message(s)", session_id, len(messages)
                    )
                return messages
            except Exception:
                logger.warning("[Steer] Redis drain failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            messages = self._pending.pop(session_id, [])
            if messages:
                logger.info("[Steer] session=%s draining %d message(s)", session_id, len(messages))
            return messages

    async def list_items(self, session_id: str) -> List[SteerItem]:
        """读取 pending/inflight 项，用于刷新后恢复 composer queue。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                raw_items = await redis.lrange(self._key(session_id), 0, -1)
                raw_items += await redis.lrange(self._inflight_key(session_id), 0, -1)
                items: list[SteerItem] = []
                seen: set[str] = set()
                for raw in raw_items:
                    item = self._decode(raw)
                    if item.id not in seen:
                        seen.add(item.id)
                        items.append(item)
                return items
            except Exception:
                logger.warning("[Steer] Redis list failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            return list(self._pending.get(session_id, []))

    async def requeue_front(self, session_id: str, messages: List[str]) -> None:
        """把消息放回队首（用于注入失败后恢复排队，保持 FIFO 送达顺序）。"""
        if not messages:
            return
        items = [SteerItem(id=f"steer-{uuid4().hex}", content=message) for message in messages]
        await self.requeue_front_items(session_id, items)

    async def requeue_front_items(self, session_id: str, messages: List[SteerItem]) -> None:
        """带 ID 回滚，避免模型调用失败后产生新 ID。"""
        if not messages:
            return
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                inflight = self._inflight_key(session_id)
                lease = self._lease_key(session_id)
                token = self._lease_tokens.get(session_id)
                if not token:
                    return
                result = await redis.eval(
                    """
                    if redis.call('GET', KEYS[3]) ~= ARGV[1] then return 0 end
                    local values = cjson.decode(ARGV[2])
                    for i = #values, 1, -1 do
                      redis.call('LPUSH', KEYS[1], values[i])
                    end
                    redis.call('DEL', KEYS[2], KEYS[3])
                    redis.call('EXPIRE', KEYS[1], ARGV[3])
                    return 1
                    """,
                    3,
                    key,
                    inflight,
                    lease,
                    token,
                    json.dumps([self._encode(item) for item in messages]),
                    "86400",
                )
                if int(result) == 1:
                    self._lease_tokens.pop(session_id, None)
                else:
                    logger.warning(
                        "[Steer] session=%s lease lost before requeue; leaving inflight for recovery",
                        session_id,
                    )
                return
            except Exception:
                logger.warning("[Steer] Redis requeue failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            queue = self._pending.setdefault(session_id, [])
            queue[:0] = messages
            logger.info(
                "[Steer] session=%s requeued %d message(s) after failed delivery",
                session_id,
                len(messages),
            )

    async def ack_items(self, session_id: str) -> None:
        """确认本次模型调用成功，释放 Redis lease。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                token = self._lease_tokens.get(session_id)
                if not token:
                    return
                result = await redis.eval(
                    """
                    if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
                    redis.call('DEL', KEYS[1], KEYS[2])
                    return 1
                    """,
                    2,
                    self._inflight_key(session_id),
                    self._lease_key(session_id),
                    token,
                )
                if int(result) == 1:
                    self._lease_tokens.pop(session_id, None)
            except Exception:
                logger.warning("[Steer] Redis ack failed", exc_info=True)
                if not self._redis_disabled:
                    raise

    async def clear_session(self, session_id: str) -> None:
        """清空该会话全部插话状态（pending / inflight / lease）。

        新 run 提交时调用：旧 run 结束后残留的插话已由前端补发为普通
        消息，若不清理，新 run 的首次模型调用会把同一条插话再次注入
        （重复投递）。Redis 路径单次 DEL 三个键，多 worker 共享状态下
        原子生效；正被某次模型调用持有（inflight）的项被清后，该调用
        结束时的 ack/requeue 会因 lease 不匹配而自然空转，无副作用。
        """
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                await redis.delete(
                    self._key(session_id),
                    self._inflight_key(session_id),
                    self._lease_key(session_id),
                )
                self._lease_tokens.pop(session_id, None)
                return
            except Exception:
                logger.warning("[Steer] Redis clear failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            self._pending.pop(session_id, None)
            self._lease_tokens.pop(session_id, None)

    def pending_count(self, session_id: str) -> int:
        """该会话当前排队数（只读，用于观测）。"""
        return len(self._pending.get(session_id, []))

    async def remove(self, session_id: str, message: str) -> bool:
        """移除该会话中排队的第一条相同内容消息（用户取消插话）。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                raw_items = await redis.lrange(key, 0, -1)
                for raw in raw_items:
                    if self._decode(raw).content == message:
                        return bool(await redis.lrem(key, 1, raw))
                return False
            except Exception:
                logger.warning("[Steer] Redis remove failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            queue = self._pending.get(session_id)
            if not queue:
                return False
            for index, queued in enumerate(queue):
                if queued.content == message:
                    del queue[index]
                    logger.info("[Steer] session=%s cancelled one queued message", session_id)
                    return True
            return False

    async def remove_by_id(self, session_id: str, message_id: str) -> bool:
        """只取消指定 ID，保证相同文本的消息互不影响。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                raw_items = await redis.lrange(key, 0, -1)
                for raw in raw_items:
                    if self._decode(raw).id == message_id:
                        return bool(await redis.lrem(key, 1, raw))
                return False
            except Exception:
                logger.warning("[Steer] Redis ID remove failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            queue = self._pending.get(session_id)
            if not queue:
                return False
            for index, queued in enumerate(queue):
                if queued.id == message_id:
                    del queue[index]
                    if not queue:
                        self._pending.pop(session_id, None)
                    logger.info("[Steer] session=%s cancelled message=%s", session_id, message_id)
                    return True
            return False


_steer_queue: SteerQueue | None = None


async def purge_stale_steers(session_id: str) -> None:
    """新 run 开始前清空该会话残留的插话队列（尽力而为，失败只记日志）。

    旧 run 结束后未被注入的插话已由前端补发为普通消息；若不清理，
    新 run 的首次模型调用会把同一条插话再次注入（重复投递）。
    """
    try:
        await get_steer_queue().clear_session(session_id)
    except Exception:
        logger.warning(
            "[Steer] session=%s failed to purge stale steers before new run",
            session_id,
            exc_info=True,
        )


def get_steer_queue() -> SteerQueue:
    """进程内单例。"""
    global _steer_queue
    if _steer_queue is None:
        _steer_queue = SteerQueue()
    return _steer_queue

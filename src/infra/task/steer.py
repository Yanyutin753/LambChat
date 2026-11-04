"""Codex 式运行中插话（steer）消息队列。

使用 Redis 列表（多 worker 共享、带 24 小时 TTL）；默认 Redis 不可用时
直接失败，避免分布式部署静默降级为进程内队列。显式传入 ``redis=None``
时才启用带锁的进程内实现（用于本地开发和单元测试）。消息由
``SteerMiddleware`` 在下一次模型调用时取出注入并持久化到图状态。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from src.infra.logging import get_logger

logger = get_logger(__name__)
_UNSET = object()
_STEER_TTL_SECONDS = 86400
CANCELLED_STEER = -1
DELIVERED_STEER = -2
_LIVE_RECEIPTS_LUA = """
local function live_receipts(key, now)
  local live = {}
  for _, raw in ipairs(redis.call('LRANGE', key, 0, -1)) do
    local ok, value = pcall(cjson.decode, raw)
    if ok and tonumber(value['receipt_expires_at'] or 0) > now then
      table.insert(live, raw)
    else
      redis.call('LREM', key, 1, raw)
    end
  end
  return live
end
"""


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
        self._cancelled: dict[tuple[str, str], float] = {}
        self._inflight: dict[str, list[SteerItem]] = {}
        self._receipts: dict[str, dict[str, tuple[SteerItem, float]]] = {}

    def _key(self, session_id: str) -> str:
        return f"lambchat:steer:{session_id}"

    def _inflight_key(self, session_id: str) -> str:
        return f"{self._key(session_id)}:inflight"

    def _lease_key(self, session_id: str) -> str:
        return f"{self._key(session_id)}:lease"

    def _cancelled_key(self, session_id: str, message_id: str) -> str:
        return f"{self._key(session_id)}:cancelled:{message_id}"

    def _receipts_key(self, session_id: str) -> str:
        return f"{self._key(session_id)}:receipts"

    def _live_memory_receipts(self, session_id: str) -> dict[str, tuple[SteerItem, float]]:
        now = time.time()
        live = {
            key: item for key, item in self._receipts.get(session_id, {}).items() if item[1] > now
        }
        if live:
            self._receipts[session_id] = live
        else:
            self._receipts.pop(session_id, None)
        return live

    def _prune_cancelled(self) -> None:
        now = time.monotonic()
        self._cancelled = {key: until for key, until in self._cancelled.items() if until > now}

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

    async def settled_outcome(self, session_id: str, message_id: str) -> str | None:
        """Read an existing receipt/withdrawal without admitting or mutating a message."""
        redis = await self._redis_or_none()
        if redis is not None:
            result = await redis.eval(
                """
                for _, raw in ipairs(redis.call('LRANGE', KEYS[1], 0, -1)) do
                  local value = cjson.decode(raw)
                  if value['id'] == ARGV[1]
                    and tonumber(value['receipt_expires_at'] or 0) > tonumber(ARGV[2]) then
                    return -2
                  end
                end
                if redis.call('EXISTS', KEYS[2]) == 1 then return -1 end
                return 0
                """,
                2,
                self._receipts_key(session_id),
                self._cancelled_key(session_id, message_id),
                message_id,
                str(time.time()),
            )
            return {DELIVERED_STEER: "delivered", CANCELLED_STEER: "cancelled"}.get(int(result))
        async with self._lock:
            receipt = self._receipts.get(session_id, {}).get(message_id)
            if receipt is not None and receipt[1] > time.time():
                return "delivered"
            if self._cancelled.get((session_id, message_id), 0) > time.monotonic():
                return "cancelled"
            return None

    async def enqueue_item(self, session_id: str, item: SteerItem) -> int:
        """入队；未消费的同 ID 去重，已撤回的 ID 返回 CANCELLED_STEER。

        撤回记录与队列共用 24 小时保留期；新的用户发送必须使用新 ID。
        """
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                encoded = self._encode(item)
                result = await redis.eval(
                    _LIVE_RECEIPTS_LUA
                    + """
                    for _, raw in ipairs(live_receipts(KEYS[4], tonumber(ARGV[4]))) do
                      if cjson.decode(raw)['id'] == ARGV[1] then return -2 end
                    end
                    if redis.call('EXISTS', KEYS[3]) == 1 then return -1 end
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
                    4,
                    key,
                    self._inflight_key(session_id),
                    self._cancelled_key(session_id, item.id),
                    self._receipts_key(session_id),
                    item.id,
                    encoded,
                    str(_STEER_TTL_SECONDS),
                    str(time.time()),
                )
                return int(result)
            except Exception:
                logger.warning("[Steer] Redis enqueue failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            self._prune_cancelled()
            if item.id in self._live_memory_receipts(session_id):
                return DELIVERED_STEER
            if (session_id, item.id) in self._cancelled:
                return CANCELLED_STEER
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
        if items and not await self.ack_items(session_id):
            raise RuntimeError("Steer delivery lease lost before acknowledgement")
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
                    end
                    -- Payload must outlive an abandoned lease so another worker can recover it.
                    redis.call('EXPIRE', KEYS[2], ARGV[3])
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
                    str(_STEER_TTL_SECONDS),
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
            messages = self._inflight.get(session_id) or self._pending.pop(session_id, [])
            if messages:
                self._inflight[session_id] = messages
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
            return list(self._pending.get(session_id, [])) + list(
                self._inflight.get(session_id, [])
            )

    async def list_receipts(self, session_id: str) -> list[SteerItem]:
        """Retain acknowledged payloads until the graph can prove they are applied."""
        redis = await self._redis_or_none()
        if redis is not None:
            raw = await redis.eval(
                _LIVE_RECEIPTS_LUA + "return live_receipts(KEYS[1], tonumber(ARGV[1]))",
                1,
                self._receipts_key(session_id),
                str(time.time()),
            )
            return [self._decode(item) for item in raw]
        async with self._lock:
            return [item for item, _ in self._live_memory_receipts(session_id).values()]

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
                    str(_STEER_TTL_SECONDS),
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
            self._inflight.pop(session_id, None)
            queue = self._pending.setdefault(session_id, [])
            queue[:0] = messages
            logger.info(
                "[Steer] session=%s requeued %d message(s) after failed delivery",
                session_id,
                len(messages),
            )

    async def ack_items(self, session_id: str) -> bool:
        """保留本次领取的 receipt；仅当前 owner 确认成功时返回 True。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                token = self._lease_tokens.get(session_id)
                if not token:
                    return False
                result = await redis.eval(
                    _LIVE_RECEIPTS_LUA
                    + """
                    if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
                    live_receipts(KEYS[3], tonumber(ARGV[2]))
                    for _, raw in ipairs(redis.call('LRANGE', KEYS[1], 0, -1)) do
                      local value = cjson.decode(raw)
                      value['receipt_expires_at'] = tonumber(ARGV[2]) + tonumber(ARGV[3])
                      redis.call('RPUSH', KEYS[3], cjson.encode(value))
                    end
                    redis.call('EXPIRE', KEYS[3], ARGV[3])
                    redis.call('DEL', KEYS[1], KEYS[2])
                    return 1
                    """,
                    3,
                    self._inflight_key(session_id),
                    self._lease_key(session_id),
                    self._receipts_key(session_id),
                    token,
                    str(time.time()),
                    str(_STEER_TTL_SECONDS),
                )
                if int(result) == 1:
                    self._lease_tokens.pop(session_id, None)
                    return True
                return False
            except Exception:
                logger.warning("[Steer] Redis ack failed", exc_info=True)
                if not self._redis_disabled:
                    raise
            return False
        async with self._lock:
            items = self._inflight.pop(session_id, [])
            if not items:
                return False
            receipts = self._live_memory_receipts(session_id)
            for item in items:
                receipts[item.id] = (item, time.time() + _STEER_TTL_SECONDS)
            if receipts:
                self._receipts[session_id] = receipts
            return True

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
            self._inflight.pop(session_id, None)
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

    async def remove_by_id(
        self, session_id: str, message_id: str, *, prevent_reenqueue: bool = True
    ) -> bool:
        """原子记录撤回并删除 pending；迟到 POST 不能复活它，已领取项不回撤。"""
        redis = await self._redis_or_none()
        if redis is not None:
            try:
                key = self._key(session_id)
                return bool(
                    await redis.eval(
                        """
                        if ARGV[3] == '1' then
                          redis.call('SET', KEYS[2], '1', 'EX', ARGV[2])
                        end
                        for _, raw in ipairs(redis.call('LRANGE', KEYS[1], 0, -1)) do
                          local ok, value = pcall(cjson.decode, raw)
                          if ok and value['id'] == ARGV[1] then
                            return redis.call('LREM', KEYS[1], 1, raw)
                          end
                        end
                        return 0
                        """,
                        2,
                        key,
                        self._cancelled_key(session_id, message_id),
                        message_id,
                        str(_STEER_TTL_SECONDS),
                        "1" if prevent_reenqueue else "0",
                    )
                )
            except Exception:
                logger.warning("[Steer] Redis ID remove failed", exc_info=True)
                if not self._redis_disabled:
                    raise
        async with self._lock:
            self._prune_cancelled()
            if prevent_reenqueue:
                self._cancelled[(session_id, message_id)] = time.monotonic() + _STEER_TTL_SECONDS
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


async def emit_undelivered_steer_events(
    session_id: str,
    run_id: str | None = None,
    presenter: Any = None,
    queue: SteerQueue | None = None,
) -> int:
    """run 终态时把未注入的插话落库为 ``steer:undelivered`` 事件（尽力而为）。

    run 在插话入队后、下一次模型调用前结束（典型：单次模型调用直接完成），
    插话既没注入也无任何落库痕迹，纯 API 消费者静默丢失。本函数在
    executor 的终态路径（completed / 用户取消 / 中断 / 失败）调用，逐条
    写出与 ``steer:message`` 同形状的事件，便于前端按 ``message_id`` 关联。

    队列本身不清空：前端补发流程仍按 ID 取消残留项再补发为普通消息，
    这里若清空会让「补发 + 取消」契约失去目标。返回成功写出的事件数。
    """
    target = queue if queue is not None else get_steer_queue()
    try:
        items = await target.list_items(session_id)
    except Exception:
        logger.warning(
            "[Steer] session=%s failed to list pending steers at run end",
            session_id,
            exc_info=True,
        )
        return 0
    if not items:
        return 0

    import uuid

    written = 0
    for item in items:
        data = {
            "content": item.content,
            "message_id": item.id or f"steer-{uuid.uuid4().hex[:12]}",
            "attachments": item.attachments,
        }
        if getattr(item, "created_at", None):
            data["created_at"] = item.created_at.isoformat()
        if run_id:
            data["run_id"] = run_id
        try:
            if presenter is not None:
                await presenter.save_event({"event": "steer:undelivered", "data": data})
            else:
                from src.infra.session.dual_writer import get_dual_writer

                await get_dual_writer().write_event(
                    session_id=session_id,
                    event_type="steer:undelivered",
                    data=data,
                )
            written += 1
        except Exception:
            logger.warning(
                "[Steer] session=%s failed to persist undelivered steer %s",
                session_id,
                getattr(item, "id", "unknown"),
                exc_info=True,
            )
    if written:
        logger.info(
            "[Steer] session=%s persisted %d undelivered steer(s) at run end",
            session_id,
            written,
        )
    return written


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

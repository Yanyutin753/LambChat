"""Qdrant 向量索引层——Mongo 之外的可选 ANN 索引视图。

设计约束：
- Mongo（native_memories）是唯一事实源；Qdrant 只存 point id + 向量 + 过滤 payload，
  可随时删库重建（backfill_from_mongo）。
- 一切故障静默降级：search 返回 None、upsert/delete 返回 False，调用方回退既有
  $vectorSearch/余弦链路，绝不阻塞主流程。
- user_id 是必带过滤条件（多租户隔离）。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

COLLECTION = "native_memories"


@dataclass(frozen=True)
class VectorHit:
    memory_id: str
    score: float


class QdrantVectorIndex:
    """AsyncQdrantClient 的薄封装。location=":memory:" 供测试/嵌入模式。"""

    def __init__(self, location: Optional[str] = None, dims: Optional[int] = None):
        from qdrant_client import AsyncQdrantClient

        self._location = location or getattr(
            settings, "NATIVE_MEMORY_QDRANT_URL", "http://127.0.0.1:6333"
        )
        api_key = getattr(settings, "NATIVE_MEMORY_QDRANT_API_KEY", "") or None
        if location == ":memory:" or self._location == ":memory:":
            api_key = None
        self._dims = int(
            dims or getattr(settings, "NATIVE_MEMORY_EMBEDDING_DIMENSIONS", 1536) or 1536
        )
        self._client = AsyncQdrantClient(location=self._location, api_key=api_key, timeout=10)
        self._ensured = False

    async def _ensure_ready(self) -> None:
        """惰性建库（一次）；失败抛异常由调用方的降级分支接住。"""
        if not self._ensured:
            await self.ensure_collection()
            self._ensured = True

    async def ensure_collection(self) -> bool:
        """确保 collection 存在且维度与配置一致。

        返回 True = 本次新建（调用方可据此触发回填）；False = 已存在且一致。
        维度不一致时抛 RuntimeError 且不删库——存量 Mongo embedding 已随旧
        维度失配，自动重建也无法正确回填，需管理员显式处置（换嵌入模型后
        应清理旧 embedding 重嵌，或删除该 collection 后重建）。
        """
        from qdrant_client.models import Distance, VectorParams

        if await self._client.collection_exists(COLLECTION):
            existing_size = await self._existing_vector_size()
            if existing_size is None or existing_size == self._dims:
                return False
            logger.error(
                "[MemoryVector] collection %s dimension mismatch: existing=%s configured=%d "
                "— vector index degraded to mongo fallback. Re-embed memories or drop the "
                "collection to recover.",
                COLLECTION,
                existing_size,
                self._dims,
            )
            raise RuntimeError(
                f"vector collection dimension mismatch: {existing_size} != {self._dims}"
            )
        await self._client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=self._dims, distance=Distance.COSINE),
        )
        logger.info(
            "[MemoryVector] Qdrant collection created: %s (%d dims, cosine)",
            COLLECTION,
            self._dims,
        )
        return True

    async def _existing_vector_size(self) -> Optional[int]:
        """读取既有 collection 的向量维度；读不出（结构异常）返回 None 视为兼容。"""
        try:
            info = await self._client.get_collection(COLLECTION)
            vectors = getattr(getattr(info.config, "params", None), "vectors", None)
            size = getattr(vectors, "size", None)
            if size is None and isinstance(vectors, dict):
                size = vectors.get("size")
            return int(size) if size is not None else None
        except Exception as e:
            logger.warning("[MemoryVector] failed to read existing vector size: %s", e)
            return None

    async def upsert(
        self,
        *,
        memory_id: str,
        user_id: str,
        vector: list[float],
        memory_type: str,
        context: Optional[str],
        updated_at: int,
    ) -> bool:
        from qdrant_client.models import PointStruct

        try:
            await self._ensure_ready()
            await self._client.upsert(
                collection_name=COLLECTION,
                points=[
                    PointStruct(
                        id=uuid.UUID(hex=memory_id),
                        vector=vector,
                        payload={
                            "user_id": user_id,
                            "memory_type": memory_type,
                            "context": context,
                            "updated_at": updated_at,
                        },
                    )
                ],
                wait=True,
            )
            return True
        except Exception as e:
            logger.warning("[MemoryVector] Qdrant upsert failed (fallback to mongo-only): %s", e)
            return False

    async def delete(self, *, memory_id: str, user_id: str) -> bool:
        """point id 即 memory_id（UUID hex），按 id 删除；user_id 仅作日志校验位。"""
        try:
            await self._ensure_ready()
            await self._client.delete(
                collection_name=COLLECTION,
                points_selector=[uuid.UUID(hex=memory_id)],
                wait=True,
            )
            return True
        except Exception as e:
            logger.warning("[MemoryVector] Qdrant delete failed: %s", e)
            return False

    async def search(
        self,
        *,
        vector: list[float],
        user_id: str,
        limit: int,
        memory_types: Optional[list[str]] = None,
        context_filter: Optional[str] = None,
    ) -> Optional[list[VectorHit]]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        must = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        if memory_types:
            must.append(FieldCondition(key="memory_type", match=MatchAny(any=memory_types)))
        if context_filter:
            must.append(FieldCondition(key="context", match=MatchValue(value=context_filter)))
        try:
            if not await self._client.collection_exists(COLLECTION):
                return []
            result = await self._client.query_points(
                collection_name=COLLECTION,
                query=vector,
                query_filter=Filter(must=must),
                limit=limit,
                with_payload=False,
            )
            # Qdrant 返回带连号的 UUID；Mongo 侧 memory_id 是无连号 hex，统一规范化
            return [
                VectorHit(memory_id=str(p.id).replace("-", ""), score=p.score)
                for p in result.points
            ]
        except Exception as e:
            logger.warning("[MemoryVector] Qdrant search failed (fallback): %s", e)
            return None

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 惰性单例（随 MEMORY_AFFECTED 设置热重建，与 backend 同生命周期）
# ---------------------------------------------------------------------------

_vector_index: Optional[QdrantVectorIndex] = None
_index_failed_until = 0.0  # monotonic 时间戳；冷却期内不再重试建连
_INDEX_RETRY_COOLDOWN_SECONDS = 60.0

# 自动回填（issue #278）：切到 qdrant 后存量 Mongo embedding 自动灌入，
# 完成标记持久在 Redis——跨副本至多跑一次；首建/重建 force 重跑。
_BACKFILL_DONE_KEY = "memory:vector_backfill:done"
_BACKFILL_LOCK_KEY = "memory:vector_backfill:lock"
_BACKFILL_LOCK_TTL = 1800  # 覆盖最大预期回填时长
_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)
_backfill_task: Optional[asyncio.Task] = None


def vector_backend_enabled() -> bool:
    return getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") == "qdrant"


async def _run_backfill_once(*, force: bool = False) -> None:
    """幂等自动回填：Redis 完成标记 + token 锁防跨副本重跑。

    回填只搬运 Mongo 已存的 embedding（不重算），成本低；任何故障静默
    降级（下次建库重试），绝不影响主链路。
    """
    try:
        from src.infra.storage.redis import get_redis_client

        rc = get_redis_client()
        if force:
            await rc.delete(_BACKFILL_DONE_KEY)
        elif await rc.get(_BACKFILL_DONE_KEY):
            return
        token = uuid.uuid4().hex[:8]
        if not await rc.set(_BACKFILL_LOCK_KEY, token, nx=True, ex=_BACKFILL_LOCK_TTL):
            return  # 其他副本在灌
        try:
            from src.infra.memory.tools import _get_backend

            backend = await _get_backend()
            collection = getattr(backend, "_collection", None) if backend is not None else None
            if collection is None:
                return
            result = await backfill_from_mongo(collection)
            await rc.set(_BACKFILL_DONE_KEY, "1")  # type: ignore[misc]
            logger.info("[MemoryVector] auto backfill completed: %s", result)
        finally:
            await rc.eval(_RELEASE_LOCK_LUA, 1, _BACKFILL_LOCK_KEY, token)  # type: ignore[misc]
    except Exception as e:
        logger.warning("[MemoryVector] auto backfill failed (will retry next init): %s", e)


def _schedule_backfill_once(*, force: bool = False) -> None:
    """后台调度回填；持引用防 GC 中断，单例存续期内至多一个在途任务。"""
    global _backfill_task
    if _backfill_task is not None and not _backfill_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _backfill_task = loop.create_task(_run_backfill_once(force=force))
    except RuntimeError:
        pass


async def get_vector_index() -> Optional[QdrantVectorIndex]:
    """单例；未启用返回 None。collection 惰性确保（首用时建）。

    Qdrant 不可达时进入冷却期，避免每次 recall/retain 都重付建连+ensure 的超时成本。
    """
    global _vector_index, _index_failed_until
    if not vector_backend_enabled():
        return None
    if _vector_index is None:
        if time.monotonic() < _index_failed_until:
            return None
        candidate = QdrantVectorIndex()
        try:
            created = await candidate.ensure_collection()
        except Exception as e:
            logger.warning("[MemoryVector] Qdrant unavailable, vector backend degraded: %s", e)
            await candidate.close()
            _index_failed_until = time.monotonic() + _INDEX_RETRY_COOLDOWN_SECONDS
            return None
        _vector_index = candidate
        # 首建（或 done 标记缺失的上次未完成回填）→ 后台自动回填存量
        _schedule_backfill_once(force=created)
    return _vector_index


async def reset_vector_index() -> None:
    global _vector_index, _index_failed_until
    if _vector_index is not None:
        await _vector_index.close()
    _vector_index = None
    _index_failed_until = 0.0


# ---------------------------------------------------------------------------
# None-safe 模块助手（backend/search 接线用；未启用或故障时静默降级）
# ---------------------------------------------------------------------------


async def index_write_through(
    *,
    user_id: str,
    memory_id: str,
    embedding: Optional[list[float]],
    memory_type: str,
    context: Optional[str],
    updated_at_ts: int,
) -> bool:
    idx = await get_vector_index()
    if idx is None or not embedding:
        return False
    return await idx.upsert(
        memory_id=memory_id,
        user_id=user_id,
        vector=embedding,
        memory_type=memory_type,
        context=context,
        updated_at=updated_at_ts,
    )


async def index_delete(user_id: str, memory_id: str) -> bool:
    idx = await get_vector_index()
    if idx is None:
        return False
    return await idx.delete(memory_id=memory_id, user_id=user_id)


async def index_search(
    *,
    vector: list[float],
    user_id: str,
    limit: int,
    memory_types: Optional[list[str]] = None,
    context_filter: Optional[str] = None,
) -> Optional[list[VectorHit]]:
    """None = 未启用/故障 → 调用方走既有 $vectorSearch/余弦链路；list = 权威结果。"""
    idx = await get_vector_index()
    if idx is None:
        return None
    return await idx.search(
        vector=vector,
        user_id=user_id,
        limit=limit,
        memory_types=memory_types,
        context_filter=context_filter,
    )


async def backfill_from_mongo(collection, batch_size: int = 100) -> dict:
    """把 Mongo 存量 embedding 幂等灌入 Qdrant（未启用时返回 skipped）。"""
    idx = await get_vector_index()
    if idx is None:
        return {"skipped": True}
    from qdrant_client.models import PointStruct

    total = 0
    cursor = collection.find(
        {"embedding": {"$ne": None}, "source": {"$ne": "session_summary"}},
        {
            "memory_id": 1,
            "user_id": 1,
            "embedding": 1,
            "memory_type": 1,
            "context": 1,
            "updated_at": 1,
        },
    )
    batch: list[PointStruct] = []
    async for doc in cursor:
        batch.append(
            PointStruct(
                id=uuid.UUID(hex=doc["memory_id"]),
                vector=doc["embedding"],
                payload={
                    "user_id": doc["user_id"],
                    "memory_type": doc.get("memory_type", "user"),
                    "context": doc.get("context"),
                    "updated_at": int(
                        doc["updated_at"].timestamp()
                        if hasattr(doc.get("updated_at"), "timestamp")
                        else (doc.get("updated_at") or 0)
                    ),
                },
            )
        )
        if len(batch) >= batch_size:
            await idx._client.upsert(collection_name=COLLECTION, points=batch, wait=True)
            total += len(batch)
            batch = []
    if batch:
        await idx._client.upsert(collection_name=COLLECTION, points=batch, wait=True)
        total += len(batch)
    return {"upserted": total}

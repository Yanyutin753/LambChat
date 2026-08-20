"""
MongoDB Store 实现

提供 LangGraph BaseStore 的 MongoDB 实现，替代 PostgresStore。
仅支持基本 KV 操作（put/get/search/list_namespaces），不支持向量语义搜索。

数据模型:
  collection: "store"
  {
    "_id":           {"namespace": [...], "key": "..."},   # 复合主键
    "namespace":     ["assistant:123", "memories"],         # 命名空间
    "key":           "memory_001",                          # 键
    "value":         {...},                                  # 值 (dict)
    "created_at":    ISO datetime,
    "updated_at":    ISO datetime,
  }
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Iterable
from datetime import datetime
from itertools import islice
from typing import TYPE_CHECKING, Any

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    MatchCondition,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

logger = get_logger(__name__)

COLLECTION_NAME = "store"
DEFAULT_STORE_BATCH_CONCURRENCY = 16
MONGODB_STORE_BATCH_MAX_OPS = 1000
MONGODB_STORE_QUERY_LIMIT = 100


def _ns_to_list(namespace: tuple[str, ...]) -> list[str]:
    return list(namespace)


def _list_to_ns(ns_list: Any) -> tuple[str, ...]:
    return tuple(ns_list)


def _parse_doc_timestamps(
    doc: dict[str, Any],
) -> tuple[datetime | None, datetime | None]:
    """解析文档中的时间戳字段。"""
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)
    return created_at, updated_at


def _doc_to_item(doc: dict[str, Any]) -> Item:
    created_at, updated_at = _parse_doc_timestamps(doc)
    now = utc_now()
    return Item(
        namespace=_list_to_ns(doc["namespace"]),
        key=doc["key"],
        value=doc["value"],
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def _doc_to_search_item(doc: dict[str, Any]) -> SearchItem:
    created_at, updated_at = _parse_doc_timestamps(doc)
    now = utc_now()
    return SearchItem(
        namespace=_list_to_ns(doc["namespace"]),
        key=doc["key"],
        value=doc["value"],
        created_at=created_at or now,
        updated_at=updated_at or now,
        score=1.0,
    )


def _build_ns_prefix_query(ns_prefix: list[str]) -> dict[str, Any]:
    """构建 namespace 前缀匹配查询。

    MongoDB 中 namespace 存为原生数组，用 $all 精确匹配前缀元素。
    同时用 $expr + $slice 确保前 N 个元素完全匹配。

    例如 prefix=["a","b"] 应匹配 ["a","b"] 和 ["a","b","c"]，但不匹配 ["a","c"]。
    """
    if not ns_prefix:
        return {}  # 空 prefix 匹配所有

    return {
        "namespace": {"$all": ns_prefix},
        "$expr": {"$eq": [{"$slice": ["$namespace", len(ns_prefix)]}, ns_prefix]},
    }


def _build_ns_suffix_query(ns_suffix: list[str]) -> dict[str, Any]:
    """构建 namespace 后缀匹配查询。

    例如 suffix=["b","c"] 应匹配 ["a","b","c"]，但不匹配 ["a","b"]。
    """
    if not ns_suffix:
        return {}

    return {
        "namespace": {"$all": ns_suffix},
        "$expr": {"$eq": [{"$slice": ["$namespace", -len(ns_suffix)]}, ns_suffix]},
    }


def _build_match_conditions_query(
    match_conditions: list[MatchCondition],
) -> dict[str, Any]:
    """构建多条件组合的 match 查询。

    当有多个条件时使用 $and 组合，避免后置条件覆盖前置条件。
    """
    conditions: list[dict[str, Any]] = []
    for condition in match_conditions:
        path = list(condition.path) if condition.path else []
        if condition.match_type == "prefix" and path:
            conditions.append(_build_ns_prefix_query(path))
        elif condition.match_type == "suffix" and path:
            conditions.append(_build_ns_suffix_query(path))

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _store_batch_concurrency() -> int:
    return max(
        1,
        int(
            getattr(
                settings,
                "MONGODB_STORE_BATCH_CONCURRENCY",
                DEFAULT_STORE_BATCH_CONCURRENCY,
            )
            or 1
        ),
    )


def _clamp_query_limit(value: int | None) -> int:
    try:
        candidate = int(value or 1)
    except (TypeError, ValueError):
        candidate = 1
    return min(max(candidate, 1), MONGODB_STORE_QUERY_LIMIT)


def _clamp_query_offset(value: int | None) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _bounded_ops_list(ops: Iterable[Op]) -> list[Op]:
    ops_list = list(islice(ops, MONGODB_STORE_BATCH_MAX_OPS + 1))
    if len(ops_list) > MONGODB_STORE_BATCH_MAX_OPS:
        raise ValueError(
            f"too many store operations in one batch (max {MONGODB_STORE_BATCH_MAX_OPS})"
        )
    return ops_list


class MongoDBStore(BaseStore):
    """基于 MongoDB 的 LangGraph Store 实现。

    用法与 PostgresStore 一致::

        store = MongoDBStore()
        store.put(("users", "123"), "prefs", {"theme": "dark"})
        item = store.get(("users", "123"), "prefs")
    """

    __slots__ = ("_client", "_db_name", "_collection_name", "_collection")

    def __init__(
        self,
        client: AsyncIOMotorClient | None = None,
        db_name: str | None = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self._client = client
        self._db_name = db_name or settings.MONGODB_DB
        self._collection_name = collection_name
        self._collection: AsyncIOMotorCollection[Any] | None = None

    @property
    def collection(self) -> AsyncIOMotorCollection[Any]:
        if self._collection is None:
            client = self._client or get_mongo_client()
            db = client[self._db_name]
            self._collection = db[self._collection_name]
        return self._collection

    async def asetup(self) -> None:
        """异步创建索引（在异步上下文中通过线程池执行）。"""
        await run_blocking_io(self._create_indexes_sync)

    def setup(self) -> None:
        """创建索引。同步调用，如果在异步上下文中则直接执行（索引创建是幂等操作）。"""
        self._create_indexes_sync()

    def _create_indexes_sync(self) -> None:
        """使用 pymongo 同步客户端创建索引（线程安全，一次性操作）。"""
        client = self._client or get_mongo_client()
        sync_col = client.delegate[self._db_name][self._collection_name]

        # Older releases created a unique index on ``key`` alone.  That makes
        # otherwise valid files with the same name in different namespaces
        # collide and causes repeated writes to fail with DuplicateKeyError.
        # The store identity is the pair (namespace, key), so remove only the
        # obsolete exact key-only unique index before ensuring the correct one.
        for index_name, index_info in sync_col.index_information().items():
            if (
                index_name != "_id_"
                and index_info.get("unique") is True
                and index_info.get("key") == [("key", 1)]
            ):
                sync_col.drop_index(index_name)
                logger.warning(
                    "Dropped legacy MongoDB store unique index %s; store identity is (namespace, key)",
                    index_name,
                )

        sync_col.create_index(
            [("namespace", 1), ("key", 1)],
            unique=True,
            name="store_ns_key_idx",
        )
        sync_col.create_index(
            [("namespace", 1)],
            name="store_namespace_idx",
        )
        logger.info(f"MongoDBStore indexes created: {self._db_name}.{self._collection_name}")

    # ------------------------------------------------------------------
    # Core: batch / abatch
    # ------------------------------------------------------------------

    def _sync_collection(self):
        """获取同步 pymongo collection（用于 batch，避免事件循环冲突）。"""
        client = self._client or get_mongo_client()
        return client.delegate[self._db_name][self._collection_name]

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        """同步批量操作 — 使用 pymongo 同步客户端，与 motor 事件循环隔离。"""
        col = self._sync_collection()
        ops_list = _bounded_ops_list(ops)
        results: list[Result] = [None] * len(ops_list)

        for i, op in enumerate(ops_list):
            if isinstance(op, GetOp):
                doc = col.find_one({"namespace": _ns_to_list(op.namespace), "key": op.key})
                results[i] = _doc_to_item(doc) if doc else None

            elif isinstance(op, PutOp):
                ns = _ns_to_list(op.namespace)
                filter_ = {"namespace": ns, "key": op.key}
                if op.value is None:
                    col.delete_one(filter_)
                else:
                    now = utc_now()
                    col.update_one(
                        filter_,
                        {
                            "$set": {"value": op.value, "updated_at": now},
                            "$setOnInsert": {"created_at": now},
                        },
                        upsert=True,
                    )

            elif isinstance(op, SearchOp):
                ns_prefix = _ns_to_list(op.namespace_prefix)
                query: dict[str, Any] = _build_ns_prefix_query(ns_prefix)
                if op.filter:
                    for key, val in op.filter.items():
                        query[f"value.{key}"] = val
                offset = _clamp_query_offset(op.offset)
                limit = _clamp_query_limit(op.limit)
                docs = list(col.find(query).skip(offset).limit(limit))
                results[i] = [_doc_to_search_item(doc) for doc in docs]

            elif isinstance(op, ListNamespacesOp):
                pipeline: list[dict[str, Any]] = []
                if op.match_conditions:
                    match_stage = _build_match_conditions_query(list(op.match_conditions))
                    if match_stage:
                        pipeline.append({"$match": match_stage})

                group_id: str | dict[str, Any] = "$namespace"
                if op.max_depth is not None:
                    group_id = {"$slice": ["$namespace", op.max_depth]}

                pipeline.extend(
                    [
                        {"$group": {"_id": group_id}},
                        {"$sort": {"_id": 1}},
                        {"$skip": _clamp_query_offset(op.offset)},
                        {"$limit": _clamp_query_limit(op.limit)},
                    ]
                )
                docs = list(col.aggregate(pipeline))
                results[i] = [_list_to_ns(doc["_id"]) for doc in docs]

            else:
                raise ValueError(f"Unknown operation type: {type(op)}")

        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        ops_list = _bounded_ops_list(ops)
        results: list[Result] = [None] * len(ops_list)
        col = self.collection
        next_index = 0
        worker_count = min(_store_batch_concurrency(), len(ops_list))

        if not worker_count:
            return results

        async def _worker() -> None:
            nonlocal next_index
            while next_index < len(ops_list):
                i = next_index
                next_index += 1
                op = ops_list[i]
                if isinstance(op, GetOp):
                    results[i] = await self._aget(col, op)
                elif isinstance(op, PutOp):
                    await self._aput(col, op)
                elif isinstance(op, SearchOp):
                    results[i] = await self._asearch(col, op)
                elif isinstance(op, ListNamespacesOp):
                    results[i] = await self._alist_namespaces(col, op)
                else:
                    raise ValueError(f"Unknown operation type: {type(op)}")

        await asyncio.gather(*(_worker() for _ in range(worker_count)))
        return results

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    async def _aget(self, col: AsyncIOMotorCollection[Any], op: GetOp) -> Item | None:
        doc = await col.find_one({"namespace": _ns_to_list(op.namespace), "key": op.key})
        return _doc_to_item(doc) if doc else None

    # ------------------------------------------------------------------
    # Put (value=None means delete)
    # ------------------------------------------------------------------

    async def _aput(self, col: AsyncIOMotorCollection[Any], op: PutOp) -> None:
        ns = _ns_to_list(op.namespace)
        filter_ = {"namespace": ns, "key": op.key}

        if op.value is None:
            await col.delete_one(filter_)
        else:
            now = utc_now()
            await col.update_one(
                filter_,
                {
                    "$set": {"value": op.value, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

    # ------------------------------------------------------------------
    # Search (namespace prefix + filter, no vector)
    # ------------------------------------------------------------------

    async def _asearch(self, col: AsyncIOMotorCollection[Any], op: SearchOp) -> list[SearchItem]:
        ns_prefix = _ns_to_list(op.namespace_prefix)
        query: dict[str, Any] = _build_ns_prefix_query(ns_prefix)

        if op.filter:
            for key, val in op.filter.items():
                query[f"value.{key}"] = val

        offset = _clamp_query_offset(op.offset)
        limit = _clamp_query_limit(op.limit)
        cursor = col.find(query).skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [_doc_to_search_item(doc) for doc in docs]

    # ------------------------------------------------------------------
    # ListNamespaces
    # ------------------------------------------------------------------

    async def _alist_namespaces(
        self, col: AsyncIOMotorCollection[Any], op: ListNamespacesOp
    ) -> list[tuple[str, ...]]:
        pipeline: list[dict[str, Any]] = []

        if op.match_conditions:
            match_stage = _build_match_conditions_query(list(op.match_conditions))
            if match_stage:
                pipeline.append({"$match": match_stage})

        # 去重 + 截断
        group_id: str | dict[str, Any] = "$namespace"
        if op.max_depth is not None:
            group_id = {"$slice": ["$namespace", op.max_depth]}

        pipeline.append({"$group": {"_id": group_id}})
        pipeline.append({"$sort": {"_id": 1}})
        limit = _clamp_query_limit(op.limit)
        pipeline.append({"$skip": _clamp_query_offset(op.offset)})
        pipeline.append({"$limit": limit})

        cursor = col.aggregate(pipeline)
        docs = await cursor.to_list(length=limit)
        return [_list_to_ns(doc["_id"]) for doc in docs]


# ---------------------------------------------------------------------------
# Factory (与 create_postgres_store 对应)
# ---------------------------------------------------------------------------


def create_mongodb_store() -> MongoDBStore:
    """创建 MongoDBStore 实例。

    复用 motor 的全局连接池，与 checkpoint 共享同一个 MongoClient。
    """
    store = MongoDBStore()
    store.setup()
    logger.info("MongoDBStore created (reusing motor connection pool)")
    return store


async def acreate_mongodb_store() -> MongoDBStore:
    """异步创建 MongoDBStore，避免在事件循环线程内同步建索引。"""
    store = MongoDBStore()
    await store.asetup()
    logger.info("MongoDBStore created asynchronously (reusing motor connection pool)")
    return store


# 模块级单例缓存
_store_instance: BaseStore | None = None
_store_initialized = False
_store_init_lock: asyncio.Lock | None = None


def _get_store_init_lock() -> asyncio.Lock:
    global _store_init_lock
    if _store_init_lock is None:
        _store_init_lock = asyncio.Lock()
    return _store_init_lock


def create_store() -> BaseStore | None:
    """创建 Store 实例（单例），按配置选择后端。

    ENABLE_POSTGRES_STORAGE=True → PostgresStore，失败 fallback MongoDB。
    ENABLE_POSTGRES_STORAGE=False → MongoDB。
    两者都不可用则返回 None。
    """
    global _store_instance, _store_initialized
    if _store_initialized:
        return _store_instance

    _store_initialized = True

    if settings.ENABLE_POSTGRES_STORAGE:
        try:
            from src.infra.storage.postgres import create_postgres_store

            _store_instance = create_postgres_store()
            logger.info("Store created: PostgresStore")
            return _store_instance
        except Exception as e:
            logger.warning(f"PostgresStore unavailable, falling back to MongoDB: {e}")

    # Fallback: MongoDB
    try:
        _store_instance = create_mongodb_store()
        logger.info("Store created: MongoDBStore")
        return _store_instance
    except Exception as e:
        logger.warning(f"MongoDBStore unavailable, no store will be used: {e}")
        return None


async def acreate_store() -> BaseStore | None:
    """异步创建 Store 实例（单例），避免在事件循环线程上执行同步初始化。"""
    global _store_instance, _store_initialized
    if _store_initialized and _store_instance is not None:
        return _store_instance

    async with _get_store_init_lock():
        if _store_initialized:
            return _store_instance

        _store_initialized = True

        if settings.ENABLE_POSTGRES_STORAGE:
            try:
                from src.infra.storage.postgres import create_postgres_store

                _store_instance = await run_blocking_io(create_postgres_store)
                logger.info("Store created asynchronously: PostgresStore")
                return _store_instance
            except Exception as e:
                logger.warning(
                    f"PostgresStore unavailable in async init, falling back to MongoDB: {e}"
                )

        try:
            _store_instance = await acreate_mongodb_store()
            logger.info("Store created asynchronously: MongoDBStore")
            return _store_instance
        except Exception as e:
            logger.warning(f"MongoDBStore unavailable in async init, no store will be used: {e}")
            return None


async def close_store() -> None:
    """Release the process-local store singleton and close it if the backend supports it."""
    global _store_instance, _store_initialized

    store = _store_instance
    _store_instance = None
    _store_initialized = False

    if store is None:
        return

    close = getattr(store, "aclose", None) or getattr(store, "close", None)
    if close is None:
        return

    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception as e:
        logger.warning("Error closing store singleton: %s", e)

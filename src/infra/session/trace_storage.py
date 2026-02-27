"""
Trace Storage - 按 trace 聚合事件存储

将同一 trace_id 的所有事件聚合到一条 MongoDB 文档中，
大幅减少文档数量，同时保留完整的事件上下文。

数据结构:
{
    "trace_id": "xxx",
    "session_id": "xxx",
    "run_id": "xxx",
    "agent_id": "xxx",
    "user_id": "xxx",
    "events": [
        {"seq": 1, "event_type": "message:chunk", "data": {...}, "timestamp": ...},
        {"seq": 2, "event_type": "thinking", "data": {...}, "timestamp": ...},
    ],
    "event_count": 2,
    "started_at": ISODate,
    "updated_at": ISODate,
    "completed_at": ISODate,
    "status": "running" | "completed" | "error",
    "metadata": {}
}

全局序号说明:
- 每个 session 有一个独立的递增序号计数器 (存储在 session_events_counter 集合)
- 每个事件写入时获取全局序号，用于断点续读
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TraceStorage:
    """
    Trace 存储类

    按 trace_id 聚合事件，使用 MongoDB $push 追加事件到数组。
    """

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[settings.MONGODB_TRACES_COLLECTION]
            # 创建索引（异步执行，不阻塞）
            import asyncio

            asyncio.create_task(self._ensure_indexes())
        return self._collection

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        try:
            # 复合索引：用于 get_session_events 查询
            # 查询模式: session_id + run_id (可选) + status (可选)
            await self._collection.create_index(
                [("session_id", 1), ("run_id", 1), ("status", 1)],
                name="session_run_status_idx",
                background=True,
            )
            # 唯一索引：trace_id
            await self._collection.create_index(
                [("trace_id", 1)],
                unique=True,
                name="trace_id_unique_idx",
                background=True,
            )
            # 索引：用于按时间排序列出 traces
            await self._collection.create_index(
                [("started_at", -1)],
                name="started_at_idx",
                background=True,
            )
            logger.info("MongoDB indexes ensured for trace_storage")
        except Exception as e:
            logger.warning(f"Failed to create indexes (non-critical): {e}")

    async def create_trace(
        self,
        trace_id: str,
        session_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        创建新的 trace 文档

        Args:
            trace_id: 唯一 trace 标识
            session_id: 会话 ID
            agent_id: Agent ID
            run_id: 运行 ID
            user_id: 用户 ID
            metadata: 额外元数据

        Returns:
            是否创建成功
        """
        now = _utc_now()
        doc = {
            "trace_id": trace_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "user_id": user_id,
            "events": [],
            "event_count": 0,
            "started_at": now,
            "updated_at": now,
            "status": "running",
            "metadata": metadata or {},
        }

        try:
            result = await self.collection.insert_one(doc)
            logger.info(
                f"Created trace {trace_id} for session {session_id}, inserted_id={result.inserted_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create trace {trace_id}: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def append_event(
        self,
        trace_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """
        追加事件到 trace

        使用 $push 和 $inc 原子操作，保证一致性。

        Args:
            trace_id: Trace ID
            event_type: 事件类型
            data: 事件数据

        Returns:
            是否追加成功
        """
        try:
            result = await self.collection.update_one(
                {"trace_id": trace_id},
                {
                    "$push": {
                        "events": {
                            "event_type": event_type,
                            "data": data,
                            "timestamp": _utc_now(),
                        }
                    },
                    "$inc": {"event_count": 1},
                    "$set": {"updated_at": _utc_now()},
                },
            )
            if result.modified_count == 0:
                logger.warning(f"append_event: trace {trace_id} not found or not modified")
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to append event to trace {trace_id}: {e}")
            return False

    async def complete_trace(
        self,
        trace_id: str,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        标记 trace 完成

        Args:
            trace_id: Trace ID
            status: 最终状态 (completed/error)
            metadata: 额外元数据

        Returns:
            是否更新成功
        """
        update = {
            "$set": {
                "status": status,
                "completed_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        }
        if metadata:
            update["$set"]["metadata"] = metadata

        try:
            result = await self.collection.update_one(
                {"trace_id": trace_id},
                update,
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to complete trace {trace_id}: {e}")
            return False

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        获取完整的 trace

        Args:
            trace_id: Trace ID

        Returns:
            trace 文档或 None
        """
        try:
            doc = await self.collection.find_one(
                {"trace_id": trace_id},
                {"_id": 0},
            )
            return doc
        except Exception as e:
            logger.error(f"Failed to get trace {trace_id}: {e}")
            return None

    async def get_trace_events(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 trace 的事件列表

        Args:
            trace_id: Trace ID
            event_types: 可选的事件类型过滤

        Returns:
            事件列表
        """
        trace = await self.get_trace(trace_id)
        if not trace:
            return []

        events = trace.get("events", [])
        if event_types:
            events = [e for e in events if e.get("event_type") in event_types]

        return events

    async def list_traces(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        列出 traces

        Args:
            session_id: 按会话过滤
            user_id: 按用户过滤
            agent_id: 按 Agent 过滤
            status: 按状态过滤
            limit: 最大数量
            skip: 跳过数量

        Returns:
            trace 列表（不含 events 数组，仅摘要）
        """
        query = {}
        if session_id:
            query["session_id"] = session_id
        if user_id:
            query["user_id"] = user_id
        if agent_id:
            query["agent_id"] = agent_id
        if status:
            query["status"] = status

        try:
            cursor = (
                self.collection.find(
                    query,
                    {
                        "_id": 0,
                        "events": 0,  # 排除大数组
                    },
                )
                .sort("started_at", -1)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Failed to list traces: {e}")
            return []

    async def get_session_events(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None,
        run_id: Optional[str] = None,
        exclude_run_id: Optional[str] = None,
        completed_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        获取会话的所有事件（跨 traces 聚合）

        按 timestamp 排序返回所有事件。

        Args:
            session_id: 会话 ID
            event_types: 可选的事件类型过滤列表
            run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
            exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
            completed_only: 是否只返回成功完成的 trace 中的事件（默认 True）

        Returns:
            事件列表，按时间戳排序
        """
        try:
            # 构建查询条件
            match_query: Dict[str, Any] = {"session_id": session_id}
            if run_id:
                match_query["run_id"] = run_id
            if exclude_run_id:
                match_query["run_id"] = {"$ne": exclude_run_id}
            # 排除正在运行的 trace（只返回 running 状态以外的）
            if completed_only:
                match_query["status"] = {"$ne": "running"}

            # 直接执行聚合查询，去掉冗余的 count_documents（聚合空结果自然返回空列表）
            # 聚合查询，展开所有 events
            pipeline: List[Dict[str, Any]] = [
                {"$match": match_query},
                {"$unwind": {"path": "$events", "preserveNullAndEmptyArrays": False}},
            ]

            # 事件类型过滤
            if event_types:
                pipeline.append({"$match": {"events.event_type": {"$in": event_types}}})

            # 添加计算字段：优先使用 data.timestamp，否则使用外层 timestamp
            # 这样可以处理所有事件类型（有些事件的 data 里没有 timestamp）
            pipeline.append(
                {
                    "$addFields": {
                        "effective_timestamp": {
                            "$ifNull": ["$events.data.timestamp", "$events.timestamp"]
                        }
                    }
                }
            )

            # 按有效时间戳排序
            pipeline.append({"$sort": {"effective_timestamp": 1}})

            # 投影
            pipeline.append(
                {
                    "$project": {
                        "_id": 0,
                        "trace_id": 1,
                        "run_id": 1,
                        "event_type": "$events.event_type",
                        "data": "$events.data",
                        "timestamp": "$events.timestamp",
                    }
                }
            )

            cursor = self.collection.aggregate(pipeline, allowDiskUse=True)
            results = await cursor.to_list(length=None)
            logger.debug(f"Session {session_id} (run_id={run_id}) returned {len(results)} events")
            return results
        except Exception as e:
            logger.error(f"Failed to get session events: {e}")
            return []

    async def get_run_events(
        self,
        session_id: str,
        run_id: str,
        event_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取特定 run 的事件

        Args:
            session_id: 会话 ID
            run_id: 运行 ID
            event_types: 可选的事件类型过滤列表

        Returns:
            事件列表，按时间戳排序
        """
        return await self.get_session_events(session_id, event_types, run_id=run_id)

    async def delete_trace(self, trace_id: str) -> bool:
        """删除 trace"""
        try:
            result = await self.collection.delete_one({"trace_id": trace_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete trace {trace_id}: {e}")
            return False

    async def delete_session_traces(self, session_id: str) -> int:
        """删除会话的所有 traces"""
        try:
            result = await self.collection.delete_many({"session_id": session_id})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Failed to delete session traces: {e}")
            return 0


# Singleton
_trace_storage: Optional[TraceStorage] = None


def get_trace_storage() -> TraceStorage:
    """获取 TraceStorage 单例"""
    global _trace_storage
    if _trace_storage is None:
        _trace_storage = TraceStorage()
    return _trace_storage

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

"""

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from src.infra.logging import get_logger
from src.infra.session._trace_storage_support import (
    _RECOMMEND_QUESTIONS_LIMIT as _RECOMMEND_QUESTIONS_LIMIT,
)
from src.infra.session._trace_storage_support import (
    TRACE_EVENTS_DEFAULT_LIMIT as TRACE_EVENTS_DEFAULT_LIMIT,
)
from src.infra.session._trace_storage_support import (
    TRACE_EVENTS_READ_LIMIT as TRACE_EVENTS_READ_LIMIT,
)
from src.infra.session._trace_storage_support import (
    TRACE_LIST_LIMIT,
    _bounded_unique_strings,
    _clamp_event_read_limit,
    _clamp_nonnegative_int,
    _clamp_positive_int,
    _event_seq,
    _get_session_event_read_default_limit,
    _normalize_recommend_questions,
)
from src.infra.session._trace_storage_support import (
    _event_chunk_index as _event_chunk_index,
)
from src.infra.session._trace_storage_support import (
    _event_preview as _event_preview,
)
from src.infra.session._trace_storage_support import (
    _get_event_chunk_size as _get_event_chunk_size,
)
from src.infra.session.trace_event_chunks import (
    ATTACHMENT_CHUNK_WRITE_FIELD,
    TraceEventChunkMixin,
)
from src.infra.session.trace_storage_writes import TraceStorageWriteMixin
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

_SESSION_EVENTS_BATCH_SIZE = 200
SESSION_EVENT_FILTER_LIST_LIMIT = 100
ATTACHMENT_CLEAR_TERMINAL_STATUSES = ("completed", "error")


@dataclass(frozen=True)
class SessionEventsSnapshot:
    """A consistent history read plus any live-stream replay requirement."""

    events: List[Dict[str, Any]]
    history_mode: Literal["complete", "active_user_only"] = "complete"
    stream_run_id: Optional[str] = None


async def _write_usage_log(trace_id: str) -> None:
    """在 trace 完成后，异步将 token 用量写入独立的 usage_logs 集合。"""
    try:
        from src.infra.usage.storage import get_usage_storage

        storage = get_usage_storage()
        collection = storage.collection

        # 只读取 trace 元数据；usage 事件通过兼容读路径从 chunk/legacy 中查询。
        trace_doc = await collection.database[settings.MONGODB_TRACES_COLLECTION].find_one(
            {"trace_id": trace_id},
            {"_id": 0, "events": 0},
        )
        if trace_doc:
            usage_event = await get_trace_storage().get_last_trace_event(
                trace_id,
                ["token:usage"],
            )
            await storage.upsert_usage_log_from_trace_metadata(
                trace_doc,
                (usage_event or {}).get("data", {}),
            )
    except Exception as e:
        # 写入 usage_logs 失败不应影响主流程
        logger.warning(f"Failed to write usage log for trace {trace_id}: {e}")


class TraceStorage(TraceStorageWriteMixin, TraceEventChunkMixin):
    """
    Trace 存储类

    按 trace_id 聚合事件，使用 MongoDB $push 追加事件到数组。
    写入时按 Redis 顺序追加，读取时按 started_at 排序后合并。
    """

    def __init__(self):
        self._collection = None
        self._chunks_collection = None
        self._session_storage = None
        self._merger = None  # 事件合并器
        self._indexes_task: asyncio.Task[None] | None = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[settings.MONGODB_TRACES_COLLECTION]
            # 索引创建在首次异步操作时触发，避免在 property getter 中调用 create_task
        return self._collection

    @property
    def chunks_collection(self):
        """延迟加载 MongoDB trace event chunks 集合"""
        if self._chunks_collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._chunks_collection = db[settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION]
        return self._chunks_collection

    @property
    def session_storage(self):
        """Session anchor storage used for cross-collection writer leases."""
        if self._session_storage is None:
            from src.infra.session.storage import SessionStorage

            self._session_storage = SessionStorage()
        return self._session_storage

    async def acquire_session_trace_write(self, session_id: str) -> bool:
        return await self.session_storage.acquire_trace_write(session_id)

    async def release_session_trace_write(self, session_id: str) -> None:
        await self.session_storage.release_trace_write(session_id)

    async def ensure_indexes_if_needed(self):
        """确保索引存在（由首次使用时调用）"""
        if not hasattr(self, "_indexes_ensured"):
            self._indexes_ensured = True
            task = asyncio.create_task(self._ensure_indexes())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            self._indexes_task = task
            # 启动事件合并器
            self._start_merger()

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        collection = self.collection
        try:
            # 复合索引：用于 get_session_events 查询
            # 查询模式: session_id + status (可选) + sort by started_at
            # 把 status 放在 session_id 后面、started_at 前面，使排序能利用索引
            await collection.create_index(
                [("session_id", 1), ("status", 1), ("started_at", 1)],
                name="session_status_started_at_idx",
                background=True,
            )
            # 复合索引：用于按 run_id 查询
            await collection.create_index(
                [("session_id", 1), ("run_id", 1), ("status", 1)],
                name="session_run_status_idx",
                background=True,
            )
            # 唯一索引：trace_id
            await collection.create_index(
                [("trace_id", 1)],
                unique=True,
                name="trace_id_unique_idx",
                background=True,
            )
            # 索引：用于按时间排序列出 traces
            await collection.create_index(
                [("started_at", -1)],
                name="started_at_idx",
                background=True,
            )
            # 复合索引：用于列表页 run 摘要查询
            await collection.create_index(
                [("session_id", 1), ("started_at", -1)],
                name="session_started_at_desc_idx",
                background=True,
            )
            # 索引：用于 EventMerger 查询未合并的已完成 traces
            await collection.create_index(
                [("status", 1), ("metadata.merged", 1)],
                name="status_merged_idx",
                background=True,
            )
            await collection.create_index(
                [
                    ("user_id", 1),
                    ("conversation_search.version", 1),
                    ("conversation_search.terms", 1),
                    ("completed_at", -1),
                ],
                name="user_conversation_terms_completed_idx",
                background=True,
            )
            await collection.create_index(
                [
                    ("conversation_search.version", 1),
                    ("status", 1),
                    ("updated_at", 1),
                ],
                name="conversation_backfill_idx",
                background=True,
            )
            chunks_collection = self.chunks_collection
            await chunks_collection.create_index(
                [("trace_id", 1), ("chunk_index", 1)],
                unique=True,
                name="trace_chunk_unique_idx",
                background=True,
            )
            await chunks_collection.create_index(
                [("session_id", 1), ("run_id", 1), ("chunk_index", 1)],
                name="session_run_chunk_idx",
                background=True,
            )
            await chunks_collection.create_index(
                [("session_id", 1), ("trace_started_at", 1), ("chunk_index", 1)],
                name="session_trace_started_chunk_idx",
                background=True,
            )
            await chunks_collection.create_index(
                [("trace_id", 1), ("end_seq", -1)],
                name="trace_end_seq_idx",
                background=True,
            )
            logger.info("MongoDB indexes ensured for trace_storage")
        except Exception as e:
            logger.warning(f"Failed to create indexes (non-critical): {e}")

    def _start_merger(self):
        """启动事件合并器"""
        if not settings.ENABLE_EVENT_MERGER:
            logger.info("EventMerger disabled by configuration")
            return

        if self._merger is None:
            try:
                from src.infra.session.event_merger import get_event_merger

                self._merger = get_event_merger(self)
                self._merger.start()
                logger.info("EventMerger started successfully")
            except Exception as e:
                logger.warning(f"Failed to start EventMerger: {e}")

    async def get_trace(
        self,
        trace_id: str,
        *,
        include_events: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        获取 trace 摘要，默认不加载大 events 数组。

        Args:
            trace_id: Trace ID
            include_events: 是否返回完整 events 数组

        Returns:
            trace 文档或 None
        """
        try:
            projection = {"_id": 0, "events": 0}
            doc = await self.collection.find_one(
                {"trace_id": trace_id},
                projection,
            )
            if doc is not None and include_events:
                doc["events"] = await self.read_trace_events_compat(trace_id)
            return doc
        except Exception as e:
            logger.error(f"Failed to get trace {trace_id}: {e}")
            return None

    async def get_trace_events(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 trace 的事件列表

        Args:
            trace_id: Trace ID
            event_types: 可选的事件类型过滤
            max_events: 最大返回事件数，防止一次读取超大 trace

        Returns:
            事件列表
        """
        try:
            return await self.read_trace_events_compat(
                trace_id,
                event_types=event_types,
                max_events=max_events,
            )
        except Exception as e:
            logger.error(f"Failed to get trace events for {trace_id}: {e}")
            return []

    async def get_first_trace_event(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch the first matching event from one trace without loading the full events array."""
        try:
            if await self._has_event_chunks(trace_id):
                events = await self.read_trace_events_compat(
                    trace_id,
                    event_types=event_types,
                    max_events=1,
                )
                return events[0] if events else None
        except Exception as e:
            logger.error(f"Failed to get first trace event from chunks for {trace_id}: {e}")
            return None

        pipeline: List[Dict[str, Any]] = [
            {"$match": {"trace_id": trace_id}},
            {
                "$project": {
                    "events.event_type": 1,
                    "events.data": 1,
                    "events.timestamp": 1,
                }
            },
            {"$unwind": "$events"},
        ]
        if event_types:
            pipeline.append({"$match": {"events.event_type": {"$in": event_types}}})
        pipeline.extend(
            [
                {"$limit": 1},
                {
                    "$project": {
                        "_id": 0,
                        "event_type": "$events.event_type",
                        "data": "$events.data",
                        "timestamp": "$events.timestamp",
                    }
                },
            ]
        )

        try:
            async for event in self.collection.aggregate(pipeline):
                return event
            return None
        except Exception as e:
            logger.error(f"Failed to get first trace event for {trace_id}: {e}")
            return None

    async def get_last_trace_event(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch the latest matching event from one trace without returning the full events array."""
        try:
            if await self._has_event_chunks(trace_id):
                bounded_event_types = _bounded_unique_strings(
                    event_types,
                    SESSION_EVENT_FILTER_LIST_LIMIT,
                )
                allowed_types = set(bounded_event_types)
                cursor = self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "events": 1, "chunk_index": 1},
                ).sort("chunk_index", -1)
                async for chunk in cursor:
                    chunk_events = sorted(
                        enumerate(chunk.get("events", []) or []),
                        key=lambda item: _event_seq(item[1], item[0]),
                        reverse=True,
                    )
                    for _index, event in chunk_events:
                        if allowed_types and event.get("event_type") not in allowed_types:
                            continue
                        return event
                events = await self.read_trace_events_compat(
                    trace_id,
                    event_types=bounded_event_types,
                    max_events=None,
                )
                return events[-1] if events else None
        except Exception as e:
            logger.error(f"Failed to get last trace event from chunks for {trace_id}: {e}")
            return None

        pipeline: List[Dict[str, Any]] = [
            {"$match": {"trace_id": trace_id}},
            {
                "$project": {
                    "events.event_type": 1,
                    "events.data": 1,
                    "events.timestamp": 1,
                    "events.seq": 1,
                }
            },
            {"$unwind": "$events"},
        ]
        if event_types:
            pipeline.append({"$match": {"events.event_type": {"$in": event_types}}})
        pipeline.extend(
            [
                {"$sort": {"events.seq": -1, "events.timestamp": -1}},
                {"$limit": 1},
                {
                    "$project": {
                        "_id": 0,
                        "event_type": "$events.event_type",
                        "data": "$events.data",
                        "timestamp": "$events.timestamp",
                    }
                },
            ]
        )

        try:
            async for event in self.collection.aggregate(pipeline):
                return event
            return None
        except Exception as e:
            logger.error(f"Failed to get last trace event for {trace_id}: {e}")
            return None

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
        limit = _clamp_positive_int(limit, default=50, maximum=TRACE_LIST_LIMIT)
        skip = _clamp_nonnegative_int(skip)
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

    async def list_run_summaries(
        self,
        session_id: str,
        limit: int = 50,
        skip: int = 0,
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出会话 run 摘要，并只投影第一条用户消息事件。"""
        limit = _clamp_positive_int(limit, default=50, maximum=TRACE_LIST_LIMIT)
        skip = _clamp_nonnegative_int(skip)
        query = {"session_id": session_id}
        if trace_id:
            query["trace_id"] = trace_id

        projection: Dict[str, Any] = {
            "_id": 0,
            "run_id": 1,
            "trace_id": 1,
            "agent_id": 1,
            "started_at": 1,
            "completed_at": 1,
            "status": 1,
            "event_count": 1,
            "first_user_message_preview": 1,
            "recommend_questions": 1,
        }

        try:
            cursor = (
                self.collection.find(query, projection)
                .sort("started_at", -1)
                .skip(skip)
                .limit(limit)
            )
            traces = await cursor.to_list(length=limit)
            summaries: List[Dict[str, Any]] = []
            for trace in traces:
                user_message = None
                preview = trace.get("first_user_message_preview") or {}
                if not preview and trace.get("trace_id"):
                    preview = (
                        await self.get_first_trace_event(
                            trace_id=str(trace.get("trace_id")),
                            event_types=["user:message"],
                        )
                        or {}
                    )
                if preview:
                    data = preview.get("data", {})
                    user_message = data.get("content") or data.get("message") or ""
                    if user_message and len(user_message) > 20:
                        user_message = user_message[:17] + "..."

                summaries.append(
                    {
                        "run_id": trace.get("run_id"),
                        "trace_id": trace.get("trace_id"),
                        "agent_id": trace.get("agent_id"),
                        "started_at": trace.get("started_at"),
                        "completed_at": trace.get("completed_at"),
                        "status": trace.get("status"),
                        "event_count": trace.get("event_count", 0),
                        "user_message": user_message,
                        "recommend_questions": _normalize_recommend_questions(
                            trace.get("recommend_questions")
                        ),
                    }
                )
            return summaries
        except Exception as e:
            logger.error(f"Failed to list run summaries: {e}")
            return []

    async def _assemble_session_events_snapshot(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None,
        run_id: Optional[str] = None,
        exclude_run_id: Optional[str] = None,
        completed_only: bool = True,
        run_ids: Optional[List[str]] = None,
        max_events: Optional[int] = None,
        active_run_id: Optional[str] = None,
    ) -> SessionEventsSnapshot:
        """
        获取会话的所有事件（跨 traces 聚合）

        按 run 顺序（started_at）合并事件，每个 run 内的事件保持原有顺序。

        Args:
            session_id: 会话 ID
            event_types: 可选的事件类型过滤列表
            run_id: 可选的运行 ID 过滤（用于隔离多轮对话）
            exclude_run_id: 可选的运行 ID 排除（用于排除正在运行的 run）
            completed_only: 是否只返回成功完成的 trace 中的事件（默认 True）
            run_ids: 可选的运行 ID 列表过滤（用于部分分享等场景）
            max_events: 可选的最大返回事件数

        Returns:
            事件列表，按 run 顺序合并
        """
        try:
            event_types = _bounded_unique_strings(event_types, SESSION_EVENT_FILTER_LIST_LIMIT)
            run_ids = _bounded_unique_strings(run_ids, SESSION_EVENT_FILTER_LIST_LIMIT)
            # 构建查询条件
            match_query: Dict[str, Any] = {"session_id": session_id}
            if run_ids:
                match_query["run_id"] = {"$in": run_ids}
            elif run_id:
                match_query["run_id"] = run_id
            if exclude_run_id:
                match_query["run_id"] = {"$ne": exclude_run_id}
            # 快照需要同时观察 active trace 的状态；其余读取保持旧过滤语义。
            if completed_only and not active_run_id:
                match_query["status"] = {"$ne": "running"}

            if max_events is not None:
                max_events = _clamp_event_read_limit(
                    max_events,
                    default=_get_session_event_read_default_limit(),
                )

            if max_events is not None and max_events <= 0:
                return SessionEventsSnapshot(events=[])

            cursor = self.collection.find(
                match_query,
                {
                    "_id": 0,
                    "trace_id": 1,
                    "run_id": 1,
                    "status": 1,
                    "started_at": 1,
                    "events": 1,
                    "recommend_questions": 1,
                    "recommend_questions_updated_at": 1,
                },
            ).sort("started_at", 1)

            traces: List[Dict[str, Any]] = []
            async for trace in cursor:
                if completed_only and trace.get("status") == "running":
                    if not active_run_id or trace.get("run_id") != active_run_id:
                        continue
                traces.append(trace)

            events_by_trace = await self.read_trace_events_batch_compat(
                traces,
                event_types=event_types,
            )
            events: List[Dict[str, Any]] = []
            history_mode: Literal["complete", "active_user_only"] = "complete"
            stream_run_id: Optional[str] = None
            for trace in traces:
                trace_id = trace.get("trace_id")
                if not trace_id:
                    continue
                trace_events = list(events_by_trace.get(str(trace_id), []))
                is_active_running = bool(
                    active_run_id
                    and trace.get("run_id") == active_run_id
                    and trace.get("status") == "running"
                )
                if is_active_running:
                    trace_events = [
                        event for event in trace_events if event.get("event_type") == "user:message"
                    ]
                    history_mode = "active_user_only"
                    stream_run_id = active_run_id
                questions = _normalize_recommend_questions(trace.get("recommend_questions"))
                recommendation_requested = not event_types or bool(
                    {"recommend:questions", "followup:questions"}.intersection(event_types)
                )
                has_legacy_recommendation = any(
                    event.get("event_type") in {"recommend:questions", "followup:questions"}
                    for event in trace_events
                )
                if questions and recommendation_requested and not has_legacy_recommendation:
                    compatibility_event_type = "recommend:questions"
                    if (
                        event_types
                        and "recommend:questions" not in event_types
                        and "followup:questions" in event_types
                    ):
                        compatibility_event_type = "followup:questions"
                    trace_events.append(
                        {
                            "event_type": compatibility_event_type,
                            "data": {"questions": questions},
                            "timestamp": trace.get("recommend_questions_updated_at")
                            or trace.get("started_at"),
                        }
                    )
                for event in trace_events:
                    item = {
                        "trace_id": trace_id,
                        "run_id": trace.get("run_id"),
                        "event_type": event.get("event_type"),
                        "data": event.get("data", {}),
                        "timestamp": event.get("timestamp"),
                    }
                    if "seq" in event:
                        item["seq"] = event.get("seq")
                    events.append(item)
                    if max_events is not None and len(events) >= max_events:
                        logger.debug(
                            f"Session {session_id} (run_id={run_id}) returned {len(events)} bounded events"
                        )
                        return SessionEventsSnapshot(
                            events=events,
                            history_mode=history_mode,
                            stream_run_id=stream_run_id,
                        )

            logger.debug(
                f"Session {session_id} (run_id={run_id}) returned {len(events)} bounded events"
            )
            return SessionEventsSnapshot(
                events=events,
                history_mode=history_mode,
                stream_run_id=stream_run_id,
            )
        except Exception as e:
            logger.error(f"Failed to get session events: {e}")
            return SessionEventsSnapshot(events=[])

    async def get_session_events_snapshot(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None,
        run_id: Optional[str] = None,
        exclude_run_id: Optional[str] = None,
        completed_only: bool = True,
        run_ids: Optional[List[str]] = None,
        max_events: Optional[int] = None,
        active_run_id: Optional[str] = None,
    ) -> SessionEventsSnapshot:
        """Read history and classify whether the active run still needs SSE replay."""
        return await self._assemble_session_events_snapshot(
            session_id,
            event_types,
            run_id=run_id,
            exclude_run_id=exclude_run_id,
            completed_only=completed_only,
            run_ids=run_ids,
            max_events=max_events,
            active_run_id=active_run_id,
        )

    async def get_session_events(
        self,
        session_id: str,
        event_types: Optional[List[str]] = None,
        run_id: Optional[str] = None,
        exclude_run_id: Optional[str] = None,
        completed_only: bool = True,
        run_ids: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get session events while preserving the legacy list-only contract."""
        snapshot = await self._assemble_session_events_snapshot(
            session_id,
            event_types,
            run_id=run_id,
            exclude_run_id=exclude_run_id,
            completed_only=completed_only,
            run_ids=run_ids,
            max_events=max_events,
        )
        return snapshot.events

    async def iter_session_events_for_cleanup(
        self,
        session_id: str,
        *,
        event_types: Optional[List[str]] = None,
        cutoff: Any = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Strictly stream session events for destructive lifecycle operations.

        Unlike the legacy read API, this path propagates storage failures so a
        caller cannot mistake an unavailable trace store for an empty session.
        It yields one trace at a time rather than materializing the session's
        complete event history.
        """
        allowed_types = set(_bounded_unique_strings(event_types, SESSION_EVENT_FILTER_LIST_LIMIT))
        query: Dict[str, Any] = {"session_id": session_id}
        if cutoff is not None:
            query["started_at"] = {"$lte": cutoff}
        cursor = self.collection.find(
            query,
            {
                "_id": 0,
                "trace_id": 1,
                "run_id": 1,
                "started_at": 1,
                "events": 1,
            },
        ).sort("started_at", 1)

        async for trace in cursor:
            trace_id = str(trace.get("trace_id") or "")
            if not trace_id:
                continue
            first_chunk = None
            first_chunk_cursor = (
                self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "chunk_index": 1, "start_seq": 1, "events": 1},
                )
                .sort("chunk_index", 1)
                .limit(1)
            )
            async for chunk in first_chunk_cursor:
                first_chunk = chunk
                break

            if first_chunk:
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            _event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
                for index, event in enumerate(trace.get("events", []) or [], start=1):
                    if _event_seq(event, index) >= first_chunk_start_seq:
                        continue
                    if allowed_types and event.get("event_type") not in allowed_types:
                        continue
                    yield {
                        "trace_id": trace_id,
                        "run_id": trace.get("run_id"),
                        "event_type": event.get("event_type"),
                        "data": event.get("data", {}),
                        "timestamp": event.get("timestamp"),
                        **({"seq": event["seq"]} if "seq" in event else {}),
                    }
                async for chunk in self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "chunk_index": 1, "events": 1},
                ).sort("chunk_index", 1):
                    for _index, event in sorted(
                        enumerate(chunk.get("events", []) or []),
                        key=lambda item: _event_seq(item[1], item[0]),
                    ):
                        if allowed_types and event.get("event_type") not in allowed_types:
                            continue
                        yield {
                            "trace_id": trace_id,
                            "run_id": trace.get("run_id"),
                            "event_type": event.get("event_type"),
                            "data": event.get("data", {}),
                            "timestamp": event.get("timestamp"),
                            **({"seq": event["seq"]} if "seq" in event else {}),
                        }
                continue
            else:
                events = trace.get("events", []) or []
            for event in events:
                if allowed_types and event.get("event_type") not in allowed_types:
                    continue
                yield {
                    "trace_id": trace_id,
                    "run_id": trace.get("run_id"),
                    "event_type": event.get("event_type"),
                    "data": event.get("data", {}),
                    "timestamp": event.get("timestamp"),
                    **({"seq": event["seq"]} if "seq" in event else {}),
                }

    async def snapshot_session_traces_for_cleanup(
        self, session_id: str, cutoff: Any
    ) -> dict[str, Any]:
        """Capture versioned terminal parents and directly discoverable orphan chunks."""
        eligible_query = {
            "session_id": session_id,
            "status": {"$in": list(ATTACHMENT_CLEAR_TERMINAL_STATUSES)},
            "updated_at": {"$lte": cutoff},
            ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
        }
        cursor = self.collection.find(
            eligible_query,
            {
                "_id": 1,
                "trace_id": 1,
                "run_id": 1,
                "status": 1,
                "updated_at": 1,
                "events": 1,
            },
        )
        parents = await cursor.to_list(length=None)
        all_parent_docs = await self.collection.find(
            {"session_id": session_id},
            {"_id": 1, "trace_id": 1},
        ).to_list(length=None)
        all_parent_trace_ids = {
            str(doc["trace_id"]) for doc in all_parent_docs if doc.get("trace_id")
        }
        trace_ids = [str(doc["trace_id"]) for doc in parents if doc.get("trace_id")]
        chunks = await self.chunks_collection.find(
            {
                "session_id": session_id,
                "updated_at": {"$lte": cutoff},
            },
            {
                "_id": 1,
                "trace_id": 1,
                "chunk_index": 1,
                "start_seq": 1,
                "updated_at": 1,
                "events": 1,
            },
        ).to_list(length=None)
        events: list[dict] = []
        chunks_by_trace: dict[str, list[dict]] = {}
        for chunk in chunks:
            chunks_by_trace.setdefault(str(chunk.get("trace_id") or ""), []).append(chunk)
        groups: list[dict[str, Any]] = []
        selected_chunk_ids: list[Any] = []
        for parent_index, parent in enumerate(parents):
            trace_id = str(parent.get("trace_id") or "")
            trace_chunks = sorted(
                chunks_by_trace.get(trace_id, []),
                key=lambda chunk: int(chunk.get("chunk_index") or 0),
            )
            parent_group_id = f"parent-{parent_index}"
            parent_events: list[dict]
            if not trace_chunks:
                parent_events = list(parent.get("events") or [])
            else:
                first_chunk = trace_chunks[0]
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            _event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
                parent_events = [
                    event
                    for index, event in enumerate(parent.get("events") or [], start=1)
                    if _event_seq(event, index) < first_chunk_start_seq
                ]
            events.extend(parent_events)
            groups.append(
                {
                    "id": parent_group_id,
                    "kind": "parent",
                    "document_id": parent["_id"],
                    "trace_id": trace_id,
                    "updated_at": parent.get("updated_at"),
                    "terminal_status": parent.get("status"),
                    "events": parent_events,
                }
            )
            for chunk_index, chunk in enumerate(trace_chunks):
                chunk_events = [
                    event
                    for _index, event in sorted(
                        enumerate(chunk.get("events") or []),
                        key=lambda item: _event_seq(item[1], item[0]),
                    )
                ]
                events.extend(chunk_events)
                selected_chunk_ids.append(chunk["_id"])
                groups.append(
                    {
                        "id": f"parent-{parent_index}-chunk-{chunk_index}",
                        "kind": "chunk",
                        "document_id": chunk["_id"],
                        "trace_id": trace_id,
                        "updated_at": chunk.get("updated_at"),
                        "parent_group_id": parent_group_id,
                        "events": chunk_events,
                    }
                )

        orphan_index = 0
        eligible_trace_ids = set(trace_ids)
        for chunk in chunks:
            trace_id = str(chunk.get("trace_id") or "")
            if trace_id in eligible_trace_ids or trace_id in all_parent_trace_ids:
                continue
            chunk_events = [
                event
                for _index, event in sorted(
                    enumerate(chunk.get("events") or []),
                    key=lambda item: _event_seq(item[1], item[0]),
                )
            ]
            events.extend(chunk_events)
            selected_chunk_ids.append(chunk["_id"])
            groups.append(
                {
                    "id": f"orphan-chunk-{orphan_index}",
                    "kind": "chunk",
                    "document_id": chunk["_id"],
                    "trace_id": trace_id,
                    "updated_at": chunk.get("updated_at"),
                    "events": chunk_events,
                }
            )
            orphan_index += 1
        return {
            "parent_ids": [doc["_id"] for doc in parents],
            "chunk_ids": selected_chunk_ids,
            "trace_ids": trace_ids,
            "events": events,
            "groups": groups,
        }

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
            事件列表，按写入顺序
        """
        return await self.get_session_events(session_id, event_types, run_id=run_id)

    async def delete_trace(self, trace_id: str) -> bool:
        """删除 trace"""
        try:
            result = await self.collection.delete_one({"trace_id": trace_id})
            if result.deleted_count > 0:
                await self.chunks_collection.delete_many({"trace_id": trace_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete trace {trace_id}: {e}")
            return False

    async def delete_session_traces(self, session_id: str) -> int:
        """删除会话的所有 traces"""
        try:
            cursor = self.collection.find(
                {"session_id": session_id},
                {"_id": 0, "trace_id": 1},
            )
            trace_docs = await cursor.to_list(length=None)
            trace_ids = [trace.get("trace_id") for trace in trace_docs if trace.get("trace_id")]
            if trace_ids:
                await self.chunks_collection.delete_many({"trace_id": {"$in": trace_ids}})
            else:
                await self.chunks_collection.delete_many({"session_id": session_id})
            result = await self.collection.delete_many({"session_id": session_id})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Failed to delete session traces: {e}")
            return 0

    async def delete_session_traces_strict(
        self, session_id: str, *, trace_ids: list[str], cutoff: Any
    ) -> int:
        """Delete all session traces and verify the destructive postcondition."""
        query = {
            "session_id": session_id,
            "trace_id": {"$in": trace_ids},
            "started_at": {"$lte": cutoff},
        }
        cursor = self.collection.find(
            query,
            {"_id": 0, "trace_id": 1},
        )
        trace_docs = await cursor.to_list(length=None)
        trace_ids = [trace.get("trace_id") for trace in trace_docs if trace.get("trace_id")]
        if trace_ids:
            await self.chunks_collection.delete_many({"trace_id": {"$in": trace_ids}})
        await self.chunks_collection.delete_many(
            {"session_id": session_id, "trace_started_at": {"$lte": cutoff}}
        )
        result = await self.collection.delete_many(query)
        if await self.collection.find_one(query, {"_id": 1}):
            raise RuntimeError(f"session_trace_delete_incomplete: {session_id}")
        if await self.chunks_collection.find_one(
            {"session_id": session_id, "trace_started_at": {"$lte": cutoff}}, {"_id": 1}
        ):
            raise RuntimeError(f"session_chunk_delete_incomplete: {session_id}")
        return result.deleted_count

    async def delete_attachment_clear_group(
        self,
        session_id: str,
        group: dict[str, Any],
    ) -> str:
        """CAS-delete one persisted parent or chunk snapshot group."""
        kind = group.get("kind")
        document_id = group.get("document_id")
        updated_at = group.get("updated_at")
        trace_id = str(group.get("trace_id") or "")
        query: dict[str, Any] = {
            "_id": document_id,
            "session_id": session_id,
            "updated_at": updated_at,
        }
        if trace_id:
            query["trace_id"] = trace_id
        if kind == "parent":
            terminal_status = group.get("terminal_status")
            if terminal_status not in ATTACHMENT_CLEAR_TERMINAL_STATUSES:
                raise ValueError("attachment_clear_parent_status_invalid")
            query["status"] = terminal_status
            query[ATTACHMENT_CHUNK_WRITE_FIELD] = {"$exists": False}
            collection = self.collection
        elif kind == "chunk":
            collection = self.chunks_collection
        else:
            raise ValueError("attachment_clear_group_kind_invalid")

        result = await collection.delete_many(query)
        if result.deleted_count > 0:
            return "deleted"
        survivor = await collection.find_one({"_id": document_id}, {"_id": 1})
        return "survivor" if survivor else "deleted"

    async def has_session_trace_documents(self, session_id: str) -> bool:
        """Return whether any parent or directly session-scoped chunk survives."""
        if await self.collection.find_one({"session_id": session_id}, {"_id": 1}):
            return True
        return bool(await self.chunks_collection.find_one({"session_id": session_id}, {"_id": 1}))

    async def close(self) -> None:
        task = self._indexes_task
        self._indexes_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if hasattr(self, "_indexes_ensured"):
            delattr(self, "_indexes_ensured")
        self._collection = None
        self._chunks_collection = None
        self._session_storage = None
        self._merger = None


# Singleton
_trace_storage: Optional[TraceStorage] = None


def get_trace_storage() -> TraceStorage:
    """获取 TraceStorage 单例"""
    global _trace_storage
    if _trace_storage is None:
        _trace_storage = TraceStorage()
    return _trace_storage


async def close_trace_storage() -> None:
    """Release the singleton TraceStorage without creating it during shutdown."""
    global _trace_storage
    storage = _trace_storage
    _trace_storage = None
    if storage is not None:
        await storage.close()

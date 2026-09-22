"""Compat read path for chunked trace events.

Split out of ``trace_event_chunks`` to keep that module within the
1000-line backend source limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.session import trace_storage as trace_storage_helpers

logger = get_logger(__name__)


class TraceEventReadCompatMixin:
    """Read trace events from chunks when present, otherwise legacy traces.events."""

    if TYPE_CHECKING:
        collection: Any
        chunks_collection: Any

    async def _has_event_chunks(self, trace_id: str) -> bool:
        try:
            chunk = await self.chunks_collection.find_one({"trace_id": trace_id}, {"_id": 1})
            return chunk is not None
        except Exception as e:
            logger.debug("Failed to probe trace event chunks for %s: %s", trace_id, e)
            return False

    async def read_trace_events_compat(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read trace events from chunks when present, otherwise legacy traces.events."""
        event_types = trace_storage_helpers._bounded_unique_strings(
            event_types,
            trace_storage_helpers.SESSION_EVENT_FILTER_LIST_LIMIT,
        )
        allowed_types = set(event_types)
        if max_events is not None:
            max_events = trace_storage_helpers._clamp_event_read_limit(
                max_events,
                default=trace_storage_helpers.TRACE_EVENTS_DEFAULT_LIMIT,
            )
            if max_events <= 0:
                return []

        def _accepts(event: Dict[str, Any]) -> bool:
            return not allowed_types or event.get("event_type") in allowed_types

        events: List[Dict[str, Any]] = []
        if await self._has_event_chunks(trace_id):
            first_chunk = None
            first_chunk_cursor = (
                self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "start_seq": 1, "events.seq": 1},
                )
                .sort("chunk_index", 1)
                .limit(1)
            )
            async for chunk in first_chunk_cursor:
                first_chunk = chunk
                break
            first_chunk_start_seq = 1
            if first_chunk:
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            trace_storage_helpers._event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
            if first_chunk_start_seq > 1:
                trace_doc = await self.collection.find_one(
                    {"trace_id": trace_id},
                    {"_id": 0, "events": 1},
                )
                for index, event in enumerate((trace_doc or {}).get("events", []) or [], start=1):
                    if trace_storage_helpers._event_seq(event, index) >= first_chunk_start_seq:
                        continue
                    if not _accepts(event):
                        continue
                    events.append(event)
                    if max_events is not None and len(events) >= max_events:
                        return events

            cursor = self.chunks_collection.find(
                {"trace_id": trace_id},
                {"_id": 0, "events": 1, "chunk_index": 1},
            ).sort("chunk_index", 1)
            async for chunk in cursor:
                chunk_events = sorted(
                    enumerate(chunk.get("events", []) or []),
                    key=lambda item: trace_storage_helpers._event_seq(item[1], item[0]),
                )
                for _index, event in chunk_events:
                    if not _accepts(event):
                        continue
                    events.append(event)
                    if max_events is not None and len(events) >= max_events:
                        return events
            return events

        trace_doc = await self.collection.find_one(
            {"trace_id": trace_id},
            {"_id": 0, "events": 1},
        )
        for event in (trace_doc or {}).get("events", []) or []:
            if not _accepts(event):
                continue
            events.append(event)
            if max_events is not None and len(events) >= max_events:
                break
        return events

    async def read_trace_events_batch_compat(
        self,
        trace_docs: List[Dict[str, Any]],
        event_types: Optional[List[str]] = None,
        active_user_only_trace_ids: Optional[set[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Read legacy/chunk events for many traces with one chunk query."""
        event_types = trace_storage_helpers._bounded_unique_strings(
            event_types,
            trace_storage_helpers.SESSION_EVENT_FILTER_LIST_LIMIT,
        )
        allowed_types = set(event_types)
        trace_ids = [
            str(trace_doc.get("trace_id") or "")
            for trace_doc in trace_docs
            if trace_doc.get("trace_id")
        ]
        if not trace_ids:
            return {}
        active_user_only_trace_ids = active_user_only_trace_ids or set()

        events_projection: Any = 1
        if active_user_only_trace_ids:
            events_projection = {
                "$cond": [
                    {"$in": ["$trace_id", sorted(active_user_only_trace_ids)]},
                    {
                        "$filter": {
                            "input": {"$ifNull": ["$events", []]},
                            "as": "event",
                            "cond": {"$eq": ["$$event.event_type", "user:message"]},
                        }
                    },
                    "$events",
                ]
            }

        chunks_by_trace: Dict[str, List[Dict[str, Any]]] = {trace_id: [] for trace_id in trace_ids}
        cursor = self.chunks_collection.find(
            {"trace_id": {"$in": trace_ids}},
            {
                "_id": 0,
                "trace_id": 1,
                "chunk_index": 1,
                "start_seq": 1,
                "events": events_projection,
            },
        ).sort([("trace_id", 1), ("chunk_index", 1)])
        async for chunk in cursor:
            trace_id = str(chunk.get("trace_id") or "")
            if trace_id in chunks_by_trace:
                chunks_by_trace[trace_id].append(chunk)

        def _accepts(event: Dict[str, Any]) -> bool:
            return not allowed_types or event.get("event_type") in allowed_types

        def _accepts_for_trace(trace_id: str, event: Dict[str, Any]) -> bool:
            if trace_id in active_user_only_trace_ids and event.get("event_type") != "user:message":
                return False
            return _accepts(event)

        events_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        for trace_doc in trace_docs:
            trace_id = str(trace_doc.get("trace_id") or "")
            if not trace_id:
                continue

            chunks = chunks_by_trace.get(trace_id, [])
            first_chunk_start_seq: int | None = None
            if chunks:
                first_chunk = chunks[0]
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            trace_storage_helpers._event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )

            events: List[Dict[str, Any]] = []
            for index, event in enumerate(trace_doc.get("events", []) or [], start=1):
                if (
                    first_chunk_start_seq is not None
                    and trace_storage_helpers._event_seq(event, index) >= first_chunk_start_seq
                ):
                    continue
                if _accepts_for_trace(trace_id, event):
                    events.append(event)

            for chunk in chunks:
                chunk_events = sorted(
                    enumerate(chunk.get("events", []) or []),
                    key=lambda item: trace_storage_helpers._event_seq(item[1], item[0]),
                )
                for _index, event in chunk_events:
                    if _accepts_for_trace(trace_id, event):
                        events.append(event)

            events_by_trace[trace_id] = events

        return events_by_trace

    async def get_first_trace_events_batch(
        self,
        trace_ids: List[str],
        event_types: Optional[List[str]] = None,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """批量取每个 trace 的第一条匹配事件（最多 2 次查询，替代 N+1）。

        语义与逐条调用 ``get_first_trace_event`` 等价：
        - chunked trace：legacy 头部事件（seq < 首个 chunk 的 start_seq）优先，
          其次按 chunk 顺序取第一个匹配；
        - legacy trace：events 数组顺序的第一个匹配；
        - 无匹配返回 None；单条查询失败按空结果处理（与旧逐条路径吞错一致）。
        """
        bounded_ids = trace_storage_helpers._bounded_unique_strings(
            trace_ids, trace_storage_helpers.TRACE_LIST_LIMIT
        )
        if not bounded_ids:
            return {}
        bounded_types = trace_storage_helpers._bounded_unique_strings(
            event_types, trace_storage_helpers.SESSION_EVENT_FILTER_LIST_LIMIT
        )
        allowed = set(bounded_types)

        # 1) chunks：一次聚合取回整批 trace 的匹配事件（chunk 内已 $filter，只传输匹配项）
        chunks_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        try:
            match: Dict[str, Any] = {"trace_id": {"$in": bounded_ids}}
            if allowed:
                match["events.event_type"] = {"$in": sorted(allowed)}
            events_projection: Any = (
                {
                    "$filter": {
                        "input": {"$ifNull": ["$events", []]},
                        "as": "event",
                        "cond": {"$in": ["$$event.event_type", sorted(allowed)]},
                    }
                }
                if allowed
                else 1
            )
            pipeline: List[Dict[str, Any]] = [
                {"$match": match},
                {"$sort": {"trace_id": 1, "chunk_index": 1}},
                {
                    "$project": {
                        "_id": 0,
                        "trace_id": 1,
                        "start_seq": 1,
                        "events": events_projection,
                    }
                },
                {
                    "$group": {
                        "_id": "$trace_id",
                        "chunks": {"$push": {"start_seq": "$start_seq", "events": "$events"}},
                    }
                },
            ]
            async for doc in await self.chunks_collection.aggregate(pipeline):
                chunks_by_trace[str(doc.get("_id"))] = list(doc.get("chunks") or [])
        except Exception as e:
            logger.error(f"Failed to batch read first trace events from chunks: {e}")
            chunks_by_trace = {}

        # 2) legacy events / chunk 头部：一次查询取回整批 trace 的 events 数组
        legacy_events_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        try:
            cursor = self.collection.find(
                {"trace_id": {"$in": bounded_ids}},
                {"_id": 0, "trace_id": 1, "events": 1},
            )
            async for doc in cursor:
                legacy_events_by_trace[str(doc.get("trace_id"))] = list(doc.get("events") or [])
        except Exception as e:
            logger.error(f"Failed to batch read first trace events from legacy traces: {e}")
            legacy_events_by_trace = {}

        def _accepts(event: Dict[str, Any]) -> bool:
            return not allowed or event.get("event_type") in allowed

        result: Dict[str, Optional[Dict[str, Any]]] = {}
        for trace_id in bounded_ids:
            chunks = chunks_by_trace.get(trace_id) or []
            first_chunk_start_seq: Optional[int] = None
            if chunks:
                first_chunk = chunks[0]
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            trace_storage_helpers._event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events") or [])
                        ),
                        default=1,
                    )
                )
            first: Optional[Dict[str, Any]] = None
            for index, event in enumerate(legacy_events_by_trace.get(trace_id) or [], start=1):
                if (
                    first_chunk_start_seq is not None
                    and trace_storage_helpers._event_seq(event, index) >= first_chunk_start_seq
                ):
                    continue
                if _accepts(event):
                    first = event
                    break
            if first is None:
                for chunk in chunks:
                    ordered = sorted(
                        enumerate(chunk.get("events") or []),
                        key=lambda item: trace_storage_helpers._event_seq(item[1], item[0]),
                    )
                    for _index, event in ordered:
                        if _accepts(event):
                            first = event
                            break
                    if first is not None:
                        break
            result[trace_id] = first
        return result

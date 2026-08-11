"""Trace creation, event writes, and completion operations."""

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.infra.logging import get_logger
from src.infra.session._trace_storage_support import _normalize_recommend_questions
from src.infra.utils.datetime import utc_now, utc_now_iso

logger = get_logger("src.infra.session.trace_storage")

_USAGE_LOGS_ENABLED = True  # 是否在 trace 完成时写入 usage_logs 集合
_ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
_TRACE_EVENT_REVISION_FIELD = "event_revision"


class TraceStorageWriteMixin:
    """Write-side behavior composed into the public TraceStorage class."""

    if TYPE_CHECKING:
        collection: Any
        _merger: Any

        async def ensure_indexes_if_needed(self) -> None: ...

        async def acquire_session_trace_write(self, session_id: str) -> bool: ...

        async def release_session_trace_write(self, session_id: str) -> None: ...

        async def _has_event_chunks(self, trace_id: str) -> bool: ...

        async def read_trace_events_compat(
            self,
            trace_id: str,
            event_types: Optional[List[str]] = None,
            max_events: Optional[int] = None,
        ) -> List[Dict[str, Any]]: ...

        async def replace_trace_events_with_chunks(
            self,
            trace_doc: Dict[str, Any],
            events: List[Dict[str, Any]],
            *,
            mark_storage_chunked: bool = True,
            remove_legacy_events: bool = True,
            parent_updates: Optional[Dict[str, Any]] = None,
        ) -> bool: ...

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
        创建 trace 文档（幂等：若已存在则跳过）

        Args:
            trace_id: 唯一 trace 标识
            session_id: 会话 ID
            agent_id: Agent ID
            run_id: 运行 ID
            user_id: 用户 ID
            metadata: 额外元数据

        Returns:
            是否创建成功（已存在也返回 True）
        """
        from pymongo.errors import DuplicateKeyError

        if not await self.acquire_session_trace_write(session_id):
            logger.warning("Trace creation rejected by session delete fence: %s", session_id)
            return False
        try:
            await self.ensure_indexes_if_needed()
            now = utc_now()
            doc: Dict[str, Any] = {
                "trace_id": trace_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "user_id": user_id,
                "events": [],
                "event_count": 0,
                _TRACE_EVENT_REVISION_FIELD: 0,
                "started_at": now,
                "updated_at": now,
                "status": "running",
                "metadata": metadata or {},
            }

            try:
                result = await self.collection.insert_one(doc)
                logger.info(
                    "Created trace %s for session %s, inserted_id=%s",
                    trace_id,
                    session_id,
                    result.inserted_id,
                )
                return True
            except DuplicateKeyError:
                # Trace already exists (e.g., queued path created it before dequeue)
                logger.debug("Trace %s already exists, skipping", trace_id)
                return True
            except Exception as e:
                logger.error(f"Failed to create trace {trace_id}: {e}")
                import traceback

                traceback.print_exc()
                return False
        finally:
            await self.release_session_trace_write(session_id)

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
                {
                    "trace_id": trace_id,
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                {
                    "$push": {
                        "events": {
                            "event_type": event_type,
                            "data": data,
                            "timestamp": utc_now(),
                        }
                    },
                    "$inc": {"event_count": 1, _TRACE_EVENT_REVISION_FIELD: 1},
                    "$set": {
                        "updated_at": utc_now(),
                        "metadata.merged": False,
                    },
                },
            )
            if result.modified_count == 0:
                logger.warning(f"append_event: trace {trace_id} not found or not modified")
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to append event to trace {trace_id}: {e}")
            return False

    async def set_run_recommend_questions(
        self,
        session_id: str,
        run_id: str,
        questions: List[str],
    ) -> bool:
        """Persist bounded recommendations on the trace identified by a run."""
        normalized = _normalize_recommend_questions(questions)
        if not session_id or not run_id or not normalized:
            return False

        try:
            await self.ensure_indexes_if_needed()
            now = utc_now()
            result = await self.collection.update_one(
                {
                    "session_id": session_id,
                    "run_id": run_id,
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                {
                    "$inc": {_TRACE_EVENT_REVISION_FIELD: 1},
                    "$set": {
                        "recommend_questions": normalized,
                        "recommend_questions_updated_at": now,
                        "updated_at": now,
                    },
                },
            )
            if result.modified_count == 0:
                logger.warning(
                    "Recommendation trace not found or unchanged: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
            return result.modified_count > 0
        except Exception as e:
            logger.warning(
                "Failed to persist recommendations: session=%s, run_id=%s, error=%s",
                session_id,
                run_id,
                e,
            )
            return False

    async def _ensure_token_usage_event(self, trace_id: str) -> None:
        """Insert a zero token usage event before done when a trace has no usage event yet."""
        now = utc_now()
        usage_event = {
            "event_type": "token:usage",
            "data": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "duration": 0.0,
                "timestamp": utc_now_iso(),
            },
            "timestamp": now,
        }
        try:
            if await self._has_event_chunks(trace_id):
                events = await self.read_trace_events_compat(trace_id)
                if any(event.get("event_type") == "token:usage" for event in events):
                    return
                done_index = next(
                    (
                        index
                        for index, event in enumerate(events)
                        if event.get("event_type") == "done"
                    ),
                    -1,
                )
                next_events = list(events)
                if done_index >= 0:
                    next_events.insert(done_index, usage_event)
                else:
                    next_events.append(usage_event)
                trace_doc = await self.collection.find_one(
                    {"trace_id": trace_id},
                    {"_id": 0, "events": 0},
                )
                if trace_doc:
                    await self.replace_trace_events_with_chunks(trace_doc, next_events)
                return

            await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    "events.event_type": {"$ne": "token:usage"},
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                [
                    {
                        "$set": {
                            "events": {
                                "$let": {
                                    "vars": {
                                        "done_index": {
                                            "$indexOfArray": ["$events.event_type", "done"]
                                        }
                                    },
                                    "in": {
                                        "$cond": [
                                            {"$gte": ["$$done_index", 0]},
                                            {
                                                "$concatArrays": [
                                                    {"$slice": ["$events", 0, "$$done_index"]},
                                                    [usage_event],
                                                    {
                                                        "$slice": [
                                                            "$events",
                                                            "$$done_index",
                                                            {
                                                                "$subtract": [
                                                                    {"$size": "$events"},
                                                                    "$$done_index",
                                                                ]
                                                            },
                                                        ]
                                                    },
                                                ]
                                            },
                                            {"$concatArrays": ["$events", [usage_event]]},
                                        ]
                                    },
                                }
                            },
                            "event_count": {"$add": [{"$ifNull": ["$event_count", 0]}, 1]},
                            _TRACE_EVENT_REVISION_FIELD: {
                                "$add": [
                                    {"$ifNull": [f"${_TRACE_EVENT_REVISION_FIELD}", 0]},
                                    1,
                                ]
                            },
                            "updated_at": now,
                        }
                    }
                ],
            )
        except Exception as e:
            logger.warning("Failed to ensure token usage event for trace %s: %s", trace_id, e)

    async def complete_trace(
        self,
        trace_id: str,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
        ensure_token_usage: bool = True,
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
            "$inc": {_TRACE_EVENT_REVISION_FIELD: 1},
            "$set": {
                "status": status,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            },
        }
        if metadata:
            for key, value in metadata.items():
                update["$set"][f"metadata.{key}"] = value

        try:
            await self.ensure_indexes_if_needed()
            if ensure_token_usage:
                await self._ensure_token_usage_event(trace_id)
            result = await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                update,
            )
            # 异步写入 usage_logs 集合（fire-and-forget，失败不影响主流程）
            if _USAGE_LOGS_ENABLED and result.modified_count > 0:
                from src.infra.session.trace_storage import _write_usage_log

                asyncio.create_task(_write_usage_log(trace_id))
            if result.modified_count > 0 and self._merger is not None:
                self._merger.schedule_merge_once()
            if result.modified_count > 0:
                from src.infra.session.conversation_history import (
                    schedule_conversation_trace_index,
                )

                schedule_conversation_trace_index(self, trace_id)
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to complete trace {trace_id}: {e}")
            return False

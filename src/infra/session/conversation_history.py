"""Authorized indexing and retrieval of final historical conversation turns."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.session.conversation_history_index import (
    CONVERSATION_SEARCH_INDEX_VERSION,
    build_conversation_search_payload,
    extract_conversation_turn,
    merge_source_refs,
)
from src.infra.session.search_index import build_search_query_terms
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.conversation_history import ConversationSourceRef
from src.kernel.schemas.session import Session

CURSOR_VERSION = 1
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 20
SEARCH_QUERY_MAX_CHARS = 500
CANDIDATE_SCAN_MAX = 500
SESSION_LOOKUP_BATCH_SIZE = 100
BACKFILL_BATCH_MAX = 100
BACKFILL_SKIP_RECENT_SECONDS = 120

logger = get_logger(__name__)
_conversation_index_tasks: set[asyncio.Task[bool]] = set()


class ConversationHistoryError(Exception):
    """Base class for stable conversation-history tool error categories."""


class ConversationHistoryInvalidArgumentError(ConversationHistoryError):
    """Raised for malformed search or pagination input."""


class ConversationHistoryNotFoundError(ConversationHistoryError):
    """Raised for missing and unauthorized resources alike."""


def _conversation_index_task_done(task: asyncio.Task[bool]) -> None:
    _conversation_index_tasks.discard(task)
    if task.cancelled():
        return
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is not None:
        logger.warning(
            "Conversation trace indexing failed: error_type=%s",
            type(error).__name__,
        )


def schedule_conversation_trace_index(trace_storage: Any, trace_id: str) -> None:
    """Schedule best-effort trace indexing without delaying terminal delivery."""
    if not trace_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    service = ConversationHistoryService(trace_storage=trace_storage)
    task = loop.create_task(service.index_trace(trace_id))
    _conversation_index_tasks.add(task)
    task.add_done_callback(_conversation_index_task_done)


def _bounded_limit(value: int | None) -> int:
    try:
        return min(max(int(value if value is not None else DEFAULT_PAGE_LIMIT), 1), MAX_PAGE_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ConversationHistoryInvalidArgumentError("invalid_limit") from exc


def _encode_cursor(
    kind: Literal["search", "detail"],
    timestamp: datetime,
    trace_id: str,
) -> str:
    payload = json.dumps(
        {
            "v": CURSOR_VERSION,
            "kind": kind,
            "timestamp": timestamp.isoformat(),
            "trace_id": trace_id,
        },
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(
    cursor: str | None,
    kind: Literal["search", "detail"],
) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, str) or not cursor or len(cursor) > 1000:
        raise ConversationHistoryInvalidArgumentError("invalid_cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        timestamp = datetime.fromisoformat(payload["timestamp"])
        trace_id = payload["trace_id"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error) as exc:
        raise ConversationHistoryInvalidArgumentError("invalid_cursor") from exc
    if (
        payload.get("v") != CURSOR_VERSION
        or payload.get("kind") != kind
        or timestamp.tzinfo is None
        or not isinstance(trace_id, str)
        or not trace_id
    ):
        raise ConversationHistoryInvalidArgumentError("invalid_cursor")
    return timestamp, trace_id


def _cursor_clause(timestamp: datetime, trace_id: str, *, field: str) -> dict[str, Any]:
    return {
        "$or": [
            {field: {"$lt": timestamp}},
            {field: timestamp, "trace_id": {"$lt": trace_id}},
        ]
    }


def _is_visible_session(session: Session | None, user_id: str) -> bool:
    if session is None or session.user_id != user_id:
        return False
    metadata = session.metadata or {}
    return (
        metadata.get("hidden_from_conversation_list") is not True
        and metadata.get("scheduled_task_id") is None
    )


class ConversationHistoryService:
    """Search and hydrate persisted final Q&A under strict user ownership."""

    def __init__(self, *, trace_storage: Any | None = None, session_manager: Any | None = None):
        if trace_storage is None:
            from src.infra.session.trace_storage import get_trace_storage

            trace_storage = get_trace_storage()
        if session_manager is None:
            from src.infra.session.manager import SessionManager

            session_manager = SessionManager()
        self.trace_storage = trace_storage
        self.session_manager = session_manager

    @property
    def collection(self):
        return self.trace_storage.collection

    async def index_trace(self, trace_id: str) -> bool:
        """Materialize one completed trace's searchable final turn."""
        if not trace_id:
            return False
        await self.trace_storage.ensure_indexes_if_needed()
        trace = await self.collection.find_one(
            {"trace_id": trace_id},
            {
                "_id": 0,
                "trace_id": 1,
                "session_id": 1,
                "user_id": 1,
                "status": 1,
            },
        )
        if not trace or trace.get("status") == "running" or not trace.get("session_id"):
            return False
        session = await self.session_manager.get_session(str(trace["session_id"]))
        if session is None or not session.user_id:
            return False
        events = await self.trace_storage.read_trace_events_compat(trace_id)
        payload = await run_blocking_io(build_conversation_search_payload, events)
        if not payload.user_text and not payload.assistant_final_text:
            return False
        indexed_at = utc_now()
        result = await self.collection.update_one(
            {"trace_id": trace_id, "status": {"$ne": "running"}},
            {
                "$set": {
                    "user_id": session.user_id,
                    "conversation_search.version": payload.version,
                    "conversation_search.user_text": payload.user_text,
                    "conversation_search.assistant_final_text": payload.assistant_final_text,
                    "conversation_search.user_terms": payload.user_terms,
                    "conversation_search.assistant_terms": payload.assistant_terms,
                    "conversation_search.terms": payload.terms,
                    "conversation_search.indexed_at": indexed_at,
                }
            },
        )
        return result.modified_count > 0

    async def _get_sessions(self, session_ids: list[str]) -> dict[str, Session]:
        resolved: dict[str, Session] = {}
        unique_ids = list(dict.fromkeys(session_ids))
        for index in range(0, len(unique_ids), SESSION_LOOKUP_BATCH_SIZE):
            batch = unique_ids[index : index + SESSION_LOOKUP_BATCH_SIZE]
            resolved.update(await self.session_manager.get_sessions(batch))
        return resolved

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, object]:
        """Search indexed turns and return authorized run references."""
        if not isinstance(query, str) or not query.strip() or len(query) > SEARCH_QUERY_MAX_CHARS:
            raise ConversationHistoryInvalidArgumentError("invalid_query")
        bounded_limit = _bounded_limit(limit)
        query_terms = build_search_query_terms(query)
        if not query_terms:
            raise ConversationHistoryInvalidArgumentError("invalid_query")
        decoded = _decode_cursor(cursor, "search")
        match: dict[str, Any] = {
            "user_id": user_id,
            "status": {"$ne": "running"},
            "conversation_search.version": CONVERSATION_SEARCH_INDEX_VERSION,
            "conversation_search.terms": {"$all": query_terms},
        }
        if decoded is not None:
            match.update(_cursor_clause(*decoded, field="completed_at"))

        docs = await (
            self.collection.find(match, {"_id": 0, "events": 0})
            .sort([("completed_at", -1), ("trace_id", -1)])
            .limit(CANDIDATE_SCAN_MAX + 1)
            .to_list(length=CANDIDATE_SCAN_MAX + 1)
        )
        sessions = await self._get_sessions(
            [str(doc.get("session_id")) for doc in docs if doc.get("session_id")]
        )
        items: list[dict[str, Any]] = []
        last_doc: dict[str, Any] | None = None
        more_candidates = False
        for index, doc in enumerate(docs):
            session_id = str(doc.get("session_id") or "")
            session = sessions.get(session_id)
            if not _is_visible_session(session, user_id):
                continue
            search_data = doc.get("conversation_search") or {}
            user_terms = set(search_data.get("user_terms") or [])
            assistant_terms = set(search_data.get("assistant_terms") or [])
            matches_user = all(term in user_terms for term in query_terms)
            matches_assistant = all(term in assistant_terms for term in query_terms)
            match_source = (
                "both"
                if matches_user and matches_assistant
                else "assistant"
                if matches_assistant
                else "user"
            )
            items.append(
                {
                    "session_id": session_id,
                    "run_id": doc.get("run_id"),
                    "session_name": session.name,
                    "completed_at": doc.get("completed_at"),
                    "user_message_preview": search_data.get("user_text", ""),
                    "assistant_final_preview": search_data.get("assistant_final_text", ""),
                    "match_source": match_source,
                }
            )
            last_doc = doc
            if len(items) >= bounded_limit:
                more_candidates = index < len(docs) - 1
                break

        next_cursor = None
        if (
            more_candidates
            and last_doc
            and last_doc.get("completed_at")
            and last_doc.get("trace_id")
        ):
            next_cursor = _encode_cursor(
                "search",
                last_doc["completed_at"],
                str(last_doc["trace_id"]),
            )
        return {"success": True, "items": items, "next_cursor": next_cursor}

    async def get_detail(
        self,
        user_id: str,
        session_id: str,
        run_id: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, object]:
        """Read one run or a paginated session as final Q&A turns."""
        session = await self.session_manager.get_session(session_id)
        if not _is_visible_session(session, user_id):
            raise ConversationHistoryNotFoundError("not_found")

        bounded_limit = _bounded_limit(limit)
        if run_id:
            trace = await self.collection.find_one(
                {
                    "session_id": session_id,
                    "run_id": run_id,
                    "status": {"$ne": "running"},
                },
                {"_id": 0, "events": 0},
            )
            if trace is None:
                raise ConversationHistoryNotFoundError("not_found")
            selected = [trace]
            has_more = False
        else:
            decoded = _decode_cursor(cursor, "detail")
            match: dict[str, Any] = {
                "session_id": session_id,
                "status": {"$ne": "running"},
            }
            if decoded is not None:
                match.update(_cursor_clause(*decoded, field="started_at"))
            docs = await (
                self.collection.find(match, {"_id": 0, "events": 0})
                .sort([("started_at", -1), ("trace_id", -1)])
                .limit(bounded_limit + 1)
                .to_list(length=bounded_limit + 1)
            )
            has_more = len(docs) > bounded_limit
            selected = docs[:bounded_limit]

        events_by_trace = await self.trace_storage.read_trace_events_batch_compat(selected)
        turns: list[dict[str, Any]] = []
        for trace in reversed(selected):
            events = events_by_trace.get(str(trace.get("trace_id")), [])
            turn = await run_blocking_io(extract_conversation_turn, events)
            turns.append(
                {
                    "run_id": trace.get("run_id"),
                    "started_at": trace.get("started_at"),
                    "completed_at": trace.get("completed_at"),
                    "user_message": turn.user_text,
                    "assistant_final": turn.assistant_final_text,
                }
            )

        next_cursor = None
        if has_more and selected:
            last_doc = selected[-1]
            if last_doc.get("started_at") and last_doc.get("trace_id"):
                next_cursor = _encode_cursor(
                    "detail",
                    last_doc["started_at"],
                    str(last_doc["trace_id"]),
                )
        return {
            "success": True,
            "session": {"session_id": session.id, "name": session.name},
            "turns": turns,
            "next_cursor": next_cursor,
        }

    async def validate_source_refs(
        self,
        user_id: str,
        refs: Sequence[ConversationSourceRef | dict[str, str]],
    ) -> list[ConversationSourceRef]:
        """Return only references owned by the user and safe for history access."""
        normalized: list[ConversationSourceRef] = []
        for raw_ref in refs:
            try:
                ref = (
                    raw_ref
                    if isinstance(raw_ref, ConversationSourceRef)
                    else ConversationSourceRef.model_validate(raw_ref)
                )
            except Exception:
                continue
            normalized.append(ref)
        normalized = merge_source_refs([], normalized)
        sessions = await self._get_sessions([ref.session_id for ref in normalized])
        candidates = [
            ref for ref in normalized if _is_visible_session(sessions.get(ref.session_id), user_id)
        ]
        if not candidates:
            return []
        pair_query = [
            {
                "session_id": ref.session_id,
                "run_id": ref.run_id,
                "status": {"$ne": "running"},
            }
            for ref in candidates
        ]
        docs = await self.collection.find(
            {"$or": pair_query},
            {"_id": 0, "session_id": 1, "run_id": 1},
        ).to_list(length=len(pair_query))
        valid_pairs = {(str(doc.get("session_id")), str(doc.get("run_id"))) for doc in docs}
        return [ref for ref in candidates if (ref.session_id, ref.run_id) in valid_pairs]

    async def backfill_indexes(self, batch_size: int = 20) -> int:
        """Index one bounded batch of old completed traces."""
        await self.trace_storage.ensure_indexes_if_needed()
        bounded_batch = min(max(int(batch_size), 1), BACKFILL_BATCH_MAX)
        cutoff = utc_now() - timedelta(seconds=BACKFILL_SKIP_RECENT_SECONDS)
        query = {
            "status": {"$ne": "running"},
            "conversation_search.version": {"$ne": CONVERSATION_SEARCH_INDEX_VERSION},
            "updated_at": {"$lt": cutoff},
        }
        docs = await (
            self.collection.find(query, {"_id": 0, "trace_id": 1})
            .sort("updated_at", 1)
            .limit(bounded_batch)
            .to_list(length=bounded_batch)
        )
        rebuilt = 0
        for doc in docs:
            trace_id = str(doc.get("trace_id") or "")
            if trace_id and await self.index_trace(trace_id):
                rebuilt += 1
        return rebuilt

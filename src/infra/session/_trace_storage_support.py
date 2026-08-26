"""Shared limits and normalization helpers for trace storage."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.infra.utils.datetime import ensure_utc, parse_iso
from src.kernel.config import settings

SESSION_EVENT_FILTER_LIST_LIMIT = 100
TRACE_EVENTS_DEFAULT_LIMIT = 1000
TRACE_EVENTS_READ_LIMIT = 5000
TRACE_LIST_LIMIT = 100
_RECOMMEND_QUESTIONS_LIMIT = 3


def _get_session_event_read_default_limit() -> int:
    configured = max(int(getattr(settings, "SESSION_EVENT_READ_DEFAULT_LIMIT", 1000) or 0), 1)
    return min(configured, TRACE_EVENTS_READ_LIMIT)


def _clamp_positive_int(value: int | None, *, default: int, maximum: int) -> int:
    try:
        candidate = int(value if value is not None else default)
    except (TypeError, ValueError):
        candidate = default
    return min(max(candidate, 1), maximum)


def _clamp_event_read_limit(value: int | None, *, default: int) -> int:
    try:
        candidate = int(value if value is not None else default)
    except (TypeError, ValueError):
        candidate = default
    if candidate <= 0:
        return 0
    return min(candidate, TRACE_EVENTS_READ_LIMIT)


def _clamp_nonnegative_int(value: int | None) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _get_event_chunk_size() -> int:
    try:
        return max(int(getattr(settings, "SESSION_EVENT_CHUNK_SIZE", 5000) or 0), 1)
    except (TypeError, ValueError):
        return 5000


def _event_chunk_index(seq: int) -> int:
    return (max(int(seq), 1) - 1) // _get_event_chunk_size()


def _event_preview(event: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not event:
        return None
    preview = {
        "event_type": event.get("event_type"),
        "data": event.get("data", {}),
        "timestamp": event.get("timestamp"),
    }
    if "seq" in event:
        preview["seq"] = event.get("seq")
    return preview


def _event_seq(event: Dict[str, Any], fallback: int) -> int:
    try:
        return int(event.get("seq", fallback))
    except (TypeError, ValueError):
        return fallback


def _bounded_unique_strings(
    values: Optional[List[str]],
    limit: int = SESSION_EVENT_FILTER_LIST_LIMIT,
) -> List[str]:
    if not values:
        return []
    bounded: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        bounded.append(value)
        if len(bounded) >= limit:
            break
    return bounded


def _normalize_recommend_questions(value: Any) -> List[str]:
    """Normalize current and defensive legacy run-field shapes."""
    if isinstance(value, dict):
        value = value.get("questions")
    if not isinstance(value, (list, tuple)):
        return []

    questions: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        question = item.strip()
        if not question:
            continue
        questions.append(question)
        if len(questions) >= _RECOMMEND_QUESTIONS_LIMIT:
            break
    return questions


def build_trace_window_find_query(
    match_query: Dict[str, Any],
    before_trace_started_at: "datetime",
    before_trace_id: Optional[str],
) -> Dict[str, Any]:
    """游标边界：(started_at, trace_id) 严格元组比较，只保留更早的 traces。"""
    boundary: Dict[str, Any] = {"started_at": {"$lt": before_trace_started_at}}
    if before_trace_id:
        boundary = {
            "$or": [
                boundary,
                {
                    "started_at": before_trace_started_at,
                    "trace_id": {"$lt": before_trace_id},
                },
            ]
        }
    return {"$and": [match_query, boundary]} if match_query else boundary


def apply_trace_window_to_traces(
    traces: List[Dict[str, Any]],
    trace_limit: Optional[int],
    window_active: bool,
) -> tuple[
    List[Dict[str, Any]],
    bool,
    Optional["datetime"],
    Optional[str],
]:
    """裁掉窗口探测项并反转为时间升序，返回 (traces, has_more, 游标)。

    窗口模式按 (started_at, trace_id) 倒序取回且多取一条探测 has_more；
    游标取窗口内最旧一条 trace，供下一页继续向前翻。
    """
    has_more_traces = False
    if trace_limit is not None:
        has_more_traces = len(traces) > trace_limit
        if has_more_traces:
            traces = traces[:trace_limit]
        traces.reverse()
    oldest_trace_started_at: Optional[datetime] = None
    oldest_trace_id: Optional[str] = None
    if window_active and traces:
        oldest_trace_started_at = coerce_trace_started_at(traces[0].get("started_at"))
        oldest_trace_id = traces[0].get("trace_id")
    return traces, has_more_traces, oldest_trace_started_at, oldest_trace_id


def coerce_trace_started_at(value: Any) -> Optional["datetime"]:
    """把 trace 的 started_at 规整为带时区的 datetime（兼容字符串存量）。"""
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        try:
            return parse_iso(value)
        except (TypeError, ValueError):
            return None
    return None

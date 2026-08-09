"""Shared limits and normalization helpers for trace storage."""

from typing import Any, Dict, List, Optional

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

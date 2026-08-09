"""Pure helpers for materializing searchable final conversation turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.infra.session.search_index import (
    MAX_SESSION_SEARCH_TERMS,
    build_search_terms,
    normalize_search_text,
)
from src.kernel.schemas.conversation_history import ConversationSourceRef

CONVERSATION_SEARCH_INDEX_VERSION = 1
CONVERSATION_SEARCH_TEXT_MAX_CHARS = 24_000
MEMORY_SOURCE_REFS_MAX = 20


@dataclass(frozen=True)
class ConversationTurnText:
    user_text: str
    assistant_final_text: str


@dataclass(frozen=True)
class ConversationSearchPayload:
    version: int
    user_text: str
    assistant_final_text: str
    user_terms: list[str]
    assistant_terms: list[str]
    terms: list[str]


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _event_depth(data: dict[str, Any]) -> int:
    try:
        return int(data.get("depth") or 0)
    except (TypeError, ValueError):
        return 0


def extract_conversation_turn(events: list[dict[str, Any]]) -> ConversationTurnText:
    """Extract user text and the main Agent's final streamed answer."""
    user_parts: list[str] = []
    assistant_parts: list[str] = []
    for event in events:
        data = _event_data(event)
        event_type = event.get("event_type")
        if event_type == "user:message":
            content = data.get("content") or data.get("message")
            if isinstance(content, str) and content:
                user_parts.append(content)
            continue
        if event_type != "message:chunk" or _event_depth(data) > 0:
            continue
        content = data.get("content")
        if isinstance(content, str) and content:
            assistant_parts.append(content)

    return ConversationTurnText(
        user_text=normalize_search_text("\n".join(user_parts)),
        assistant_final_text=normalize_search_text("".join(assistant_parts)),
    )


def _dedupe_terms(*groups: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for term in group:
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= MAX_SESSION_SEARCH_TERMS:
                return terms
    return terms


def build_conversation_search_payload(
    events: list[dict[str, Any]],
) -> ConversationSearchPayload:
    """Build a bounded trace-side projection for keyword history search."""
    turn = extract_conversation_turn(events)
    user_terms = build_search_terms(turn.user_text)
    assistant_terms = build_search_terms(turn.assistant_final_text)
    return ConversationSearchPayload(
        version=CONVERSATION_SEARCH_INDEX_VERSION,
        user_text=turn.user_text[:CONVERSATION_SEARCH_TEXT_MAX_CHARS],
        assistant_final_text=turn.assistant_final_text[:CONVERSATION_SEARCH_TEXT_MAX_CHARS],
        user_terms=user_terms,
        assistant_terms=assistant_terms,
        terms=_dedupe_terms(user_terms, assistant_terms),
    )


def _coerce_source_ref(value: ConversationSourceRef | dict[str, str]) -> ConversationSourceRef:
    if isinstance(value, ConversationSourceRef):
        return value
    return ConversationSourceRef.model_validate(value)


def merge_source_refs(
    existing: list[ConversationSourceRef | dict[str, str]] | None,
    incoming: list[ConversationSourceRef | dict[str, str]] | None,
    *,
    limit: int = MEMORY_SOURCE_REFS_MAX,
) -> list[ConversationSourceRef]:
    """Merge references by recency, moving repeated references to the newest end."""
    bounded_limit = max(int(limit), 0)
    if bounded_limit == 0:
        return []

    ordered: dict[tuple[str, str], ConversationSourceRef] = {}
    for raw_ref in [*(existing or []), *(incoming or [])]:
        ref = _coerce_source_ref(raw_ref)
        key = (ref.session_id, ref.run_id)
        ordered.pop(key, None)
        ordered[key] = ref
    return list(ordered.values())[-bounded_limit:]

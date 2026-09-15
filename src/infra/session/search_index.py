"""Helpers for session search indexing and match previews."""

from __future__ import annotations

import re
from dataclasses import dataclass

SESSION_SEARCH_INDEX_VERSION = 3
MAX_SESSION_SEARCH_TERMS = 4096
MAX_SESSION_SEARCH_TEXT_CHARS = 24000
MAX_PREVIEW_CHARS = 160

# 会话文档上的搜索索引/写入器字段：只被搜索与回填路径消费，可达数十
# KB/会话；列表读取（侧边栏）一律投影掉，Session 模型也不声明它们
SESSION_LIST_EXCLUDED_FIELDS = frozenset(
    {
        "search_text",
        "search_terms",
        "name_search_terms",
        "message_search_terms",
        "latest_user_message",
        "search_index_version",
        "search_index_updated_at",
        "active_trace_writers",
    }
)


def session_list_projection(*, keep_search_text: bool = False) -> dict[str, int]:
    """Mongo 投影：列表读取排除搜索索引重字段。

    keep_search_text=True 供搜索路径生成命中预览（search_text 不排除）。
    """
    projection = {field: 0 for field in SESSION_LIST_EXCLUDED_FIELDS}
    if keep_search_text:
        projection.pop("search_text", None)
    return projection


_WORD_OR_CJK_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SessionSearchIndexPayload:
    name_search_terms: list[str]
    message_search_terms: list[str]
    search_terms: list[str]
    search_text: str
    latest_user_message: str
    search_index_version: int = SESSION_SEARCH_INDEX_VERSION


def normalize_search_text(text: str | None) -> str:
    """Collapse whitespace while keeping user-visible wording intact."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def build_search_terms(text: str | None) -> list[str]:
    """Build compact search terms that work for latin substrings and CJK phrases."""
    normalized = normalize_search_text(text)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        clean = term.strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(clean)

    for match in _WORD_OR_CJK_RE.finditer(normalized):
        token = match.group(0)
        if token.isascii():
            lowered = token.lower()
            add(lowered)
            if len(lowered) >= 4:
                for index in range(len(lowered) - 2):
                    add(lowered[index : index + 3])
        else:
            add(token)
            if len(token) == 1:
                continue
            for char in token:
                add(char)
            for index in range(len(token) - 1):
                add(token[index : index + 2])

    return terms[:MAX_SESSION_SEARCH_TERMS]


def build_search_query_terms(text: str | None) -> list[str]:
    """Build query terms optimized for substring-style matching."""
    normalized = normalize_search_text(text)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        clean = term.strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(clean)

    for match in _WORD_OR_CJK_RE.finditer(normalized):
        token = match.group(0)
        if token.isascii():
            lowered = token.lower()
            if len(lowered) < 4:
                add(lowered)
                continue
            for index in range(len(lowered) - 2):
                add(lowered[index : index + 3])
            continue

        if len(token) == 1:
            add(token)
            continue
        for char in token:
            add(char)
        for index in range(len(token) - 1):
            add(token[index : index + 2])

    return terms[:MAX_SESSION_SEARCH_TERMS]


def build_search_preview(search_text: str | None, query: str | None) -> str | None:
    """Extract a short preview snippet for the current search query."""
    normalized_query = normalize_search_text(query)
    if search_text:
        for raw_line in search_text.splitlines():
            normalized_line = normalize_search_text(raw_line)
            if not normalized_line:
                continue
            if _find_match_start(normalized_line, normalized_query) != -1:
                return normalized_line[:MAX_PREVIEW_CHARS]

    normalized_text = normalize_search_text(search_text)
    if not normalized_text:
        return None
    if not normalized_query:
        return normalized_text[:MAX_PREVIEW_CHARS]

    start = _find_match_start(normalized_text, normalized_query)
    if start == -1:
        return None

    query_match = _find_match_token(normalized_text, normalized_query) or normalized_query
    end = start + len(query_match)
    window_start = max(0, start - 32)
    window_end = min(len(normalized_text), end + 96)
    snippet = normalized_text[window_start:window_end].strip()
    if window_start > 0:
        snippet = f"...{snippet}"
    if window_end < len(normalized_text):
        snippet = f"{snippet}..."
    return snippet[:MAX_PREVIEW_CHARS]


def compose_session_search_index(
    *,
    session_name: str | None,
    message_search_terms: list[str] | None,
    search_text: str | None,
    latest_user_message: str | None,
) -> SessionSearchIndexPayload:
    """Compose the persisted session-side search document."""
    name_terms = build_search_terms(session_name)
    message_terms = _truncate_terms(message_search_terms or [])
    combined_terms = _truncate_terms([*name_terms, *message_terms])
    normalized_latest = normalize_search_text(latest_user_message)

    return SessionSearchIndexPayload(
        name_search_terms=name_terms,
        message_search_terms=message_terms,
        search_terms=combined_terms,
        search_text=_append_search_text(search_text, normalized_latest),
        latest_user_message=normalized_latest,
    )


def append_message_to_search_index(
    *,
    session_name: str | None,
    existing_message_search_terms: list[str] | None,
    existing_search_text: str | None,
    latest_user_message: str | None,
) -> SessionSearchIndexPayload:
    """Update session-side search data with one more user message."""
    normalized_latest = normalize_search_text(latest_user_message)
    added_terms = build_search_terms(normalized_latest)
    merged_terms = _truncate_terms([*(existing_message_search_terms or []), *added_terms])
    return compose_session_search_index(
        session_name=session_name,
        message_search_terms=merged_terms,
        search_text=existing_search_text,
        latest_user_message=normalized_latest,
    )


def build_backfilled_search_index(
    *,
    session_name: str | None,
    user_messages: list[str],
) -> SessionSearchIndexPayload:
    """Build a full search index for an existing session from stored user messages."""
    normalized_messages = [
        normalized for message in user_messages if (normalized := normalize_search_text(message))
    ]
    message_terms: list[str] = []
    for message in normalized_messages:
        message_terms.extend(build_search_terms(message))

    return compose_session_search_index(
        session_name=session_name,
        message_search_terms=message_terms,
        search_text="\n".join(normalized_messages[:-1]),
        latest_user_message=normalized_messages[-1] if normalized_messages else "",
    )


def merge_search_state(
    *,
    session_name: str | None,
    base_message_terms: list[str] | None,
    base_search_text: str | None,
    base_latest_user_message: str | None,
    extra_message_terms: list[str] | None,
    extra_search_text: str | None,
    extra_latest_user_message: str | None,
) -> SessionSearchIndexPayload:
    """Merge two session search states without dropping newer live content."""
    merged_terms = _truncate_terms([*(base_message_terms or []), *(extra_message_terms or [])])

    base_history_lines = _normalize_search_lines(
        _normalize_search_text_without_latest(base_search_text, base_latest_user_message)
    )
    extra_history_lines = _normalize_search_lines(
        _normalize_search_text_without_latest(extra_search_text, extra_latest_user_message)
    )
    base_latest = normalize_search_text(base_latest_user_message)
    extra_latest = normalize_search_text(extra_latest_user_message)
    latest = extra_latest or base_latest

    history_lines = _merge_search_lines(base_history_lines, extra_history_lines)
    if (
        base_latest
        and base_latest != latest
        and (not history_lines or history_lines[-1] != base_latest)
    ):
        history_lines.append(base_latest)
    merged_text = _join_search_lines(history_lines)

    return compose_session_search_index(
        session_name=session_name,
        message_search_terms=merged_terms,
        search_text=merged_text,
        latest_user_message=latest,
    )


def _truncate_terms(terms: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean = term.strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
        if len(deduped) >= MAX_SESSION_SEARCH_TERMS:
            break
    return deduped


def _append_search_text(existing: str | None, latest: str) -> str:
    lines = _normalize_search_lines(existing)
    if latest:
        lines.append(latest)
    return _join_search_lines(lines)


def _normalize_search_text_without_latest(search_text: str | None, latest: str | None) -> str:
    lines = _normalize_search_lines(search_text)
    normalized_latest = normalize_search_text(latest)
    if not lines or not normalized_latest:
        return _join_search_lines(lines)
    if lines[-1] == normalized_latest:
        lines = lines[:-1]
    return _join_search_lines(lines)


def _normalize_search_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [
        normalized
        for raw_line in text.splitlines()
        if (normalized := normalize_search_text(raw_line))
    ]


def _merge_search_lines(base_lines: list[str], extra_lines: list[str]) -> list[str]:
    if not base_lines:
        return list(extra_lines)
    if not extra_lines:
        return list(base_lines)

    max_overlap = min(len(base_lines), len(extra_lines))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if base_lines[-size:] == extra_lines[:size]:
            overlap = size
            break
    return [*base_lines, *extra_lines[overlap:]]


def _join_search_lines(lines: list[str]) -> str:
    if not lines:
        return ""

    kept: list[str] = []
    total_chars = 0
    for line in reversed(lines):
        line_len = len(line)
        separator_len = 1 if kept else 0
        if total_chars + separator_len + line_len > MAX_SESSION_SEARCH_TEXT_CHARS:
            if kept:
                break
            return line[-MAX_SESSION_SEARCH_TEXT_CHARS:]
        kept.append(line)
        total_chars += separator_len + line_len
    return "\n".join(reversed(kept))


def _find_match_start(text: str, query: str) -> int:
    match = _find_match_token(text, query)
    if not match:
        return -1
    return text.lower().find(match.lower())


def _find_match_token(text: str, query: str) -> str | None:
    text_lower = text.lower()
    query_lower = query.lower()
    if query_lower and query_lower in text_lower:
        return query

    segments = [segment.group(0) for segment in _WORD_OR_CJK_RE.finditer(query)]
    segments.sort(key=len, reverse=True)
    for segment in segments:
        if segment.lower() in text_lower:
            return segment
    return None

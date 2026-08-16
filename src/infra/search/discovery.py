"""Deterministic lexical discovery with Chinese pinyin aliases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from pypinyin import Style, lazy_pinyin

_SEPARATORS = re.compile(r"[_:\-\s]+")
_TYPO_MIN_LENGTH = 4
_TYPO_MIN_RATIO = 0.82


def _normalize(value: str) -> str:
    return _SEPARATORS.sub(" ", value).strip().lower()


def _compact(value: str) -> str:
    return _normalize(value).replace(" ", "")


def _pinyin_aliases(value: str) -> tuple[str, str]:
    """Return contiguous full pinyin and initials for searchable text."""
    if not value:
        return "", ""
    syllables = lazy_pinyin(value, style=Style.NORMAL, errors="default")
    initials = lazy_pinyin(value, style=Style.FIRST_LETTER, errors="default")
    return _compact("".join(syllables)), _compact("".join(initials))


def _safe_pinyin_aliases(value: str) -> tuple[str, str]:
    try:
        return _pinyin_aliases(value)
    except Exception:
        return "", ""


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    """One name and its metadata in a discovery registry."""

    name: str
    text: str = ""
    tags: tuple[str, ...] = ()
    payload: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class DiscoveryMatch:
    """A ranked discovery result."""

    record: DiscoveryRecord
    score: float

    @property
    def name(self) -> str:
        return self.record.name

    @property
    def payload(self) -> Any:
        return self.record.payload


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    record: DiscoveryRecord
    name: str
    compact_name: str
    name_tokens: tuple[str, ...]
    text: str
    text_tokens: tuple[str, ...]
    full_pinyin: tuple[str, ...]
    initials: tuple[str, ...]

    @property
    def required_aliases(self) -> tuple[str, ...]:
        return (
            self.name,
            self.compact_name,
            self.text,
            *self.name_tokens,
            *self.text_tokens,
            *self.full_pinyin,
            *self.initials,
        )


def _parse_record(record: DiscoveryRecord) -> _ParsedRecord:
    normalized_name = _normalize(record.name)
    metadata = " ".join((record.text, *record.tags)).strip()
    normalized_text = _normalize(metadata)
    name_pinyin, name_initials = _safe_pinyin_aliases(record.name)
    text_pinyin, text_initials = _safe_pinyin_aliases(metadata)
    return _ParsedRecord(
        record=record,
        name=normalized_name,
        compact_name=normalized_name.replace(" ", ""),
        name_tokens=tuple(normalized_name.split()),
        text=normalized_text,
        text_tokens=tuple(normalized_text.split()),
        full_pinyin=tuple(value for value in (name_pinyin, text_pinyin) if value),
        initials=tuple(value for value in (name_initials, text_initials) if value),
    )


def _term_matches_required(term: str, parsed: _ParsedRecord) -> bool:
    compact_term = _compact(term)
    return bool(compact_term) and any(compact_term in alias for alias in parsed.required_aliases)


def _typo_score(term: str, aliases: tuple[str, ...]) -> float:
    if len(term) < _TYPO_MIN_LENGTH:
        return 0.0
    best = 0.0
    for alias in aliases:
        if len(alias) < _TYPO_MIN_LENGTH:
            continue
        ratio = SequenceMatcher(None, term, alias).ratio()
        if ratio >= _TYPO_MIN_RATIO:
            best = max(best, 20.0 + ratio * 10.0)
    return best


def _score_term(term: str, parsed: _ParsedRecord) -> float:
    normalized = _normalize(term)
    compact = normalized.replace(" ", "")
    if not compact:
        return 0.0
    if normalized == parsed.name or compact == parsed.compact_name:
        return 100.0
    if normalized in parsed.name_tokens:
        return 80.0
    if any(token.startswith(normalized) for token in parsed.name_tokens):
        return 70.0
    if compact in parsed.compact_name:
        return 60.0
    if any(compact == alias for alias in parsed.full_pinyin):
        return 55.0
    if any(compact in alias for alias in parsed.full_pinyin):
        return 50.0
    if any(compact == alias for alias in parsed.initials):
        return 48.0
    if any(compact in alias for alias in parsed.initials):
        return 45.0
    if normalized in parsed.text_tokens:
        return 35.0
    if compact in parsed.text.replace(" ", ""):
        return 30.0
    return _typo_score(compact, (parsed.compact_name, *parsed.full_pinyin))


def _select_exact(
    query: str, records: list[DiscoveryRecord], max_results: int
) -> list[DiscoveryMatch]:
    requested = {
        name.strip().lower() for name in query[len("select:") :].split(",") if name.strip()
    }
    matches = [
        DiscoveryMatch(record=record, score=1000.0)
        for record in records
        if record.name.lower() in requested
    ]
    return sorted(matches, key=lambda match: match.name.lower())[:max_results]


def search_records(
    query: str,
    records: list[DiscoveryRecord],
    *,
    max_results: int = 10,
) -> list[DiscoveryMatch]:
    """Search records by exact, normalized, pinyin, and conservative typo aliases."""
    stripped = query.strip()
    if not stripped or not records or max_results <= 0:
        return []
    if stripped.lower().startswith("select:"):
        return _select_exact(stripped, records, max_results)

    raw_terms = stripped.split()
    required = [term[1:] for term in raw_terms if term.startswith("+") and len(term) > 1]
    terms = [term[1:] if term.startswith("+") else term for term in raw_terms]
    parsed_records = [_parse_record(record) for record in records]
    ranked: list[DiscoveryMatch] = []
    for parsed in parsed_records:
        if any(not _term_matches_required(term, parsed) for term in required):
            continue
        scores = [_score_term(term, parsed) for term in terms]
        positive_scores = [s for s in scores if s > 0]
        if not positive_scores:
            continue
        ranked.append(DiscoveryMatch(record=parsed.record, score=sum(positive_scores)))

    ranked.sort(key=lambda match: (-match.score, match.name.lower(), match.name))
    return ranked[:max_results]

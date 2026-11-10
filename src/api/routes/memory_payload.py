"""Shared memory response fields and bounded text normalization."""

from typing import Any


def _clean_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for tag in value:
        text = str(tag).strip()
        if text:
            tags.append(text[:40])
        if len(tags) >= 20:
            break
    return tags


def _clean_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if max_length is not None:
        return text[:max_length]
    return text


def _memory_projection() -> dict[str, int]:
    return {
        "memory_id": 1,
        "user_id": 1,
        "title": 1,
        "summary": 1,
        "memory_type": 1,
        "tags": 1,
        "content": 1,
        "content_storage_mode": 1,
        "content_store_key": 1,
        "context": 1,
        "source": 1,
        "created_at": 1,
        "updated_at": 1,
        "accessed_at": 1,
        "access_count": 1,
        "source_refs": 1,
        "origin_session_ids": 1,
        "scope": 1,
        "project_id": 1,
    }

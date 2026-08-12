"""Lossless transport compaction for reconstructed chat history."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _compatible_message_chunks(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("event_type") != "message:chunk" or right.get("event_type") != "message:chunk":
        return False

    left_data = left.get("data")
    right_data = right.get("data")
    if not isinstance(left_data, dict) or not isinstance(right_data, dict):
        return False
    if not isinstance(left_data.get("content"), str) or not isinstance(
        right_data.get("content"), str
    ):
        return False

    left_identity = {
        key: value for key, value in left.items() if key not in {"data", "seq", "timestamp"}
    }
    right_identity = {
        key: value for key, value in right.items() if key not in {"data", "seq", "timestamp"}
    }
    if left_identity != right_identity:
        return False

    left_metadata = {key: value for key, value in left_data.items() if key != "content"}
    right_metadata = {key: value for key, value in right_data.items() if key != "content"}
    return left_metadata == right_metadata


def compact_consecutive_message_chunks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only adjacent semantically compatible assistant text chunks."""
    compacted: list[dict[str, Any]] = []
    for source_event in events:
        event = deepcopy(source_event)
        if compacted and _compatible_message_chunks(compacted[-1], event):
            previous = compacted[-1]
            merged = event
            merged["data"]["content"] = previous["data"]["content"] + event["data"]["content"]
            compacted[-1] = merged
        else:
            compacted.append(event)
    return compacted

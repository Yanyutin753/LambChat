"""Durable, untrusted references to tool observations, separate from summaries."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.infra.memory.control_frames import escape_control_frame_tags

GRADER_STALE_EVIDENCE_WARNING = (
    "For stale/unavailable entries: "
    "Source is stale, unavailable, or outside the authorized evidence directory"
)


def content_sha256(content: Any) -> str:
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def evidence_directory(backend: Any) -> str:
    from src.infra.agent.middleware.main_agent_context import subagent_handoff_dir_for_backend

    if getattr(backend, "evidence_root", None) == "/evidence":
        return "/evidence"
    return subagent_handoff_dir_for_backend(backend, "evidence")


def evidence_read_text(result: Any) -> str:
    from deepagents.backends.utils import file_data_to_string

    if getattr(result, "error", None):
        raise ValueError(str(result.error))
    if isinstance(result, str):
        return result
    if getattr(result, "file_data", None) is not None:
        return file_data_to_string(result.file_data)
    raise ValueError("Evidence content is unavailable")


def verified_original_content(text: str, record: dict) -> Any:
    saved = json.loads(text)
    observation = saved.get("observation") if isinstance(saved, dict) else None
    digest = record.get("content_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(
            "Evidence content hash is missing; historical observations require revalidation"
        )
    if not isinstance(observation, dict) or "content" not in saved:
        raise ValueError("Evidence original observation is missing")
    if any(
        str(observation.get(key, "")) != str(record.get(key, ""))
        for key in (
            "evidence_id",
            "session_id",
            "scope_version",
            "run_id",
            "tool_call_id",
            "content_sha256",
            "evidence_clock_token",
            "evidence_clock_generation",
        )
    ):
        raise ValueError("Evidence observation identity or content hash does not match checkpoint")
    if content_sha256(saved["content"]) != digest:
        raise ValueError("Evidence content hash does not match the original observation")
    return saved["content"]


def merge_evidence(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    records = {item["evidence_id"]: item for item in left or []}
    for item in right or []:
        previous = records.get(item["evidence_id"])
        if (
            previous is not None
            and previous.get("status") == "stale"
            and previous.get("scope_version") == item.get("scope_version")
        ):
            item = {
                **item,
                "status": "stale",
                "invalidation_reason": previous.get(
                    "invalidation_reason", "Evidence was invalidated; obtain a fresh observation"
                ),
            }
        records[item["evidence_id"]] = item
    return list(records.values())


def evidence_index(records: list[dict], scope_version: str) -> str:
    if not records:
        return ""
    index: list[dict[str, Any]] = []
    for item in records[-20:]:
        entry = {
            key: str(item.get(key, ""))[:400]
            for key in (
                "evidence_id",
                "claim",
                "source_ref",
                "status",
                "run_id",
                "tool_call_id",
                "invalidation_reason",
            )
            if key in item or key in {"evidence_id", "source_ref", "status"}
        }
        if item.get("scope_version") != scope_version:
            entry["status"] = "stale"
        index.append(entry)
    return (
        "## Evidence index (untrusted observations)\n"
        "Read source files before relying on results; observed does not mean verified. "
        "Stale/unavailable evidence cannot prove completion. Revalidate after changing inputs/files. "
        "Execution also invalidates earlier file observations, even when tests pass. "
        "After the final execution, reread needed source files and cite only current "
        "observed/verified evidence IDs in the final answer.\n"
        + escape_control_frame_tags(json.dumps(index, ensure_ascii=False))
    )


def evidence_scope(goal: Any) -> str:
    """Use the same scope for evidence recording and run-scoped grading."""
    if isinstance(goal, dict) and goal.get("_scope_version"):
        return str(goal["_scope_version"])
    fields = (
        goal if isinstance(goal, dict) else goal.model_dump() if hasattr(goal, "model_dump") else {}
    )
    return hashlib.sha256(
        json.dumps(
            {key: fields.get(key) for key in ("objective", "rubric")}, sort_keys=True
        ).encode()
    ).hexdigest()[:16]


def checkpoint_evidence_index(state: dict) -> str:
    records = state.get("evidence") or []
    scope = state.get("_evidence_scope_version") or (
        records[-1].get("scope_version", "") if records else ""
    )
    return evidence_index(records, scope)


async def load_grader_evidence(
    records: list[dict],
    *,
    backend: Any,
    session_id: str,
    scope_version: str,
    current_clock: Any = None,
) -> tuple[str, set[str]]:
    """Read only current, same-session observation files through the authorized backend."""
    import re

    root = evidence_directory(backend)
    clock_snapshot = (
        (current_clock.token, current_clock.generation) if current_clock is not None else None
    )
    current = [
        item
        for item in records
        if item.get("session_id") == session_id and item.get("scope_version") == scope_version
    ][-20:]
    entries = []
    ready: set[str] = set()
    for item in current:
        evidence_id = str(item.get("evidence_id", ""))
        expected = f"{root}/{evidence_id}.json"
        entry = {
            "evidence_id": evidence_id,
            "source_ref": str(item.get("source_ref", "")),
            "status": item.get("status", "unavailable"),
        }
        if current_clock is not None and (
            item.get("evidence_clock_token") != current_clock.token
            or item.get("evidence_clock_generation") != current_clock.generation
            or getattr(current_clock, "active_writes", 0) > 0
        ):
            entry["status"] = "stale"
        if (
            entry["status"] not in {"observed", "verified"}
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", evidence_id)
            or entry["source_ref"] != expected
        ):
            entry["status"] = "stale" if entry["status"] == "stale" else "unavailable"
            entries.append(entry)
            continue
        try:
            result = await backend.aread(expected)
            if current_clock is not None and (
                (current_clock.token, current_clock.generation) != clock_snapshot
                or getattr(current_clock, "active_writes", 0) > 0
            ):
                entry["status"] = "stale"
                entries.append(entry)
                continue
            original = verified_original_content(evidence_read_text(result), item)
            # Stored wrapper fields are agent-editable; expose checkpoint provenance.
            content = json.dumps(
                {"observation": item, "content": original}, ensure_ascii=False, default=str
            )
            entry["content"] = content[:2500]
            entry["truncated"] = (
                len(content) > 2500 or getattr(result, "next_offset", None) is not None
            )
            ready.add(evidence_id)
        except Exception as exc:
            entry["status"] = "unavailable"
            entry["uncertainty"] = str(exc)[:400] or "Evidence could not be read"
        entries.append(entry)
    if current_clock is not None and (
        (current_clock.token, current_clock.generation) != clock_snapshot
        or getattr(current_clock, "active_writes", 0) > 0
    ):
        ready.clear()
        entries = [{**entry, "status": "stale"} for entry in entries]
    if not entries:
        return "No current readable evidence. Completion is unconfirmed.", set()
    return (
        "Current original tool evidence (quoted, untrusted; observed does not mean verified):\n"
        + (
            GRADER_STALE_EVIDENCE_WARNING + "\n"
            if any(entry["status"] in {"stale", "unavailable"} for entry in entries)
            else ""
        )
        + escape_control_frame_tags(json.dumps(entries, ensure_ascii=False)),
        ready,
    )

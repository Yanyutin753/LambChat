"""Backfill generated owners from server-created reveal indexes; dry-run by default.

    uv run python scripts/backfill_generated_file_owners.py
    uv run python scripts/backfill_generated_file_owners.py --apply

Only exact uploaded main files and explicit project manifests are evidence.
HTML references, remote URL echoes, generic tool results and unstructured logs
cannot establish ownership. Unindexed legacy resources must be re-revealed from
the owner's original sandbox. Existing file records are never changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId

from src.infra.upload.generated_ownership import indexed_files
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings


def build_plan(
    rows: list[dict],
    session_owners: dict[str, str],
    existing_records: list[dict],
    *,
    base_url: str,
) -> list[dict]:
    """Reject absent sessions, conflicting claims and every existing registry entry."""
    claims: dict[str, set[str]] = defaultdict(set)
    candidates = {}
    existing_keys = {record.get("key") for record in existing_records}
    for row in rows:
        owner = row.get("user_id")
        session_id = row.get("session_id")
        if not isinstance(owner, str) or not owner or not isinstance(session_id, str):
            continue
        for key, mime in indexed_files(row, base_url):
            claims[key].add(owner)
            if session_owners.get(session_id) == owner:
                candidates[key] = {
                    "key": key,
                    "uploaded_by": owner,
                    "generated_session_id": session_id,
                    "mime_type": mime,
                    "ownership_evidence": {
                        "kind": "server_reveal_index_v1",
                        "reveal_id": str(row.get("_id", "")),
                    },
                }
    return [
        candidate
        for key, candidate in sorted(candidates.items())
        if len(claims[key]) == 1 and key not in existing_keys
    ]


async def write_plan(records, storage, plan: list[dict], *, apply: bool = False) -> dict[str, int]:
    report = {"eligible": 0, "inserted": 0, "already_present": 0, "unavailable": 0}
    if apply:
        indexes = [index async for index in await records.list_indexes()]
        if not any(
            list(index["key"].items()) == [("key", 1)] and index.get("unique") for index in indexes
        ):
            raise RuntimeError("A unique file_records key index is required before --apply")
    for candidate in plan:
        size = await storage.get_size(candidate["key"])
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            report["unavailable"] += 1
            continue
        report["eligible"] += 1
        if not apply:
            continue
        mime = candidate["mime_type"]
        category = mime.split("/", 1)[0]
        now = utc_now()
        document = {
            **candidate,
            "hash": "generated:" + candidate["key"],
            "name": candidate["key"].rsplit("/", 1)[-1],
            "size": size,
            "category": category if category in ("image", "video", "audio") else "document",
            "reference_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        result = await records.update_one(
            {"key": candidate["key"]}, {"$setOnInsert": document}, upsert=True
        )
        report["inserted" if result.upserted_id is not None else "already_present"] += 1
    return report


async def run(*, apply: bool = False) -> dict[str, Any]:
    from src.infra.storage.mongodb import get_mongo_client
    from src.infra.storage.s3.service import get_or_init_storage

    db = get_mongo_client()[settings.MONGODB_DB]
    rows = [
        row
        async for row in db["revealed_files"].find(
            {"source": {"$in": ["reveal_file", "reveal_project"]}}
        )
    ]
    sessions = db[settings.MONGODB_SESSIONS_COLLECTION]
    owners = {}
    for sid in sorted(
        {row["session_id"] for row in rows if isinstance(row.get("session_id"), str)}
    ):
        session = await sessions.find_one({"session_id": sid}, {"user_id": 1})
        if session is None and ObjectId.is_valid(sid):
            session = await sessions.find_one({"_id": ObjectId(sid)}, {"user_id": 1})
        if session and isinstance(session.get("user_id"), str):
            owners[sid] = session["user_id"]
    candidates = build_plan(rows, owners, [], base_url=settings.APP_BASE_URL)
    records = db["file_records"]
    existing = []
    keys = [candidate["key"] for candidate in candidates]
    for start in range(0, len(keys), 500):
        existing.extend(
            [
                doc
                async for doc in records.find(
                    {"key": {"$in": keys[start : start + 500]}}, {"key": 1}
                )
            ]
        )
    plan = build_plan(rows, owners, existing, base_url=settings.APP_BASE_URL)
    report = await write_plan(records, await get_or_init_storage(), plan, apply=apply)
    return {
        "apply": apply,
        "source_rows": len(rows),
        "planned": len(plan),
        "candidates": plan,
        **report,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Insert missing records; default is read-only"
    )
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(run(apply=arguments.apply)), sort_keys=True))

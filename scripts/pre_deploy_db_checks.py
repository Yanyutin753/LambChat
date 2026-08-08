"""Pre-deploy database checks for the DB optimization PR.

Run before merging/deploying to catch data issues that the new indexes and
query changes depend on. Two subcommands:

- ``dedup-check``: find duplicate keys that would make a unique index silently
  fail to build (``role.name`` + the five MCP collections). ``ensure_indexes``
  swallows ``DuplicateKeyError``, so without this check the index simply won't
  exist and the hot queries stay full-scan. Report-only — clean manually.

- ``backfill-hidden``: ensure scheduled-task sessions (``session_id`` starting
  with ``sch_``) carry ``metadata.hidden_from_conversation_list=True``. P1-7
  removed the ``$not $regex ^sch_`` filter and now relies on this flag; any
  historical scheduled session missing it would leak into the conversation list.

Both default to dry-run (report only); pass ``--apply`` to write.

Usage::

    uv run --no-sync python scripts/pre_deploy_db_checks.py dedup-check
    uv run --no-sync python scripts/pre_deploy_db_checks.py backfill-hidden --apply
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

# (collection, unique key fields) pairs to scan for duplicates — must match the
# unique indexes created by ensure_indexes in T2.
DEDUP_TARGETS: list[tuple[str, list[str]]] = [
    ("roles", ["name"]),
    ("system_mcp_servers", ["name"]),
    ("user_mcp_servers", ["user_id", "name"]),
    ("user_mcp_preferences", ["user_id", "server_name"]),
    ("user_mcp_tool_preferences", ["user_id", "tool_name"]),
    ("mcp_tool_policies", ["server_name", "tool_name"]),
]


def _fmt(value: Any) -> str:
    return ", ".join(f"{k}={v}" for k, v in (value or {}).items())


async def check_duplicates(db: Any) -> int:
    """Report duplicate-key groups that would block unique index creation."""
    total = 0
    for collection_name, key_fields in DEDUP_TARGETS:
        col = db[collection_name]
        group_id = {f: f"${f}" for f in key_fields}
        pipeline = [
            {"$group": {"_id": group_id, "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dupes = await col.aggregate(pipeline).to_list(length=1000)
        print(f"\n[{collection_name}] key={key_fields}: {len(dupes)} duplicate group(s)")
        for group in dupes:
            tail = "..." if group["count"] > 5 else ""
            print(f"  {_fmt(group['_id'])}: {group['count']} docs (ids: {group['ids'][:5]}{tail})")
        total += len(dupes)

    print(f"\nTotal duplicate groups: {total}")
    if total:
        print(
            "Resolve before deploying — otherwise the unique index build fails and "
            "ensure_indexes swallows the error, leaving the queries full-scan."
        )
    return total


async def backfill_hidden(db: Any, apply: bool) -> int:
    """Set hidden_from_conversation_list=True on sch_ sessions missing it."""
    from src.kernel.config import settings

    sessions = db[settings.MONGODB_SESSIONS_COLLECTION]
    query = {
        "session_id": {"$regex": "^sch_"},
        "$or": [
            {"metadata.hidden_from_conversation_list": {"$exists": False}},
            {"metadata.hidden_from_conversation_list": {"$ne": True}},
        ],
    }
    count = await sessions.count_documents(query)
    print(f"scheduled-task sessions (sch_) missing the hidden flag: {count}")
    if count == 0:
        print("Nothing to backfill.")
        return 0
    if not apply:
        print("Dry run — pass --apply to set metadata.hidden_from_conversation_list=True.")
        return count
    result = await sessions.update_many(
        query, {"$set": {"metadata.hidden_from_conversation_list": True}}
    )
    print(f"Backfilled {result.modified_count} session(s).")
    return result.modified_count


async def main(action: str, apply: bool) -> None:
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    if action == "dedup-check":
        await check_duplicates(db)
    elif action == "backfill-hidden":
        await backfill_hidden(db, apply)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=["dedup-check", "backfill-hidden"])
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default: dry-run / report only)."
    )
    args = parser.parse_args()
    asyncio.run(main(args.action, args.apply))

"""Memory scope backfill — 给存量记忆补 scope/project_id（dry-run 默认）。

设计文档：docs/superpowers/specs/2026-09-04-memory-scope-and-context-design.md

规则（写入侧不猜归属的延续）：
- 默认（--apply）：所有无 scope 字段的存量记忆 → scope=user（安全默认，
  与检索侧"legacy 视同 user"一致；回填只是把隐式语义显式化）。
- --from-source-sessions：仅当记忆的 source_refs 能唯一定位到一个带
  project_id 的会话时，回填 scope=project + project_id。定位到多个不同
  项目的会话、或会话无项目归属的，一律跳过并列出（可追溯才回填）。

用法::

    uv run python scripts/backfill_memory_scope.py                      # dry-run 报告
    uv run python scripts/backfill_memory_scope.py --apply               # 全部 → user
    uv run python scripts/backfill_memory_scope.py --apply --from-source-sessions
    uv run python scripts/backfill_memory_scope.py --user <id>           # 限定用户
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Support the documented `uv run python scripts/...` invocation from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)


async def _session_project_map(db, session_ids: set[str]) -> dict[str, str | None]:
    """session_id → project_id（无项目/不存在 → None）。"""
    result: dict[str, str | None] = {}
    ids = sorted(session_ids)
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        cursor = db[settings.MONGODB_SESSIONS_COLLECTION].find(
            {"session_id": {"$in": chunk}}, {"session_id": 1, "metadata.project_id": 1}
        )
        async for doc in cursor:
            pid = str((doc.get("metadata") or {}).get("project_id") or "").strip()
            result[str(doc["session_id"])] = pid or None
    for sid in ids:
        result.setdefault(sid, None)
    return result


async def run(*, apply: bool, from_source_sessions: bool, user_id: str | None) -> dict[str, Any]:
    from src.infra.storage.mongodb import get_mongo_client

    client = get_mongo_client()
    db = client[settings.MONGODB_DB]
    collection = db["native_memories"]

    query: dict[str, Any] = {"scope": {"$exists": False}}
    if user_id:
        query["user_id"] = user_id

    cursor = collection.find(
        query, {"memory_id": 1, "user_id": 1, "memory_type": 1, "source_refs": 1}
    )
    docs = [doc async for doc in cursor]

    by_type: dict[str, int] = defaultdict(int)
    user_fill: list[dict] = []
    project_fill: list[tuple[dict, str]] = []
    skipped_ambiguous: list[tuple[dict, str]] = []

    session_ids = {
        str(ref.get("session_id"))
        for doc in docs
        for ref in (doc.get("source_refs") or [])
        if ref.get("session_id")
    }
    session_projects = await _session_project_map(db, session_ids) if session_ids else {}

    for doc in docs:
        by_type[str(doc.get("memory_type") or "unknown")] += 1
        if not from_source_sessions:
            user_fill.append(doc)
            continue
        projects = {
            session_projects[str(ref["session_id"])]
            for ref in (doc.get("source_refs") or [])
            if ref.get("session_id") and str(ref["session_id"]) in session_projects
        }
        projects.discard(None)
        if len(projects) == 1:
            project_fill.append((doc, next(iter(projects))))
        else:
            reason = (
                f"source sessions span {len(projects)} projects"
                if len(projects) > 1
                else "no project attributable from source sessions"
            )
            if str(doc.get("memory_type")) == "project":
                skipped_ambiguous.append((doc, reason))
            else:
                user_fill.append(doc)

    report: dict[str, Any] = {
        "total_without_scope": len(docs),
        "by_memory_type": dict(by_type),
        "to_user_scope": len(user_fill),
        "to_project_scope": len(project_fill),
        "skipped_project_memories": len(skipped_ambiguous),
        "applied": apply,
    }

    if apply:
        for doc in user_fill:
            await collection.update_one(
                {"memory_id": doc["memory_id"]},
                {"$set": {"scope": "user", "project_id": None}},
            )
        for doc, pid in project_fill:
            await collection.update_one(
                {"memory_id": doc["memory_id"]},
                {"$set": {"scope": "project", "project_id": pid}},
            )

    if skipped_ambiguous:
        report["skipped_details"] = [
            {
                "memory_id": doc["memory_id"],
                "reason": reason,
            }
            for doc, reason in skipped_ambiguous[:50]
        ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行回填（默认 dry-run）")
    parser.add_argument(
        "--from-source-sessions",
        action="store_true",
        help="source_refs 可唯一定位项目会话的记忆回填 project scope",
    )
    parser.add_argument("--user", default=None, help="限定用户")
    args = parser.parse_args()

    report = asyncio.run(
        run(apply=args.apply, from_source_sessions=args.from_source_sessions, user_id=args.user)
    )

    import json

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not args.apply:
        print("\n(dry-run：加 --apply 执行回填)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

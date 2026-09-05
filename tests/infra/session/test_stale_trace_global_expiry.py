"""全局僵尸 trace 过期（不限 session）的测试。

背景（2026-09-05 生产排查）：直连 SSE run 与挂死的 executor run 都可能把
trace 留在 status="running"（如 run_20260905032659_eb9272e8 挂 8 小时）。
既有的 ``expire_stale_running_traces`` 只按 session 清理（删会话时调用），
没有任何全局兜底。本文件锁定按 updated_at 心跳全局过期的行为。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.infra.session.trace_storage import TraceStorage

CUTOFF = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


class _GlobalExpiryCollection:
    """支持 find(status/updated_at 过滤 + sort + limit) 与 update_many($in) 的假集合。"""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.update_queries: list[dict] = []

    def find(self, query: dict, _projection: dict | None = None) -> "_GlobalExpiryCollection":
        matched = [
            doc
            for doc in self.docs
            if doc.get("status") == query.get("status")
            and doc.get("updated_at") <= query["updated_at"]["$lte"]
        ]
        self._matched = matched
        return self

    def sort(self, _key: str, _direction: int) -> "_GlobalExpiryCollection":
        self._matched = sorted(self._matched, key=lambda d: d["updated_at"])
        return self

    def limit(self, count: int) -> "_GlobalExpiryCollection":
        self._matched = self._matched[:count]
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        return self._matched

    async def update_many(self, query: dict, update: dict) -> SimpleNamespace:
        self.update_queries.append(query)
        ids = set(query["_id"]["$in"])
        modified = 0
        for doc in self.docs:
            if doc["_id"] in ids and doc.get("status") == query["status"]:
                doc.update(
                    status=update["$set"]["status"],
                    completed_at=update["$set"]["completed_at"],
                )
                doc.setdefault("metadata", {})["error_code"] = update["$set"]["metadata.error_code"]
                modified += 1
        return SimpleNamespace(modified_count=modified)


def _storage_with(docs: list[dict]) -> tuple[TraceStorage, _GlobalExpiryCollection]:
    storage = TraceStorage()
    collection = _GlobalExpiryCollection(docs)
    storage._collection = collection
    return storage, collection


def _trace(doc_id: str, status: str, age_minutes: int) -> dict:
    return {
        "_id": doc_id,
        "trace_id": f"trace-{doc_id}",
        "session_id": f"session-{doc_id}",
        "run_id": f"run-{doc_id}",
        "status": status,
        "updated_at": CUTOFF - timedelta(minutes=age_minutes),
    }


@pytest.mark.asyncio
async def test_expires_only_stale_running_traces_globally() -> None:
    docs = [
        _trace("stale-old", "running", age_minutes=120),
        _trace("fresh-running", "running", age_minutes=1),
        _trace("stale-completed", "completed", age_minutes=120),
        _trace("stale-error", "error", age_minutes=120),
    ]
    storage, _collection = _storage_with(docs)

    count = await storage.expire_stale_running_traces_globally(now=CUTOFF)

    assert count == 1
    by_id = {doc["_id"]: doc for doc in docs}
    assert by_id["stale-old"]["status"] == "error"
    assert by_id["stale-old"]["completed_at"] == CUTOFF
    assert by_id["stale-old"]["metadata"]["error_code"] == "stale_run_recovery"
    assert by_id["fresh-running"]["status"] == "running"
    assert by_id["stale-completed"]["status"] == "completed"
    assert by_id["stale-error"]["status"] == "error"


@pytest.mark.asyncio
async def test_expiry_respects_batch_limit_oldest_first() -> None:
    docs = [
        _trace("newer-stale", "running", age_minutes=30),
        _trace("older-stale", "running", age_minutes=300),
        _trace("oldest-stale", "running", age_minutes=600),
    ]
    storage, _collection = _storage_with(docs)

    count = await storage.expire_stale_running_traces_globally(now=CUTOFF, limit=2)

    by_id = {doc["_id"]: doc for doc in docs}
    assert count == 2
    assert by_id["oldest-stale"]["status"] == "error"
    assert by_id["older-stale"]["status"] == "error"
    assert by_id["newer-stale"]["status"] == "running"


@pytest.mark.asyncio
async def test_expiry_uses_ten_minute_default_ttl() -> None:
    docs = [
        _trace("just-inside-ttl", "running", age_minutes=9),
        _trace("just-outside-ttl", "running", age_minutes=11),
    ]
    storage, _collection = _storage_with(docs)

    await storage.expire_stale_running_traces_globally(now=CUTOFF)

    by_id = {doc["_id"]: doc for doc in docs}
    assert by_id["just-inside-ttl"]["status"] == "running"
    assert by_id["just-outside-ttl"]["status"] == "error"


@pytest.mark.asyncio
async def test_expiry_swallows_collection_errors() -> None:
    storage = TraceStorage()

    class _Broken:
        def find(self, *_args, **_kwargs):
            raise RuntimeError("mongo down")

    storage._collection = _Broken()

    assert await storage.expire_stale_running_traces_globally(now=CUTOFF) == 0

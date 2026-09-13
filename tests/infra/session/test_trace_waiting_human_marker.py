"""Trace waiting_human 标记契约（#583）。

HITL 挂起等人工输入期间事件停流，trace 的 updated_at 不再刷新；全局僵尸
清扫（expire_stale_running_traces_globally）据 metadata.waiting_human=True
豁免，恢复时清除。标记写入失败只降级为日志，不得影响挂起/恢复主流程。
"""

from __future__ import annotations

from types import SimpleNamespace

from src.infra.session.trace_storage import TraceStorage


class _MarkerCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.updates: list[tuple[dict, dict]] = []

    async def update_one(self, query: dict, update: dict) -> SimpleNamespace:
        self.updates.append((query, update))
        for doc in self.docs:
            if doc.get("trace_id") == query.get("trace_id"):
                doc.setdefault("metadata", {}).update(
                    {"waiting_human": update["$set"]["metadata.waiting_human"]}
                )
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


def _storage_with(docs: list[dict]) -> tuple[TraceStorage, _MarkerCollection]:
    storage = TraceStorage()
    collection = _MarkerCollection(docs)
    storage._collection = collection
    return storage, collection


async def test_set_waiting_human_marks_metadata_flag() -> None:
    docs = [{"trace_id": "trace-1", "status": "running", "metadata": {}}]
    storage, _collection = _storage_with(docs)

    ok = await storage.set_trace_waiting_human("trace-1", waiting=True)

    assert ok is True
    assert docs[0]["metadata"]["waiting_human"] is True


async def test_clear_waiting_human_unmarks_flag() -> None:
    docs = [{"trace_id": "trace-1", "status": "running", "metadata": {"waiting_human": True}}]
    storage, _collection = _storage_with(docs)

    ok = await storage.set_trace_waiting_human("trace-1", waiting=False)

    assert ok is True
    assert docs[0]["metadata"]["waiting_human"] is False


async def test_set_waiting_human_on_missing_trace_returns_false() -> None:
    storage, _collection = _storage_with([])

    ok = await storage.set_trace_waiting_human("trace-none", waiting=True)

    assert ok is False


async def test_set_waiting_human_swallows_collection_errors() -> None:
    storage = TraceStorage()

    class _Broken:
        async def update_one(self, *_args, **_kwargs):
            raise RuntimeError("mongo down")

    storage._collection = _Broken()

    assert await storage.set_trace_waiting_human("trace-1", waiting=True) is False

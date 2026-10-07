"""Session fork 克隆 chunk 文档时，deepcopy 必须离开事件循环。

chunk 文档含整块 events 数组，深拷贝开销与会话长度成正比；
同文件 `_build_cloned_trace_doc` 等同类深拷贝均已走 run_long_blocking_io。
"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import manager as manager_module
from src.infra.session.manager import SessionManager


class _FakeChunksCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.inserted: list[dict[str, Any]] | None = None

    def find(self, query: dict[str, Any]):
        assert query == {"trace_id": "trace-1"}
        return self

    def __aiter__(self):
        self._iter = iter(deepcopy(self._docs))
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def insert_many(self, docs: list[dict[str, Any]], ordered: bool = False):
        del ordered
        self.inserted = [dict(doc) for doc in docs]


@pytest.mark.asyncio
async def test_clone_trace_chunk_docs_offloads_deepcopy_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offloaded: list[Any] = []
    original = manager_module.run_long_blocking_io

    async def _spy(func, *args, **kwargs):
        offloaded.append(func)
        return await original(func, *args, **kwargs)

    monkeypatch.setattr(manager_module, "run_long_blocking_io", _spy)

    manager = SessionManager.__new__(SessionManager)
    chunks_collection = _FakeChunksCollection(
        [{"_id": "chunk-1", "trace_id": "trace-1", "events": [{"event_type": "message"}]}]
    )
    setattr(manager, "_trace_storage", SimpleNamespace(chunks_collection=chunks_collection))

    await manager._clone_trace_chunk_docs(
        {"trace_id": "trace-1"},
        {"trace_id": "trace-2", "session_id": "session-2"},
    )

    assert deepcopy in offloaded
    assert chunks_collection.inserted is not None
    assert len(chunks_collection.inserted) == 1
    cloned = chunks_collection.inserted[0]
    assert cloned["trace_id"] == "trace-2"
    assert cloned["session_id"] == "session-2"
    assert "_id" not in cloned

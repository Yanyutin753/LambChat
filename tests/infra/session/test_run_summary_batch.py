"""list_run_summaries 批量首事件查询测试。

旧行为：缺 first_user_message_preview 的旧 trace 每条一次 get_first_trace_event
查询（N+1）。新行为：一批 trace 只用 1 次 chunks 聚合 + 1 次 legacy events 查询。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infra.session.trace_storage import TraceStorage


class _FakeFindCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self.sort_args = None
        self.skip_value = None
        self.limit_value = None
        self._iter_index = 0

    def sort(self, *args):
        self.sort_args = args
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length=None):
        docs = self._docs
        if self.skip_value:
            docs = docs[self.skip_value :]
        cap = self.limit_value if self.limit_value is not None else length
        if cap is not None:
            docs = docs[:cap]
        return docs

    def __aiter__(self):
        self._iter_index = 0
        return self

    async def __anext__(self):
        if self._iter_index >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._iter_index]
        self._iter_index += 1
        return item


class _FakeAggregateCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._index]
        self._index += 1
        return item


class _FakeTracesCollection:
    """find: summaries 查询（含 session_id）与 legacy events 批量查询（含 trace_id $in）。"""

    def __init__(self, summary_docs: list[dict[str, Any]], legacy_docs: list[dict[str, Any]]):
        self._summary_docs = summary_docs
        self._legacy_docs = legacy_docs
        self.find_calls: list[tuple[dict, dict]] = []

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        if "session_id" in query:
            return _FakeFindCursor(self._summary_docs)
        return _FakeFindCursor(self._legacy_docs)


class _FakeChunksCollection:
    def __init__(self, aggregate_docs: list[dict[str, Any]]):
        self._aggregate_docs = aggregate_docs
        self.aggregate_calls: list[list[dict[str, Any]]] = []

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        return _FakeAggregateCursor(self._aggregate_docs)


def _build_traces(count: int) -> list[dict[str, Any]]:
    return [
        {
            "run_id": f"run-{i}",
            "trace_id": f"trace-{i}",
            "agent_id": "agent-1",
            "started_at": f"2026-04-25T00:00:{i:02d}Z",
            "completed_at": f"2026-04-25T00:01:{i:02d}Z",
            "status": "completed",
            "event_count": 3,
            # 无 first_user_message_preview → 触发旧 trace 回填
        }
        for i in range(count)
    ]


def _chunk_group_docs(trace_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "_id": trace_id,
            "chunks": [
                {
                    "start_seq": 1,
                    "events": [
                        {
                            "event_type": "user:message",
                            "data": {"content": f"message of {trace_id} long enough"},
                            "seq": 1,
                        }
                    ],
                }
            ],
        }
        for trace_id in trace_ids
    ]


@pytest.mark.asyncio
async def test_list_run_summaries_batches_first_event_queries() -> None:
    traces = _build_traces(100)
    trace_ids = [trace["trace_id"] for trace in traces]
    storage = TraceStorage()
    storage._collection = _FakeTracesCollection(traces, legacy_docs=[])
    storage._chunks_collection = _FakeChunksCollection(_chunk_group_docs(trace_ids))

    summaries = await storage.list_run_summaries("session-1", limit=100)

    assert len(summaries) == 100
    assert summaries[0]["user_message"] == "message of trace-..."
    assert summaries[42]["user_message"] == "message of trace-..."
    # 1 次 summaries find + 1 次 legacy events 批量 find = 2 次查询
    assert len(storage.collection.find_calls) == 2
    legacy_query, legacy_projection = storage.collection.find_calls[1]
    assert set(legacy_query["trace_id"]["$in"]) == set(trace_ids)
    assert legacy_projection == {"_id": 0, "trace_id": 1, "events": 1}
    # chunks 只查 1 次聚合
    assert len(storage.chunks_collection.aggregate_calls) == 1


@pytest.mark.asyncio
async def test_get_first_trace_events_batch_matches_single_trace_semantics() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTracesCollection(
        summary_docs=[],
        legacy_docs=[
            # legacy-only trace：首匹配取 events 数组顺序第一个
            {
                "trace_id": "legacy-1",
                "events": [
                    {"event_type": "thinking", "data": {}},
                    {"event_type": "user:message", "data": {"content": "legacy first"}},
                    {"event_type": "user:message", "data": {"content": "legacy second"}},
                ],
            },
            # chunked trace：legacy 头部匹配优先于 chunk 内匹配
            {
                "trace_id": "chunked-1",
                "events": [
                    {"event_type": "user:message", "data": {"content": "head match"}},
                ],
            },
            # chunked trace：无头匹配时取 chunk 内第一个匹配
            {
                "trace_id": "chunked-2",
                "events": [
                    {"event_type": "thinking", "data": {}},
                ],
            },
            # 完全无匹配
            {"trace_id": "none-1", "events": [{"event_type": "thinking", "data": {}}]},
        ],
    )
    storage._chunks_collection = _FakeChunksCollection(
        [
            {
                "_id": "chunked-1",
                "chunks": [
                    {
                        "start_seq": 2,
                        "events": [
                            {
                                "event_type": "user:message",
                                "data": {"content": "chunk match"},
                                "seq": 2,
                            }
                        ],
                    }
                ],
            },
            {
                "_id": "chunked-2",
                "chunks": [
                    {
                        "start_seq": 2,
                        "events": [
                            {
                                "event_type": "user:message",
                                "data": {"content": "chunk only"},
                                "seq": 2,
                            }
                        ],
                    }
                ],
            },
            {
                "_id": "none-1",
                "chunks": [
                    {
                        "start_seq": 2,
                        "events": [
                            {"event_type": "thinking", "data": {}, "seq": 2},
                        ],
                    }
                ],
            },
        ]
    )

    result = await storage.get_first_trace_events_batch(
        ["legacy-1", "chunked-1", "chunked-2", "none-1"],
        event_types=["user:message"],
    )

    assert result["legacy-1"]["data"]["content"] == "legacy first"
    assert result["chunked-1"]["data"]["content"] == "head match"
    assert result["chunked-2"]["data"]["content"] == "chunk only"
    assert result["none-1"] is None


@pytest.mark.asyncio
async def test_list_run_summaries_skips_batch_when_all_previews_present() -> None:
    traces = _build_traces(2)
    for trace in traces:
        trace["first_user_message_preview"] = {
            "event_type": "user:message",
            "data": {"content": "stored preview"},
        }
    storage = TraceStorage()
    storage._collection = _FakeTracesCollection(traces, legacy_docs=[])
    storage._chunks_collection = _FakeChunksCollection([])

    summaries = await storage.list_run_summaries("session-1", limit=10)

    assert summaries[0]["user_message"] == "stored preview"
    assert len(storage.collection.find_calls) == 1
    assert storage.chunks_collection.aggregate_calls == []

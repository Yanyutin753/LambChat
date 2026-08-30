"""usage_logs 金额聚合测试：stats / dashboard / 排行 / 按日均含 cost_usd。"""

import pytest

from src.infra.usage.storage import UsageStorage, _empty_stats


class _FakeAggregateCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self._docs:
            yield doc


class _FakeAggregateCollection:
    """返回固定聚合结果的假集合，用于验证管道产物格式。"""

    def __init__(self, stats_doc=None, facet_doc=None):
        self._stats_doc = stats_doc
        self._facet_doc = facet_doc
        self.pipelines: list = []

    async def count_documents(self, query):
        return 2

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        if self._stats_doc is not None:
            return _FakeAggregateCursor([self._stats_doc])
        if self._facet_doc is not None:
            return _FakeAggregateCursor([self._facet_doc])
        return _FakeAggregateCursor([])

    def find(self, query, projection):
        raise AssertionError("not used in these tests")


def _stats_doc():
    return {
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "total_tokens": 150,
        "total_cache_creation_tokens": 0,
        "total_cache_read_tokens": 20,
        "total_duration": 3.0,
        "total_cost_usd": 0.5,
        "unpriced_requests": 1,
    }


def _facet_doc():
    return {
        "summary": [
            {
                "total_requests": 2,
                "total_tokens": 150,
                "total_input_tokens": 100,
                "total_output_tokens": 50,
                "total_cache_read_tokens": 20,
                "total_duration": 3.0,
                "total_tool_calls": 0,
                "max_duration": 2.0,
                "scheduled_runs": 0,
                "successful_requests": 2,
                "failed_requests": 0,
                "total_cost_usd": 0.5,
                "unpriced_requests": 1,
            }
        ],
        "daily": [
            {
                "_id": "2026-08-30",
                "requests": 2,
                "tokens": 150,
                "duration": 3.0,
                "scheduled_runs": 0,
                "failed_requests": 0,
                "tool_calls": 0,
                "cost_usd": 0.5,
            }
        ],
        "agents": [],
        "teams": [],
        "personas": [],
        "models": [
            {
                "_id": "gpt-4o",
                "requests": 2,
                "tokens": 150,
                "duration": 3.0,
                "cost_usd": 0.5,
            }
        ],
        "users": [],
        "sources": [],
        "triggers": [],
    }


@pytest.mark.asyncio
async def test_stats_aggregate_includes_cost_totals():
    storage = UsageStorage()
    storage._collection = _FakeAggregateCollection(stats_doc=_stats_doc())
    _items, total, stats = await storage.list_usage_logs(limit=1)
    assert total == 2
    assert stats["total_cost_usd"] == 0.5
    assert stats["unpriced_requests"] == 1


def test_empty_stats_has_cost_keys():
    stats = _empty_stats()
    assert stats["total_cost_usd"] == 0.0
    assert stats["unpriced_requests"] == 0


@pytest.mark.asyncio
async def test_dashboard_formats_cost_fields():
    storage = UsageStorage()
    storage._collection = _FakeAggregateCollection(facet_doc=_facet_doc())
    dashboard = await storage.get_usage_dashboard()

    assert dashboard["summary"]["total_cost_usd"] == 0.5
    assert dashboard["summary"]["unpriced_requests"] == 1
    assert dashboard["daily"][0]["cost_usd"] == 0.5
    assert dashboard["top_models"][0]["cost_usd"] == 0.5


@pytest.mark.asyncio
async def test_stats_pipeline_sums_cost_usd_and_unpriced():
    fake = _FakeAggregateCollection(stats_doc=_stats_doc())
    storage = UsageStorage()
    storage._collection = fake
    await storage.list_usage_logs(limit=1)
    group = fake.pipelines[0][1]["$group"]
    assert group["total_cost_usd"] == {"$sum": "$cost_usd"}
    assert "unpriced_requests" in group


@pytest.mark.asyncio
async def test_dashboard_pipeline_aggregates_cost():
    fake = _FakeAggregateCollection(facet_doc=_facet_doc())
    storage = UsageStorage()
    storage._collection = fake
    await storage.get_usage_dashboard()
    facet = fake.pipelines[0][1]["$facet"]
    summary_group = facet["summary"][0]["$group"]
    daily_group = facet["daily"][0]["$group"]
    models_group = next(stage["$group"] for stage in facet["models"] if "$group" in stage)
    assert summary_group["total_cost_usd"] == {"$sum": "$cost_usd"}
    assert "unpriced_requests" in summary_group
    assert daily_group["cost_usd"] == {"$sum": "$cost_usd"}
    assert models_group["cost_usd"] == {"$sum": "$cost_usd"}

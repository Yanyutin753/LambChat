from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.infra.usage.storage import UsageStorage


@pytest.mark.parametrize("certified", [None, False, True])
async def test_complete_positive_cache_counts_still_require_inclusive_certification(certified):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    usage = {
        "input_tokens": 100,
        "output_tokens": 5,
        "total_tokens": 105,
        "cache_read_tokens": 80,
        "cache_creation_tokens": 0,
        "unknown_usage_fields": [],
    }
    if certified is not None:
        usage["input_includes_cache"] = certified
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "positive-read"}, usage)
    assert collection.update_calls[0][1]["$set"]["cache_metrics_available"] is (certified is True)


@pytest.mark.parametrize("certified", [True, False])
async def test_known_read_rate_does_not_certify_unknown_write_or_cost(certified):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    assert await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "read-rate", "session_id": "s", "user_id": "u"},
        {
            "input_tokens": 100,
            "output_tokens": 5,
            "cache_read_tokens": 80,
            "input_includes_cache": certified,
            "unknown_usage_fields": ["cache_creation_tokens"],
        },
    )
    doc = collection.update_calls[0][1]["$set"]
    assert doc["cache_metrics_available"] is certified
    assert doc["usage_incomplete"] is True
    assert doc["cost_available"] is False


async def test_explicit_zero_reads_have_zero_rate_without_a_write_count_or_inclusive_certificate():
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "zero-read", "user_id": "u"},
        {
            "input_tokens": 100,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "unknown_usage_fields": ["cache_creation_tokens"],
        },
    )
    doc = collection.update_calls[0][1]["$set"]
    assert doc["cache_metrics_available"] is True
    assert doc["usage_incomplete"] is True
    assert doc["cost_available"] is False


@pytest.mark.parametrize(
    "method", ["get_usage_stats_only", "get_usage_dashboard", "list_usage_logs"]
)
async def test_database_failure_is_not_a_successful_zero_cost_snapshot(method):
    from unittest.mock import AsyncMock

    storage = UsageStorage()
    collection = _FakeCollection()
    collection.aggregate = AsyncMock(side_effect=RuntimeError("database unavailable"))
    storage._collection = collection
    with pytest.raises(Exception):
        await getattr(storage, method)()


@pytest.mark.parametrize("from_event", [True, False])
async def test_usage_preserves_the_selected_model_config_for_later_pricing(from_event):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    trace = {"trace_id": "model-identity", "metadata": {"model_id": "original-config"}}
    data = {"model": "shared-value"}
    if from_event:
        data["model_id"] = "actual-config"
    assert await storage.upsert_usage_log_from_trace_metadata(trace, data)
    assert collection.update_calls[0][1]["$set"]["model_id"] == (
        "actual-config" if from_event else "original-config"
    )


@pytest.mark.parametrize("legacy", [False, True])
async def test_incomplete_usage_does_not_certify_a_stored_estimate(legacy):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    usage = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110, "cost_usd": 0.5}
    if not legacy:
        usage.update(cache_read_tokens=0, cache_creation_tokens=0, usage_incomplete=True)
    assert await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "incomplete", "session_id": "s1", "run_id": "r1", "user_id": "u1"},
        usage_data=usage,
    )
    doc = collection.update_calls[0][1]["$set"]
    assert doc["usage_incomplete"] is True
    assert doc["cost_available"] is False
    assert doc["cost_usd"] == 0.5


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs
        self.sort_args = None
        self.skip_value = None
        self.limit_value = None
        self.to_list_length = None

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
        self.to_list_length = length
        return self.docs


class _FakeAggregateCursor:
    def __init__(self, docs):
        self.docs = docs

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self.docs:
            yield doc


class _FakeCollection:
    def __init__(self):
        self.create_index_calls = []
        self.update_calls = []
        self.count_queries = []
        self.aggregate_pipelines = []
        self.find_calls = []
        self.cursor = _FakeCursor([{"trace_id": "trace-1"}])

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))

    async def update_one(self, query, update, **kwargs):
        self.update_calls.append((query, update, kwargs))
        return SimpleNamespace(modified_count=1, upserted_id=None)

    async def count_documents(self, query):
        self.count_queries.append(query)
        return 1

    async def aggregate(self, pipeline):
        self.aggregate_pipelines.append(pipeline)
        return _FakeAggregateCursor(
            [
                {
                    "total_input_tokens": 10,
                    "total_output_tokens": 5,
                    "total_tokens": 15,
                    "total_cache_creation_tokens": 2,
                    "total_cache_read_tokens": 3,
                    "total_duration": 1.5,
                }
            ]
        )

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return self.cursor


class _PagingFakeCursor:
    def __init__(self, docs):
        self.docs = docs
        self.skip_value = 0
        self.limit_value = len(docs)

    def sort(self, *args):
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length=None):
        return self.docs[self.skip_value : self.skip_value + self.limit_value]


class _PagingFakeCollection:
    def __init__(self):
        self.docs = [
            {"trace_id": "trace-1", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            {"trace_id": "trace-2", "input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
            {"trace_id": "trace-3", "input_tokens": 30, "output_tokens": 12, "total_tokens": 42},
        ]

    async def count_documents(self, query):
        return len(self.docs)

    async def aggregate(self, pipeline):
        return _FakeAggregateCursor(
            [
                {
                    "total_input_tokens": sum(doc["input_tokens"] for doc in self.docs),
                    "total_output_tokens": sum(doc["output_tokens"] for doc in self.docs),
                    "total_tokens": sum(doc["total_tokens"] for doc in self.docs),
                    "total_cache_creation_tokens": 0,
                    "total_cache_read_tokens": 0,
                    "total_duration": 0.0,
                }
            ]
        )

    def find(self, query, projection):
        return _PagingFakeCursor(self.docs)


@pytest.mark.asyncio
async def test_ensure_indexes_uses_existing_trace_id_index_name() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    await storage.ensure_indexes()

    assert collection.create_index_calls[0] == (
        "trace_id",
        {"unique": True, "name": "trace_id_unique_idx"},
    )


@pytest.mark.asyncio
async def test_upsert_usage_log_normalizes_token_numbers_and_metadata() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "agent-1",
            "started_at": "2026-06-14T00:00:00+00:00",
            "completed_at": datetime(2026, 6, 14, 0, 1, tzinfo=timezone.utc),
            "status": "completed",
            "metadata": {
                "username": "Ada",
                "agent_name": "Fast Agent",
                "step_count": "4",
                "tool_calls": None,
            },
            "events": [
                {"event_type": "token:usage", "data": {"total_tokens": "old"}},
                {
                    "event_type": "token:usage",
                    "data": {
                        "model": "openai/gpt-5",
                        "input_tokens": "10",
                        "output_tokens": 5.8,
                        "total_tokens": None,
                        "cache_creation_tokens": "2",
                        "cache_read_tokens": "3",
                        "duration": "1.25",
                    },
                },
            ],
        }
    )

    assert inserted is True
    query, update, kwargs = collection.update_calls[0]
    assert query == {
        "trace_id": "trace-1",
        "$or": [
            {"trace_event_revision": {"$exists": False}},
            {"trace_event_revision": {"$lte": 0}},
        ],
    }
    assert kwargs == {"upsert": True}
    doc = update["$set"]
    assert doc["username"] == "Ada"
    assert doc["agent_name"] == "Fast Agent"
    assert doc["model"] == "openai/gpt-5"
    assert doc["input_tokens"] == 10
    assert doc["output_tokens"] == 5
    assert doc["total_tokens"] == 15
    assert doc["cache_creation_tokens"] == 2
    assert doc["cache_read_tokens"] == 3
    assert doc["duration"] == 1.25
    assert doc["step_count"] == 4
    assert doc["tool_calls"] == 0
    assert isinstance(doc["started_at"], datetime)


@pytest.mark.asyncio
async def test_upsert_usage_log_from_trace_metadata_uses_provided_usage_data() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "agent-1",
            "started_at": "2026-06-14T00:00:00+00:00",
            "completed_at": datetime(2026, 6, 14, 0, 1, tzinfo=timezone.utc),
            "status": "completed",
            "metadata": {"username": "Ada", "agent_name": "Fast Agent"},
        },
        {
            "model": "openai/gpt-5",
            "input_tokens": "10",
            "output_tokens": 5.8,
            "duration": "1.25",
        },
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["trace_id"] == "trace-1"
    assert doc["model"] == "openai/gpt-5"
    assert doc["input_tokens"] == 10
    assert doc["output_tokens"] == 5
    assert doc["total_tokens"] == 15
    assert doc["duration"] == 1.25


@pytest.mark.asyncio
async def test_upsert_usage_log_from_trace_metadata_records_error_summary() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-err",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "started_at": "2026-06-14T00:00:00+00:00",
            "status": "error",
            "metadata": {"username": "Ada", "agent_name": "Search Agent"},
        },
        {},
        error_data={
            "error": "Error code: 429 - rate limit exceeded",
            "type": "RateLimitError",
            "run_id": "run-1",
        },
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["model"] == ""
    assert doc["error_message"].startswith("Error code: 429")
    assert doc["error_type"] == "RateLimitError"


@pytest.mark.asyncio
async def test_upsert_usage_log_from_trace_metadata_keeps_error_blank_without_error_data() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-ok",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "started_at": "2026-06-14T00:00:00+00:00",
            "status": "completed",
            "metadata": {"username": "Ada", "agent_name": "Search Agent"},
        },
        {"model": "glm-5.3", "input_tokens": 10, "output_tokens": 5},
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["model"] == "glm-5.3"
    assert doc["error_message"] == ""
    assert doc["error_type"] == ""


@pytest.mark.asyncio
async def test_list_usage_logs_builds_bounded_query_and_stats() -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    items, total, stats = await storage.list_usage_logs(
        user_id="user-1",
        model="openai/gpt-5",
        start_date="2026-06-01T00:00:00+00:00",
        end_date="2026-07-01T00:00:00+00:00",
        search="ada",
        skip=-10,
        limit=999,
    )

    assert items == [
        {
            "trace_id": "trace-1",
            "cost_available": False,
            "usage_incomplete": None,
            "cost_complete": False,
            "partial_cost_usd": None,
            "estimated_cost_usd": None,
        }
    ]
    assert total == 1
    assert stats["total_requests"] == 1
    query = collection.count_queries[0]
    assert query["user_id"] == "user-1"
    assert query["model"] == "openai/gpt-5"
    assert query["username"] == {"$regex": "ada", "$options": "i"}
    assert query["started_at"]["$gte"] == datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert query["started_at"]["$lt"] == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert collection.cursor.skip_value == 0
    assert collection.cursor.limit_value == 200


@pytest.mark.asyncio
async def test_list_usage_logs_paginates_items_but_keeps_stats_global() -> None:
    collection = _PagingFakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    items, total, stats = await storage.list_usage_logs(skip=1, limit=1)

    assert items == [
        {
            "trace_id": "trace-2",
            "input_tokens": 20,
            "output_tokens": 8,
            "total_tokens": 28,
            "cost_available": False,
            "usage_incomplete": None,
            "cost_complete": False,
            "partial_cost_usd": None,
            "estimated_cost_usd": None,
        }
    ]
    assert total == 3
    assert stats["total_requests"] == 3
    assert stats["total_input_tokens"] == 60
    assert stats["total_output_tokens"] == 25
    assert stats["total_tokens"] == 85


@pytest.mark.asyncio
async def test_upsert_usage_log_enriches_operational_metadata(monkeypatch) -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    async def fake_session_metadata(session_id):
        assert session_id == "session-1"
        return {
            "team_id": "team-1",
            "team_name": "Growth Team",
            "persona_preset_id": "persona-1",
            "persona_preset_name": "Researcher",
            "source": "scheduled_task",
            "scheduled_task_id": "task-1",
            "scheduled_task_run_id": "run-scheduled-1",
            "scheduled_task_trigger_type": "cron",
        }

    monkeypatch.setattr(storage, "_get_session_metadata", fake_session_metadata)

    inserted = await storage.upsert_usage_log(
        {
            "trace_id": "trace-ops",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "team",
            "started_at": "2026-06-14T00:00:00+00:00",
            "completed_at": "2026-06-14T00:02:00+00:00",
            "status": "completed",
            "metadata": {
                "username": "Ada",
                "agent_name": "Team Agent",
                "team_id": "team-from-trace",
                "step_count": 7,
                "tool_calls": 3,
            },
            "events": [
                {
                    "event_type": "token:usage",
                    "data": {
                        "model": "openai/gpt-5",
                        "input_tokens": 20,
                        "output_tokens": 30,
                        "duration": 120.0,
                    },
                },
            ],
        }
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["team_id"] == "team-from-trace"
    assert doc["team_name"] == "Growth Team"
    assert doc["persona_preset_id"] == "persona-1"
    assert doc["persona_preset_name"] == "Researcher"
    assert doc["source"] == "scheduled_task"
    assert doc["scheduled_task_id"] == "task-1"
    assert doc["scheduled_task_run_id"] == "run-scheduled-1"
    assert doc["scheduled_task_trigger_type"] == "cron"


@pytest.mark.asyncio
async def test_upsert_usage_log_resolves_team_name_when_missing(monkeypatch) -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    async def fake_session_metadata(session_id):
        return {"team_id": "team-1"}

    async def fake_resolve_team_name(team_id):
        assert team_id == "team-1"
        return "Ops Team"

    monkeypatch.setattr(storage, "_get_session_metadata", fake_session_metadata)
    monkeypatch.setattr(storage, "_resolve_team_name", fake_resolve_team_name)

    inserted = await storage.upsert_usage_log(
        {
            "trace_id": "trace-team",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "team",
            "started_at": "2026-06-14T00:00:00+00:00",
            "completed_at": "2026-06-14T00:02:00+00:00",
            "status": "completed",
            "metadata": {"username": "Ada", "agent_name": "Team Agent"},
            "events": [
                {
                    "event_type": "token:usage",
                    "data": {"input_tokens": 1, "output_tokens": 2},
                },
            ],
        }
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["team_id"] == "team-1"
    assert doc["team_name"] == "Ops Team"


class _DashboardFakeCollection:
    def __init__(self):
        self.aggregate_pipelines = []

    async def aggregate(self, pipeline):
        self.aggregate_pipelines.append(pipeline)
        return _FakeAggregateCursor(
            [
                {
                    "daily": [
                        {
                            "_id": "2026-06-14",
                            "requests": 2,
                            "tokens": 150,
                            "duration": 60.0,
                            "scheduled_runs": 1,
                            "tool_calls": 5,
                            "failed_requests": 1,
                            "input_tokens": 70,
                            "cache_creation_tokens": 5,
                            "cache_read_tokens": 20,
                        }
                    ],
                    "agents": [
                        {"_id": "Team Agent", "requests": 2, "tokens": 150, "duration": 60.0}
                    ],
                    "teams": [
                        {
                            "_id": "team-1",
                            "name": "Growth Team",
                            "requests": 2,
                            "tokens": 150,
                            "duration": 60.0,
                        }
                    ],
                    "personas": [
                        {
                            "_id": "persona-1",
                            "name": "Researcher",
                            "requests": 1,
                            "tokens": 80,
                            "duration": 30.0,
                        }
                    ],
                    "models": [
                        {
                            "_id": "openai/gpt-5",
                            "requests": 2,
                            "tokens": 150,
                            "duration": 60.0,
                            "input_tokens": 70,
                            "cache_creation_tokens": 5,
                            "cache_read_tokens": 20,
                            "zero_cache_requests": 1,
                        },
                        {
                            "_id": "openai/o4-mini",
                            "requests": 1,
                            "tokens": 10,
                            "duration": 2.0,
                            "input_tokens": 0,
                            "cache_creation_tokens": 0,
                            "cache_read_tokens": 0,
                            "zero_cache_requests": 1,
                        },
                    ],
                    "users": [
                        {
                            "_id": "user-1",
                            "name": "Ada",
                            "requests": 2,
                            "tokens": 150,
                            "duration": 60.0,
                        }
                    ],
                    "sources": [
                        {"_id": "scheduled_task", "requests": 1, "tokens": 90, "duration": 40.0}
                    ],
                    "triggers": [{"_id": "cron", "requests": 1, "tokens": 90, "duration": 40.0}],
                    "summary": [
                        {
                            "total_requests": 2,
                            "total_tokens": 150,
                            "total_input_tokens": 70,
                            "total_output_tokens": 80,
                            "total_cache_creation_tokens": 5,
                            "total_cache_read_tokens": 20,
                            "total_duration": 60.0,
                            "total_tool_calls": 5,
                            "scheduled_runs": 1,
                            "successful_requests": 1,
                            "failed_requests": 1,
                            "max_duration": 45.0,
                        }
                    ],
                }
            ]
        )


@pytest.mark.asyncio
async def test_get_usage_dashboard_returns_daily_and_rankings() -> None:
    collection = _DashboardFakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    dashboard = await storage.get_usage_dashboard(
        user_id="user-1",
        start_date="2026-06-01T00:00:00+00:00",
        end_date="2026-07-01T00:00:00+00:00",
    )

    assert dashboard["summary"]["total_requests"] == 2
    assert dashboard["summary"]["scheduled_runs"] == 1
    assert dashboard["summary"]["failed_requests"] == 1
    assert dashboard["summary"]["success_rate"] == 0.5
    assert dashboard["summary"]["avg_tokens_per_request"] == 75
    assert dashboard["summary"]["avg_duration_per_request"] == 30.0
    assert dashboard["summary"]["scheduled_share"] == 0.5
    assert dashboard["summary"]["cache_read_share"] == 20 / 70
    assert dashboard["summary"]["tool_calls_per_request"] == 2.5
    assert dashboard["summary"]["peak_day"]["date"] == "2026-06-14"
    assert dashboard["daily"][0]["date"] == "2026-06-14"
    assert dashboard["daily"][0]["failed_requests"] == 1
    assert dashboard["daily"][0]["cache_read_share"] == 20 / 70
    assert dashboard["top_agents"][0]["name"] == "Team Agent"
    assert dashboard["top_teams"][0]["id"] == "team-1"
    assert dashboard["top_personas"][0]["name"] == "Researcher"
    assert dashboard["top_models"][0] == {
        "id": "openai/gpt-5",
        "name": "openai/gpt-5",
        "partial_cost_usd": 0.0,
        "partial_requests": 0,
        "estimated_cost_usd": 0.0,
        "estimated_requests": 0,
        "unknown_usage_fields": [],
        "requests": 2,
        "tokens": 150,
        "duration": 60.0,
        "cost_usd": 0.0,
        "input_tokens": 70,
        "cache_creation_tokens": 5,
        "cache_read_tokens": 20,
        "cache_read_share": 20 / 70,
        "zero_cache_requests": 1,
        "priced_requests": 0,
        "unpriced_requests": 0,
        "cache_unknown_requests": 0,
        "usage_unknown_requests": 0,
    }
    assert dashboard["top_models"][1]["cache_read_share"] == 0.0
    assert dashboard["top_users"][0]["name"] == "Ada"
    assert dashboard["sources"][0]["id"] == "scheduled_task"
    assert dashboard["triggers"][0]["id"] == "cron"

    match_stage = collection.aggregate_pipelines[0][0]
    assert match_stage["$match"]["user_id"] == "user-1"
    assert match_stage["$match"]["started_at"]["$gte"] == datetime(2026, 6, 1, tzinfo=timezone.utc)
    pipeline_text = str(collection.aggregate_pipelines[0])
    assert "scheduled_task_id" in pipeline_text
    assert "cache_creation_tokens" in pipeline_text
    assert "cache_read_tokens" in pipeline_text
    assert "zero_cache_requests" in pipeline_text


class _ProviderQuirkFakeCollection:
    """provider 口径不一致：input_tokens 不含缓存 token，甚至 cache > input。"""

    async def aggregate(self, pipeline):
        return _FakeAggregateCursor(
            [
                {
                    "daily": [
                        {
                            "_id": "2026-09-03",
                            "requests": 1,
                            "input_tokens": 0,
                            "cache_creation_tokens": 12000,
                            "cache_read_tokens": 14813,
                        }
                    ],
                    "models": [
                        {
                            "_id": "anthropic/claude",
                            "requests": 1,
                            "input_tokens": 10,
                            "cache_creation_tokens": 50,
                            "cache_read_tokens": 100,
                        }
                    ],
                    "agents": [],
                    "teams": [],
                    "personas": [],
                    "users": [],
                    "sources": [],
                    "triggers": [],
                    "summary": [
                        {
                            "total_requests": 1,
                            "total_input_tokens": 10,
                            "total_cache_creation_tokens": 50,
                            "total_cache_read_tokens": 100,
                        }
                    ],
                }
            ]
        )


@pytest.mark.asyncio
async def test_dashboard_cache_share_normalizes_provider_token_semantics() -> None:
    """input 不含缓存 token 的 provider：分母取 max(input, read+write)，且 clamp ≤ 1。"""
    storage = UsageStorage()
    storage._collection = _ProviderQuirkFakeCollection()

    dashboard = await storage.get_usage_dashboard()

    # summary: eff = max(10, 100+50) = 150 → 100/150
    assert abs(dashboard["summary"]["cache_read_share"] - 100 / 150) < 1e-9
    # daily: eff = max(0, 14813+12000) = 26813 → 14813/26813（不再因 input=0 显示 0）
    assert abs(dashboard["daily"][0]["cache_read_share"] - 14813 / 26813) < 1e-9
    # ranking 与 summary 同口径
    assert abs(dashboard["top_models"][0]["cache_read_share"] - 100 / 150) < 1e-9


def test_cache_read_share_clamped_when_cache_exceeds_input() -> None:
    from src.infra.usage.storage import _cache_read_share

    # 裸除法会得到 10.0（10000%）；归一化后 clamp 到 1.0
    assert _cache_read_share(input_tokens=10, cache_read_tokens=100, cache_creation_tokens=0) == 1.0
    # 无任何 token → 0.0
    assert _cache_read_share(input_tokens=0, cache_read_tokens=0, cache_creation_tokens=0) == 0.0
    # 标准口径（input 已含缓存）：eff=input，share 不变
    assert abs(_cache_read_share(100, 30, 20) - 0.3) < 1e-9


@pytest.mark.asyncio
async def test_upsert_usage_log_from_trace_metadata_surfaces_cancel_reason() -> None:
    """取消的 run：status 照抄 cancelled，原因从 trace 元数据兜底透出。

    取消路径竞态下（API 副本先终结 trace、worker 的 error 事件后落库），
    usage 写入时可能没有 error 事件——面板必须仍显示取消原因而不是空。
    """
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-cancelled",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "started_at": "2026-06-14T00:00:00+00:00",
            "status": "cancelled",
            "metadata": {
                "username": "Ada",
                "agent_name": "Search Agent",
                "cancel_reason": "Task cancelled by user",
            },
        },
        {},
        error_data=None,
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["status"] == "cancelled"
    assert doc["error_message"] == "Task cancelled by user"
    assert doc["error_type"] == "cancelled"


@pytest.mark.asyncio
async def test_upsert_usage_log_from_trace_metadata_prefers_error_event_over_cancel_reason() -> (
    None
):
    """worker 抢先落了 error 事件（如 "Task cancelled"）时以事件原文优先。"""
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    inserted = await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-cancelled-evt",
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "started_at": "2026-06-14T00:00:00+00:00",
            "status": "cancelled",
            "metadata": {
                "username": "Ada",
                "agent_name": "Search Agent",
                "cancel_reason": "Task cancelled via pub/sub",
            },
        },
        {},
        error_data={"error": "Task cancelled", "type": "CancelledError", "run_id": "run-1"},
    )

    assert inserted is True
    doc = collection.update_calls[0][1]["$set"]
    assert doc["status"] == "cancelled"
    assert doc["error_message"] == "Task cancelled"
    assert doc["error_type"] == "CancelledError"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "error", "completed"])
@pytest.mark.parametrize("usage_model", [None, "", "fallback-model"])
async def test_usage_log_falls_back_to_run_model_without_usage_model(status, usage_model) -> None:
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection

    await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "trace-model",
            "status": status,
            "metadata": {"model": "selected-model"},
        },
        {"model": usage_model} if usage_model is not None else {},
    )

    doc = collection.update_calls[0][1]["$set"]
    assert doc["model"] == (usage_model or "selected-model")
    assert doc["total_tokens"] == 0
    assert doc["cost_available"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("starts_with_quick_handoff", [False, True])
async def test_repeated_hitl_resumes_store_one_cumulative_usage_record(
    monkeypatch, starts_with_quick_handoff
) -> None:
    from src.agents.core.node_utils import resolve_run_usage_carry
    from src.infra.agent.events.processor import AgentEventProcessor
    from src.infra.pricing.calculator import PriceRates, compute_cost
    from src.infra.task.hitl import build_hitl_resume_payload
    from src.infra.writer.present import Presenter

    rates = PriceRates(input=1, output=2, cache_read=0.1)

    async def price_usage(**kwargs):
        cost = compute_cost(
            input_tokens=kwargs["input_tokens"],
            output_tokens=kwargs["output_tokens"],
            cache_read_tokens=kwargs["cache_read_tokens"],
            rates=rates,
        )
        return cost, rates, "test"

    monkeypatch.setattr("src.infra.agent.events.processor.compute_usage_cost", price_usage)
    events = []
    presenter = Presenter()

    async def capture(event):
        events.append({"event_type": event["event"], "data": event["data"]})

    monkeypatch.setattr(presenter, "emit", capture)
    resume_payload = None
    handoff_payload = None
    for index, (input_tokens, output_tokens, cache_tokens) in enumerate(
        [(100, 10, 10), (200, 20, 20), (50, 5, 30), (0, 0, 0)]
    ):
        processor = AgentEventProcessor(presenter)
        started_at, prior = resolve_run_usage_carry(
            resume_payload, default_started_at=100.0, handoff_usage=handoff_payload
        )
        processor.seed_usage(prior)
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cache_tokens, "cache_creation": 0},
        }
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        usage_metadata=usage,
                        response_metadata={"token_usage": dict(usage)},
                    )
                },
            }
        )
        assert events[-1]["event_type"] == "token:usage"
        assert await processor.emit_token_usage(model="selected-model") is False
        assert events[-1]["data"]["total_tokens"] == [110, 330, 385, 385][index]
        if starts_with_quick_handoff and index == 0:
            handoff_payload = {
                "run_started_at": started_at,
                "prior_usage": processor.usage_totals(),
            }
            continue
        approval = SimpleNamespace(
            id=f"approval-{index}",
            message="confirm",
            metadata={
                "interrupt_id": f"interrupt-{index}",
                "resume_context": {
                    "run_started_at": started_at,
                    "prior_usage": processor.usage_totals(),
                },
            },
        )
        resume_payload = build_hitl_resume_payload(approval, {"approved": True})

    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    trace = {"trace_id": "same-trace", "status": "completed", "events": events}
    await storage.upsert_usage_log(trace)
    await storage.upsert_usage_log(trace)

    for query, update, options in collection.update_calls:
        assert query == {
            "trace_id": "same-trace",
            "$or": [
                {"trace_event_revision": {"$exists": False}},
                {"trace_event_revision": {"$lte": 0}},
            ],
        }
        assert options["upsert"] is True
        doc = update["$set"]
        assert doc["input_tokens"] == 350
        assert doc["output_tokens"] == 35
        assert doc["total_tokens"] == 385
        assert doc["cache_read_tokens"] == 60
        assert doc["cost_usd"] == pytest.approx(0.000366)


@pytest.mark.parametrize("certificate", [None, False, 1, True])
async def test_cost_snapshot_requires_inclusive_input_certificate(certificate):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    usage = {
        "input_tokens": 100,
        "output_tokens": 5,
        "total_tokens": 105,
        "cache_read_tokens": 70,
        "cache_creation_tokens": 0,
        "cost_usd": 0.9,
        "usage_incomplete": False,
        "unknown_usage_fields": [],
    }
    if certificate is not None:
        usage["input_includes_cache"] = certificate
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "raw-cost"}, usage)
    stored = collection.update_calls[0][1]["$set"]
    assert stored["cost_usd"] == 0.9
    assert stored["cost_available"] is (certificate is True)


@pytest.mark.parametrize("certificate", [None, False, 1, True])
async def test_usage_listing_does_not_recertify_legacy_cost(certificate):
    collection = _FakeCollection()
    storage = UsageStorage()
    storage._collection = collection
    doc = {
        "trace_id": "legacy-cost",
        "cost_usd": 0.9,
        "cost_available": True,
        "usage_incomplete": False,
    }
    if certificate is not None:
        doc["input_includes_cache"] = certificate
    collection.find = lambda *args, **kwargs: _FakeCursor([doc])
    [stored] = await storage._fetch_items({}, 0, 10)
    assert stored["cost_usd"] == 0.9
    assert stored["cost_available"] is (certificate is True)


def test_cache_rates_use_available_counts_despite_missing_calls() -> None:
    from src.infra.usage.formatting import _format_dashboard

    counts = {
        "input_tokens": 100,
        "cache_read_tokens": 60,
        "cache_creation_tokens": 0,
        "cache_unknown_requests": 2,
        "cache_uncertified_requests": 2,
    }
    result = _format_dashboard(
        {
            "summary": [
                {
                    "total_input_tokens": 100,
                    "total_cache_read_tokens": 60,
                    "cache_unknown_requests": 2,
                    "cache_uncertified_requests": 2,
                }
            ],
            "daily": [{"_id": "2026-10-19", **counts}],
            "models": [{"_id": "model", **counts}],
        }
    )
    assert result["summary"]["cache_read_share"] == 0.6
    assert result["daily"][0]["cache_read_share"] == 0.6
    assert result["top_models"][0]["cache_read_share"] == 0.6

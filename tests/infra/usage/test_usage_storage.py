from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.infra.usage.storage import UsageStorage


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

    def aggregate(self, pipeline):
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

    def aggregate(self, pipeline):
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
    assert query == {"trace_id": "trace-1"}
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

    assert items == [{"trace_id": "trace-1"}]
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
        {"trace_id": "trace-2", "input_tokens": 20, "output_tokens": 8, "total_tokens": 28}
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

    def aggregate(self, pipeline):
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
                        {"_id": "openai/gpt-5", "requests": 2, "tokens": 150, "duration": 60.0}
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
    assert dashboard["top_agents"][0]["name"] == "Team Agent"
    assert dashboard["top_teams"][0]["id"] == "team-1"
    assert dashboard["top_personas"][0]["name"] == "Researcher"
    assert dashboard["top_models"][0]["name"] == "openai/gpt-5"
    assert dashboard["top_users"][0]["name"] == "Ada"
    assert dashboard["sources"][0]["id"] == "scheduled_task"
    assert dashboard["triggers"][0]["id"] == "cron"

    match_stage = collection.aggregate_pipelines[0][0]
    assert match_stage["$match"]["user_id"] == "user-1"
    assert match_stage["$match"]["started_at"]["$gte"] == datetime(2026, 6, 1, tzinfo=timezone.utc)
    pipeline_text = str(collection.aggregate_pipelines[0])
    assert "scheduled_task_id" in pipeline_text

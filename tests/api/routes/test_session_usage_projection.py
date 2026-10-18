"""Display-only historical pricing must match the final owned usage snapshot."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return deepcopy(self.docs)


class _Collection:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def find(self, query, projection):
        self.queries.append(query)
        return _Cursor(
            [
                doc
                for doc in self.docs
                if all(
                    doc.get(key) in value["$in"]
                    if isinstance(value, dict) and "$in" in value
                    else doc.get(key) == value
                    for key, value in query.items()
                )
            ]
        )


def _event(**data):
    return dict(
        trace_id="trace",
        run_id="run",
        event_type="token:usage",
        seq=4,
        data=dict(
            model="model",
            model_id="config",
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            cache_read_tokens=20,
            input_includes_cache=True,
            usage_incomplete=True,
            unknown_usage_fields=["cache_creation_tokens"],
            **data,
        ),
    )


def _row(**updates):
    row = dict(
        trace_id="trace",
        run_id="run",
        session_id="session",
        user_id="owner",
        model="model",
        model_id="config",
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=0,
        input_includes_cache=True,
        usage_incomplete=True,
        unknown_usage_fields=["cache_creation_tokens"],
        cost_available=False,
        cost_usd=0.0,
        partial_cost_usd=0.25,
        status="completed",
    )
    row.update(updates)
    return row


async def _project(events, rows):
    from src.api.routes.session_usage_projection import project_session_usage_costs

    collection = _Collection(rows)
    result = await project_session_usage_costs(
        events,
        session_id="session",
        user_id="owner",
        usage_storage=SimpleNamespace(collection=collection),
    )
    return result, collection


async def test_historical_partial_backfill_is_visible_without_mutating_raw_events():
    events = [_event()]
    original = deepcopy(events)
    rows = [_row()]
    result, collection = await _project(events, rows)
    assert result[0]["data"]["partial_cost_usd"] == 0.25
    assert "cost_usd" not in result[0]["data"]
    assert result[0]["data"]["usage_incomplete"] is True
    assert result[0]["data"]["unknown_usage_fields"] == ["cache_creation_tokens"]
    assert "cache_creation_tokens" not in result[0]["data"]
    assert events == original
    assert rows == [_row()]
    assert len(collection.queries) == 1
    assert collection.queries[0]["user_id"] == "owner"
    assert collection.queries[0]["session_id"] == "session"
    assert collection.queries[0]["trace_id"] == {"$in": ["trace"]}


async def test_free_cache_write_backfill_projects_complete_cost_without_claiming_known_write_count():
    events = [_event()]
    result, _ = await _project(
        events,
        [
            _row(
                cost_complete=True,
                cost_available=True,
                cost_usd=0.0001,
                partial_cost_usd=None,
                cost_rates=dict(
                    input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True
                ),
            )
        ],
    )
    data = result[0]["data"]
    assert data["cost_usd"] == 0.0001 and data["cost_complete"] is True
    assert data["usage_incomplete"] is True
    assert data["unknown_usage_fields"] == ["cache_creation_tokens"]
    assert data["cost_rates"] == dict(
        input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True
    )
    assert "cache_creation_tokens" not in data
    assert "cost_complete" not in events[0]["data"]


async def test_confirmed_history_upgrade_replaces_old_partial_fields_and_uses_saved_rate_breakdown():
    event = _event(partial_cost_usd=0.25, partial_cost_breakdown={"output": 0.25})
    original = deepcopy(event)
    result, _ = await _project(
        [event],
        [
            _row(
                cost_complete=True,
                cost_available=True,
                cost_usd=0.0001,
                partial_cost_usd=None,
                cost_rates=dict(
                    input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True
                ),
            )
        ],
    )
    data = result[0]["data"]
    assert "partial_cost_usd" not in data and "partial_cost_breakdown" not in data
    assert "estimated_cost_usd" not in data
    assert data["cost_breakdown"] == dict(
        input=0.00008, output=0.00002, cache_read=0, cache_write=0, total=0.0001
    )
    assert event == original


@pytest.mark.parametrize(
    "updates",
    [
        {"user_id": "other"},
        {"session_id": "other"},
        {"run_id": "other"},
        {"input_tokens": 101},
        {"output_tokens": 11},
        {"total_tokens": 111},
        {"cache_read_tokens": 21},
        {"cache_creation_tokens": 1},
        {"unknown_usage_fields": []},
        {"input_includes_cache": False},
        {"input_includes_cache": 1},
        {"usage_incomplete": False},
        {"model": "other"},
        {"model_id": "other"},
    ],
)
async def test_mismatched_history_snapshot_never_receives_backfilled_cost(updates):
    events = [_event()]
    result, _ = await _project(events, [_row(**updates)])
    assert result == events


async def test_only_final_main_usage_receives_cost_and_intermediate_or_child_events_do_not():
    events = [_event(), _event(), _event(depth=1)]
    events[0]["seq"] = 1
    events[1]["seq"] = 2
    events[2]["seq"] = 3
    result, _ = await _project(events, [_row()])
    assert "partial_cost_usd" not in result[0]["data"]
    assert result[1]["data"]["partial_cost_usd"] == 0.25
    assert "partial_cost_usd" not in result[2]["data"]


async def test_legacy_history_gets_estimate_without_financial_recertification():
    event = _event(cache_creation_tokens=0)
    for key in ("usage_incomplete", "unknown_usage_fields", "input_includes_cache"):
        event["data"].pop(key)
    row = _row(cost_usd=0.75, cost_available=True, partial_cost_usd=None)
    for key in ("usage_incomplete", "unknown_usage_fields", "input_includes_cache"):
        row.pop(key)
    result, _ = await _project([event], [row])
    data = result[0]["data"]
    assert data["estimated_cost_usd"] == 0.75
    assert "cost_usd" not in data
    assert "usage_incomplete" not in data
    assert "input_includes_cache" not in data


async def test_missing_counter_equivalence_requires_both_sides_to_explicitly_mark_unknown():
    event = _event()
    event["data"].pop("unknown_usage_fields")
    result, _ = await _project([event], [_row()])
    assert result == [event]


async def test_history_pricing_uses_one_batch_for_multiple_final_trace_events():
    second = _event()
    second.update(trace_id="trace-2", run_id="run-2")
    result, collection = await _project(
        [_event(), second], [_row(), _row(trace_id="trace-2", run_id="run-2")]
    )
    assert [event["data"]["partial_cost_usd"] for event in result] == [0.25, 0.25]
    assert len(collection.queries) == 1
    assert collection.queries[0]["trace_id"] == {"$in": ["trace", "trace-2"]}


@pytest.mark.parametrize("owner", ["owner", "different-owner"])
async def test_session_history_projects_costs_only_after_session_ownership_check(
    monkeypatch, owner
):
    from src.api.routes import session as routes
    from src.infra.session import dual_writer
    from src.kernel.errors import AppError
    from src.kernel.schemas.user import TokenPayload

    events = [_event()]
    manager = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(session_id="session", user_id=owner, metadata={})
        )
    )
    monkeypatch.setattr(routes, "SessionManager", lambda: manager)
    monkeypatch.setattr(
        dual_writer,
        "get_dual_writer",
        lambda: SimpleNamespace(read_session_events=AsyncMock(return_value=events)),
    )
    projection = AsyncMock(return_value=events)
    monkeypatch.setattr(routes, "project_session_usage_costs", projection)
    kwargs = dict(
        session_id="session",
        event_types=None,
        run_id=None,
        exclude_run_id=None,
        limit=None,
        include_active_user_message=False,
        include_active_events=False,
        trace_limit=None,
        before_trace_started_at=None,
        before_trace_id=None,
        compact_message_chunks=False,
        user=TokenPayload(sub="owner", username="Owner", permissions=["chat:read"]),
    )
    if owner == "owner":
        response = await routes.get_session_events(**kwargs)
        assert response["events"] == events
        projection.assert_awaited_once_with(events, session_id="session", user_id="owner")
    else:
        with pytest.raises(AppError):
            await routes.get_session_events(**kwargs)
        projection.assert_not_awaited()

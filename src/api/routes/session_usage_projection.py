"""Read-only billing projection for an already authorized session history page."""

from typing import Any

from src.infra.logging import get_logger
from src.infra.pricing.calculator import PriceRates, compute_cost
from src.infra.usage.cost_certainty import _usage_cost_fields
from src.infra.usage.counter_availability import TOKEN_FIELDS
from src.infra.usage.storage import get_usage_storage

logger = get_logger(__name__)
HISTORY_USAGE_BATCH_SIZE = 200


def _literal_boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _snapshot_matches(event: dict[str, Any], row: dict[str, Any]) -> bool:
    data = event["data"]
    if event.get("run_id") and row.get("run_id") and event["run_id"] != row["run_id"]:
        return False
    for key in ("model", "model_id"):
        if data.get(key) and data[key] != row.get(key):
            return False
    if (data.get("input_includes_cache") is True) != (row.get("input_includes_cache") is True):
        return False
    if _literal_boolean(data.get("usage_incomplete")) is not _literal_boolean(
        row.get("usage_incomplete")
    ):
        return False
    left_unknown = data.get("unknown_usage_fields")
    right_unknown = row.get("unknown_usage_fields")
    if (left_unknown is not None and not isinstance(left_unknown, list)) or (
        right_unknown is not None and not isinstance(right_unknown, list)
    ):
        return False
    left_unknown = left_unknown if isinstance(left_unknown, list) else []
    right_unknown = right_unknown if isinstance(right_unknown, list) else []
    if any(
        not isinstance(field, str) or field not in TOKEN_FIELDS
        for field in [*left_unknown, *right_unknown]
    ):
        return False
    if set(left_unknown) != set(right_unknown):
        return False
    for field in TOKEN_FIELDS:
        left, right = data.get(field), row.get(field)
        if field in left_unknown and field in right_unknown:
            left = 0 if left is None else left
            right = 0 if right is None else right
        if (
            not isinstance(left, int)
            or isinstance(left, bool)
            or left < 0
            or not isinstance(right, int)
            or isinstance(right, bool)
            or right < 0
            or left != right
        ):
            return False
    return True


def _saved_cost_breakdown(row: dict[str, Any]) -> dict[str, float] | None:
    snapshot = row.get("cost_rates")
    if not isinstance(snapshot, dict):
        return None
    unknown = row.get("unknown_usage_fields")
    unknown = unknown if isinstance(unknown, list) else []
    cost = compute_cost(
        **{
            field: None if field in unknown else row.get(field)
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
            )
        },
        rates=PriceRates(
            input=snapshot.get("input"),
            output=snapshot.get("output"),
            cache_read=snapshot.get("cache_read"),
            cache_write=snapshot.get("cache_write"),
            cache_write_included=snapshot.get("cache_write_included") is True,
        ),
    )
    return cost.to_event_data() if cost is not None and cost.total_usd == row["cost_usd"] else None


async def project_session_usage_costs(
    events: list[dict[str, Any]],
    *,
    session_id: str,
    user_id: str | None,
    usage_storage=None,
) -> list[dict[str, Any]]:
    final_usage: dict[str, int] = {}
    for index, event in enumerate(events):
        data = event.get("data")
        trace_id = event.get("trace_id")
        if (
            event.get("event_type") == "token:usage"
            and isinstance(trace_id, str)
            and trace_id
            and isinstance(data, dict)
            and data.get("depth") in (None, 0)
            and not data.get("subagent_id")
        ):
            final_usage[trace_id] = index
    if not final_usage or not session_id or not user_id:
        return events
    storage = usage_storage or get_usage_storage()
    trace_ids = list(final_usage)
    rows = []
    try:
        for offset in range(0, len(trace_ids), HISTORY_USAGE_BATCH_SIZE):
            rows.extend(
                await storage.collection.find(
                    {
                        "trace_id": {"$in": trace_ids[offset : offset + HISTORY_USAGE_BATCH_SIZE]},
                        "session_id": session_id,
                        "user_id": user_id,
                    },
                    {
                        "_id": 0,
                        **{
                            key: 1
                            for key in (
                                *TOKEN_FIELDS,
                                "trace_id",
                                "run_id",
                                "session_id",
                                "user_id",
                                "status",
                                "model",
                                "model_id",
                                "usage_incomplete",
                                "unknown_usage_fields",
                                "input_includes_cache",
                                "cost_available",
                                "cost_complete",
                                "cost_rates",
                                "cost_usd",
                                "partial_cost_usd",
                            )
                        },
                    },
                ).to_list(length=HISTORY_USAGE_BATCH_SIZE)
            )
    except Exception as error:
        logger.warning("History usage projection failed: %s", type(error).__name__)
        return events
    projected = list(events)
    for row in rows:
        matched_index = final_usage.get(row.get("trace_id"))
        if (
            matched_index is None
            or row.get("user_id") != user_id
            or row.get("session_id") != session_id
            or row.get("status") == "running"
            or not _snapshot_matches(events[matched_index], row)
        ):
            continue
        classified = _usage_cost_fields(row)
        money = {}
        if classified["cost_available"]:
            money["cost_usd"] = row["cost_usd"]
            if classified["cost_complete"]:
                money["cost_complete"] = True
            breakdown = _saved_cost_breakdown(row)
            if breakdown is not None:
                money["cost_breakdown"] = breakdown
        elif classified["partial_cost_usd"] is not None:
            money["partial_cost_usd"] = classified["partial_cost_usd"]
        elif classified["estimated_cost_usd"] is not None:
            money["estimated_cost_usd"] = classified["estimated_cost_usd"]
        if not money:
            continue
        if isinstance(row.get("cost_rates"), dict):
            money["cost_rates"] = dict(row["cost_rates"])
        data = {
            key: value
            for key, value in events[matched_index]["data"].items()
            if key
            not in (
                "cost_usd",
                "cost_complete",
                "cost_rates",
                "cost_breakdown",
                "partial_cost_usd",
                "partial_cost_breakdown",
                "estimated_cost_usd",
            )
        }
        projected[matched_index] = {**events[matched_index], "data": {**data, **money}}
    return projected

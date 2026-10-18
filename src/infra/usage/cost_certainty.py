"""Shared Python and MongoDB guards for separate billing certainty categories."""

from math import isfinite
from sys import float_info
from typing import Any, TypeGuard

from src.infra.usage.counter_availability import (
    TOKEN_FIELDS,
    _boolean_condition,
    _valid_counter_condition,
)

REQUIRED_COST_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens")


def _known_counter_condition(field: str) -> dict[str, Any]:
    return {
        "$and": [
            _valid_counter_condition(field),
            {
                "$not": [
                    {
                        "$in": [
                            field,
                            {
                                "$cond": [
                                    {"$isArray": "$unknown_usage_fields"},
                                    "$unknown_usage_fields",
                                    [],
                                ]
                            },
                        ]
                    }
                ]
            },
        ]
    }


def _amount_condition(field: str) -> dict[str, Any]:
    return {
        "$and": [
            {"$in": [{"$type": f"${field}"}, ["int", "long", "double"]]},
            {"$gte": [f"${field}", 0]},
            {"$lte": [f"${field}", float_info.max]},
        ]
    }


def _valid_cost(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= float_info.max
        and isfinite(value)
    )


def _has_complete_cost_receipt(doc: dict[str, Any]) -> bool:
    if doc.get("cost_source") == "provider_settlement":
        return (
            doc.get("cost_complete") is True
            and type(doc.get("cost_units")) is int
            and doc["cost_units"] >= 0
            and _valid_cost(doc.get("cost_usd"))
            and doc["cost_usd"] == doc["cost_units"] / 1_000_000_000
        )
    if (
        doc.get("cost_complete") is not True
        or doc.get("input_includes_cache") is not True
        or not _valid_cost(doc.get("cost_usd"))
    ):
        return False
    unknown = doc.get("unknown_usage_fields")
    unknown = unknown if isinstance(unknown, list) else []

    def known(field):
        value = doc.get(field)
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            and field not in unknown
        )

    if not all(known(field) for field in REQUIRED_COST_FIELDS):
        return False
    if doc["cache_read_tokens"] > doc["input_tokens"]:
        return False
    rates = doc.get("cost_rates")
    valid_included_policy = (
        isinstance(rates, dict)
        and rates.get("cache_write_included") is True
        and (
            rates.get("cache_write") is None
            or _valid_cost(rates.get("cache_write"))
            and rates["cache_write"] == 0
        )
    )
    if (
        isinstance(rates, dict)
        and rates.get("cache_write_included") is True
        and not valid_included_policy
    ):
        return False
    if known("cache_creation_tokens"):
        return doc["cache_read_tokens"] + doc["cache_creation_tokens"] <= doc["input_tokens"]
    return valid_included_policy


def _usage_cost_fields(doc: dict[str, Any]) -> dict[str, Any]:
    complete = _has_complete_cost_receipt(doc)
    if doc.get("cost_source") == "provider_settlement":
        units = doc.get("cost_units")
        return {
            "cost_available": complete,
            "cost_complete": complete,
            "partial_cost_usd": units / 1_000_000_000
            if not complete and type(units) is int and units >= 0
            else None,
            "estimated_cost_usd": None,
        }
    confirmed = (
        doc.get("cost_available") is True
        and (doc.get("usage_incomplete") is False or complete)
        and doc.get("input_includes_cache") is True
        and _valid_cost(doc.get("cost_usd"))
    )
    partial = doc.get("partial_cost_usd")
    partial = (
        float(partial)
        if not confirmed and doc.get("input_includes_cache") is True and _valid_cost(partial)
        else None
    )
    raw_cost = doc.get("cost_usd")
    estimate = (
        float(raw_cost)
        if not confirmed
        and partial is None
        and doc.get("cost_available") is True
        and _valid_cost(raw_cost)
        else None
    )
    return {
        "cost_available": confirmed,
        "cost_complete": complete,
        "partial_cost_usd": partial,
        "estimated_cost_usd": estimate,
    }


def _usage_snapshot_query(trace_id: str, expected: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {
        "trace_id": trace_id,
        "cost_source": {"$ne": "provider_settlement"},
        "input_includes_cache": {"$eq": True, "$type": "bool"},
    }
    for key in (
        *TOKEN_FIELDS,
        "model",
        "model_id",
        "unknown_usage_fields",
        "trace_event_revision",
        "usage_incomplete",
        "cost_available",
        "cost_complete",
        "partial_cost_usd",
        "cost_usd",
        "cost_rates",
    ):
        query[key] = (
            expected[key]
            if key in expected and expected[key] is not None
            else {"$eq": None, "$exists": True}
            if key in expected
            else {"$exists": False}
        )
    return query


COMPLETE_USAGE_CONDITION = _boolean_condition("usage_incomplete", False)
FREE_WRITE_RATE_CONDITION = {
    "$or": [
        {"$eq": [{"$ifNull": ["$cost_rates.cache_write", None]}, None]},
        {
            "$and": [
                _amount_condition("cost_rates.cache_write"),
                {"$eq": ["$cost_rates.cache_write", 0]},
            ]
        },
    ]
}
COMPLETE_COST_CONDITION = {
    "$and": [
        _boolean_condition("cost_complete", True),
        *[_known_counter_condition(field) for field in REQUIRED_COST_FIELDS],
        {"$lte": ["$cache_read_tokens", "$input_tokens"]},
        {
            "$or": [
                {"$not": [_boolean_condition("cost_rates.cache_write_included", True)]},
                FREE_WRITE_RATE_CONDITION,
            ]
        },
        {
            "$or": [
                {
                    "$and": [
                        _known_counter_condition("cache_creation_tokens"),
                        {
                            "$cond": [
                                {
                                    "$and": [
                                        _valid_counter_condition("cache_read_tokens"),
                                        _valid_counter_condition("cache_creation_tokens"),
                                    ]
                                },
                                {
                                    "$lte": [
                                        {"$add": ["$cache_read_tokens", "$cache_creation_tokens"]},
                                        "$input_tokens",
                                    ]
                                },
                                False,
                            ]
                        },
                    ]
                },
                {
                    "$and": [
                        {"$not": [_known_counter_condition("cache_creation_tokens")]},
                        _boolean_condition("cost_rates.cache_write_included", True),
                        FREE_WRITE_RATE_CONDITION,
                    ]
                },
            ]
        },
    ]
}
PRICED_USAGE_CONDITION = {
    "$and": [
        _boolean_condition("cost_available", True),
        {"$or": [COMPLETE_USAGE_CONDITION, COMPLETE_COST_CONDITION]},
        _boolean_condition("input_includes_cache", True),
        _amount_condition("cost_usd"),
    ]
}
SETTLEMENT_CONDITION = {
    "$and": [
        {"$eq": [{"$ifNull": ["$cost_source", None]}, "provider_settlement"]},
        {"$in": [{"$type": "$cost_units"}, ["int", "long"]]},
        {"$gte": ["$cost_units", 0]},
    ]
}
PRICED_USAGE_CONDITION = {
    "$or": [
        {
            "$and": [
                SETTLEMENT_CONDITION,
                _boolean_condition("cost_complete", True),
                _amount_condition("cost_usd"),
                {
                    "$cond": [
                        SETTLEMENT_CONDITION,
                        {"$eq": ["$cost_usd", {"$divide": ["$cost_units", 1_000_000_000]}]},
                        False,
                    ]
                },
            ]
        },
        {
            "$and": [
                {"$ne": [{"$ifNull": ["$cost_source", None]}, "provider_settlement"]},
                PRICED_USAGE_CONDITION,
            ]
        },
    ]
}
PARTIAL_USAGE_CONDITION = {
    "$and": [
        {"$not": [PRICED_USAGE_CONDITION]},
        {"$or": [SETTLEMENT_CONDITION, _boolean_condition("input_includes_cache", True)]},
        _amount_condition("partial_cost_usd"),
    ]
}
ESTIMATED_USAGE_CONDITION = {
    "$and": [
        {"$not": [PRICED_USAGE_CONDITION]},
        {"$not": [PARTIAL_USAGE_CONDITION]},
        _boolean_condition("cost_available", True),
        _amount_condition("cost_usd"),
    ]
}


def _cost_certainty_aggregates() -> dict[str, Any]:
    return {
        "partial_cost_usd": {"$sum": {"$cond": [PARTIAL_USAGE_CONDITION, "$partial_cost_usd", 0]}},
        "partial_requests": {"$sum": {"$cond": [PARTIAL_USAGE_CONDITION, 1, 0]}},
        "estimated_cost_usd": {"$sum": {"$cond": [ESTIMATED_USAGE_CONDITION, "$cost_usd", 0]}},
        "estimated_requests": {"$sum": {"$cond": [ESTIMATED_USAGE_CONDITION, 1, 0]}},
    }

"""Aggregate reported token availability independently of billing certification."""

from typing import Any

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)


def _boolean_condition(field: str, value: bool) -> dict[str, Any]:
    return {"$and": [{"$eq": [{"$type": f"${field}"}, "bool"]}, {"$eq": [f"${field}", value]}]}


def _valid_counter_condition(field: str) -> dict[str, Any]:
    return {
        "$and": [
            {"$in": [{"$type": f"${field}"}, ["int", "long"]]},
            {"$gte": [f"${field}", 0]},
        ]
    }


def _token_sum(field: str) -> dict[str, Any]:
    return {"$sum": {"$cond": [_valid_counter_condition(field), f"${field}", 0]}}


def _counter_availability_aggregates() -> dict[str, Any]:
    unknown_fields = {
        "$cond": [
            {"$isArray": "$unknown_usage_fields"},
            "$unknown_usage_fields",
            [],
        ]
    }
    unspecified_incomplete = {
        "$and": [
            _boolean_condition("usage_incomplete", True),
            {"$eq": [{"$size": unknown_fields}, 0]},
        ]
    }
    return {
        f"unreported_{field}_requests": {
            "$sum": {
                "$cond": [
                    {
                        "$and": [
                            _valid_counter_condition(field),
                            {"$not": [{"$in": [field, unknown_fields]}]},
                            {"$not": [unspecified_incomplete]},
                        ]
                    },
                    0,
                    1,
                ]
            }
        }
        for field in TOKEN_FIELDS
    }

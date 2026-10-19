"""Normalize usage aggregation results for API responses."""

from typing import Any, Dict

from src.infra.usage.counter_availability import TOKEN_FIELDS


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(float(value)), 0)
        except ValueError:
            return 0
    return 0


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str):
        try:
            return max(float(value), 0.0)
        except ValueError:
            return 0.0
    return 0.0


def _format_cost_certainty(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "partial_cost_usd": _as_float(doc.get("partial_cost_usd")),
        "partial_requests": _as_int(doc.get("partial_requests")),
        "estimated_cost_usd": _as_float(doc.get("estimated_cost_usd")),
        "estimated_requests": _as_int(doc.get("estimated_requests")),
    }


def _format_counter_availability(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "unknown_usage_fields": [
            field for field in TOKEN_FIELDS if _as_int(doc.get(f"unreported_{field}_requests")) > 0
        ]
    }


def _empty_stats() -> Dict[str, Any]:
    return {
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_duration": 0.0,
        "total_cost_usd": 0.0,
        **_format_cost_certainty({}),
        **_format_counter_availability({}),
        "unpriced_requests": 0,
        "priced_requests": 0,
        "usage_unknown_requests": 0,
        "cache_unknown_requests": 0,
    }


def _aggregate_cache_unknown_requests(
    doc: Dict[str, Any], cache_read_field: str = "cache_read_tokens"
) -> int:
    # Positive rates require inclusive input accounting for every contributing request.
    field = (
        "cache_uncertified_requests"
        if _as_int(doc.get(cache_read_field)) > 0
        else "cache_unknown_requests"
    )
    return _as_int(doc.get(field, doc.get("cache_unknown_requests")))


def _cache_read_share(
    input_tokens: int, cache_read_tokens: int, cache_creation_tokens: int
) -> float:
    """缓存命中率：分母取 max(input, cache_read+cache_creation)。

    provider 口径不一：部分（如 Anthropic 协议）的 input_tokens 不含缓存 token，
    裸除法会低估甚至除零；统一取两者较大值，并把结果 clamp 到 ≤1。
    """
    effective_input = max(input_tokens, cache_read_tokens + cache_creation_tokens)
    if effective_input <= 0:
        return 0.0
    return min(cache_read_tokens / effective_input, 1.0)


def _format_ranking_item(doc: Dict[str, Any]) -> Dict[str, Any]:
    item_id = str(doc.get("_id") or "")
    input_tokens = _as_int(doc.get("input_tokens"))
    cache_read_tokens = _as_int(doc.get("cache_read_tokens"))
    cache_creation_tokens = _as_int(doc.get("cache_creation_tokens"))
    return {
        "id": item_id,
        "name": str(doc.get("name") or item_id or "Unknown"),
        "requests": _as_int(doc.get("requests")),
        "tokens": _as_int(doc.get("tokens")),
        "duration": _as_float(doc.get("duration")),
        "cost_usd": _as_float(doc.get("cost_usd")),
        **_format_cost_certainty(doc),
        **_format_counter_availability(doc),
        "priced_requests": _as_int(doc.get("priced_requests")),
        "unpriced_requests": _as_int(doc.get("unpriced_requests")),
        "usage_unknown_requests": _as_int(doc.get("usage_unknown_requests")),
        "cache_unknown_requests": _aggregate_cache_unknown_requests(doc),
        "input_tokens": input_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_read_share": _cache_read_share(
            input_tokens, cache_read_tokens, cache_creation_tokens
        ),
        "zero_cache_requests": _as_int(doc.get("zero_cache_requests")),
    }


def _format_dashboard(doc: Dict[str, Any]) -> Dict[str, Any]:
    summary_doc = (doc.get("summary") or [{}])[0] if isinstance(doc.get("summary"), list) else {}
    total_requests = _as_int(summary_doc.get("total_requests"))
    successful_requests = _as_int(summary_doc.get("successful_requests"))
    total_tokens = _as_int(summary_doc.get("total_tokens"))
    total_input_tokens = _as_int(summary_doc.get("total_input_tokens"))
    total_cache_read_tokens = _as_int(summary_doc.get("total_cache_read_tokens"))
    total_cache_creation_tokens = _as_int(summary_doc.get("total_cache_creation_tokens"))
    total_duration = _as_float(summary_doc.get("total_duration"))
    scheduled_runs = _as_int(summary_doc.get("scheduled_runs"))
    total_tool_calls = _as_int(summary_doc.get("total_tool_calls"))
    failed_requests = _as_int(summary_doc.get("failed_requests"))
    cancelled_requests = _as_int(summary_doc.get("cancelled_requests"))
    daily_items = [
        {
            "date": str(item.get("_id") or ""),
            "requests": _as_int(item.get("requests")),
            "tokens": _as_int(item.get("tokens")),
            "duration": _as_float(item.get("duration")),
            "cost_usd": _as_float(item.get("cost_usd")),
            **_format_cost_certainty(item),
            **_format_counter_availability(item),
            "priced_requests": _as_int(item.get("priced_requests")),
            "unpriced_requests": _as_int(item.get("unpriced_requests")),
            "usage_unknown_requests": _as_int(item.get("usage_unknown_requests")),
            "cache_unknown_requests": _aggregate_cache_unknown_requests(item),
            "scheduled_runs": _as_int(item.get("scheduled_runs")),
            "cancelled_requests": _as_int(item.get("cancelled_requests")),
            "failed_requests": _as_int(item.get("failed_requests")),
            "tool_calls": _as_int(item.get("tool_calls")),
            "input_tokens": _as_int(item.get("input_tokens")),
            "cache_creation_tokens": _as_int(item.get("cache_creation_tokens")),
            "cache_read_tokens": _as_int(item.get("cache_read_tokens")),
            "cache_read_share": _cache_read_share(
                _as_int(item.get("input_tokens")),
                _as_int(item.get("cache_read_tokens")),
                _as_int(item.get("cache_creation_tokens")),
            ),
        }
        for item in doc.get("daily", [])
        if item.get("_id")
    ]
    peak_day = max(
        daily_items,
        key=lambda item: (item["tokens"], item["requests"], item["duration"]),
        default=None,
    )
    summary = {
        "total_requests": total_requests,
        "priced_requests": _as_int(summary_doc.get("priced_requests")),
        "usage_unknown_requests": _as_int(summary_doc.get("usage_unknown_requests")),
        "cache_unknown_requests": _aggregate_cache_unknown_requests(
            summary_doc, "total_cache_read_tokens"
        ),
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": _as_int(summary_doc.get("total_output_tokens")),
        "total_cache_read_tokens": total_cache_read_tokens,
        "total_duration": total_duration,
        "total_tool_calls": total_tool_calls,
        "total_cost_usd": _as_float(summary_doc.get("total_cost_usd")),
        **_format_cost_certainty(summary_doc),
        **_format_counter_availability(summary_doc),
        "unpriced_requests": _as_int(summary_doc.get("unpriced_requests")),
        "scheduled_runs": scheduled_runs,
        "failed_requests": failed_requests,
        "cancelled_requests": cancelled_requests,
        "success_rate": (successful_requests / total_requests) if total_requests else 0.0,
        "avg_tokens_per_request": (total_tokens / total_requests) if total_requests else 0.0,
        "avg_duration_per_request": (total_duration / total_requests) if total_requests else 0.0,
        "scheduled_share": (scheduled_runs / total_requests) if total_requests else 0.0,
        "cache_read_share": _cache_read_share(
            total_input_tokens, total_cache_read_tokens, total_cache_creation_tokens
        ),
        "tool_calls_per_request": ((total_tool_calls / total_requests) if total_requests else 0.0),
        "max_duration": _as_float(summary_doc.get("max_duration")),
        "peak_day": peak_day,
    }
    return {
        "summary": summary,
        "daily": daily_items,
        "top_agents": [_format_ranking_item(item) for item in doc.get("agents", [])],
        "top_teams": [_format_ranking_item(item) for item in doc.get("teams", [])],
        "top_personas": [_format_ranking_item(item) for item in doc.get("personas", [])],
        "top_models": [_format_ranking_item(item) for item in doc.get("models", [])],
        "top_users": [_format_ranking_item(item) for item in doc.get("users", [])],
        "sources": [_format_ranking_item(item) for item in doc.get("sources", [])],
        "triggers": [_format_ranking_item(item) for item in doc.get("triggers", [])],
    }


def _empty_dashboard() -> Dict[str, Any]:
    return {
        "summary": {
            "total_requests": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_duration": 0.0,
            "total_tool_calls": 0,
            "total_cost_usd": 0.0,
            **_format_cost_certainty({}),
            **_format_counter_availability({}),
            "unpriced_requests": 0,
            "priced_requests": 0,
            "cache_unknown_requests": 0,
            "usage_unknown_requests": 0,
            "scheduled_runs": 0,
            "failed_requests": 0,
            "cancelled_requests": 0,
            "success_rate": 0.0,
            "avg_tokens_per_request": 0.0,
            "avg_duration_per_request": 0.0,
            "scheduled_share": 0.0,
            "cache_read_share": 0.0,
            "tool_calls_per_request": 0.0,
            "max_duration": 0.0,
            "peak_day": None,
        },
        "daily": [],
        "top_agents": [],
        "top_teams": [],
        "top_personas": [],
        "top_models": [],
        "top_users": [],
        "sources": [],
        "triggers": [],
    }

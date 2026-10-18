"""Run-scoped execution identity without changing the user's selected agent."""

from typing import Any


def get_run_handoff(metadata: dict[str, Any]) -> dict[str, Any]:
    handoff = metadata.get("agent_handoff")
    if (
        isinstance(handoff, dict)
        and handoff.get("run_id") == metadata.get("current_run_id")
        and handoff.get("run_id")
        and handoff.get("agent_id") == "search"
        and metadata.get("agent_id") == "quick"
    ):
        return handoff
    return {}


def resolve_execution_agent_id(metadata: dict[str, Any]) -> str:
    return str(get_run_handoff(metadata).get("agent_id") or metadata.get("agent_id") or "search")


def restore_handoff_usage(handoff: dict[str, Any], latest_usage: dict[str, Any]) -> dict[str, Any]:
    """A recovered run already has its original request; retain cumulative usage, not its message ID."""
    prior = handoff.get("prior_usage") or {}
    counters: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
    ):
        values = [
            value for value in (prior.get(key), latest_usage.get(key)) if isinstance(value, int)
        ]
        if values:
            counters[key] = max(values)
    sources = [
        source
        for source in (prior, latest_usage)
        if any(isinstance(source.get(key), int) for key in counters)
    ]
    if any("unknown_usage_fields" in source for source in sources):
        unknown: set[str] = set()
        for source in sources:
            fields = source.get("unknown_usage_fields")
            if isinstance(fields, list) and all(
                isinstance(key, str) and key in counters for key in fields
            ):
                unknown.update(fields)
            else:
                unknown.update(counters)
        counters["unknown_usage_fields"] = sorted(unknown)
        counters["usage_observed"] = True
    if sources and all(source.get("input_includes_cache") is True for source in sources):
        counters["input_includes_cache"] = True
    settlements = [
        source
        for source in (prior, latest_usage)
        if source.get("cost_source") == "provider_settlement"
    ]
    if settlements:
        latest = settlements[-1]
        for key in (
            "cost_source",
            "cost_units",
            "cost_receipts",
            "legacy_cost_units",
            "legacy_cost_unknown",
            "legacy_actual_models",
            "legacy_model_identity_complete",
            "model_identity_complete",
            "actual_models",
        ):
            if key in latest:
                counters[key] = latest[key]
        if all("cost_receipts" in source for source in settlements):
            receipts: dict[str, dict[str, Any]] = {}
            for source in settlements:
                for call_id, receipt in source["cost_receipts"].items():
                    previous = receipts.get(call_id)
                    if previous is None or previous["unknown"]:
                        receipts[call_id] = dict(receipt)
                        if previous is not None and receipt["unknown"]:
                            receipts[call_id]["charged_units"] = max(
                                previous["charged_units"], receipt["charged_units"]
                            )
            counters["cost_receipts"] = receipts
    return {"run_started_at": handoff.get("run_started_at"), "prior_usage": counters}

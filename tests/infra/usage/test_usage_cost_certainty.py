"""Keep historical estimates and independently priced usage visible without certification."""

from types import SimpleNamespace

import pytest

from src.infra.usage.formatting import _empty_dashboard, _empty_stats, _format_dashboard
from src.infra.usage.storage import UsageStorage
from src.kernel.schemas.usage import UsageDashboardResponse, UsageLog, UsageStats


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    def skip(self, *args):
        return self

    def limit(self, *args):
        return self

    async def to_list(self, **kwargs):
        return self.docs


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.updates = []

    def find(self, *args):
        return _Cursor(self.docs)

    async def update_one(self, query, update, **kwargs):
        self.updates.append(update["$set"])
        return SimpleNamespace(modified_count=1)


@pytest.mark.parametrize("certificate", [None, False, 1, True])
async def test_legacy_cost_is_exposed_as_estimate_before_certificate_normalization(certificate):
    raw = {"trace_id": "old", "cost_usd": 3.5, "cost_available": True}
    if certificate is not None:
        raw["input_includes_cache"] = certificate
    collection = _Collection([raw.copy()])
    storage = UsageStorage()
    storage._collection = collection
    [item] = await storage._fetch_items({}, 0, 10)
    assert item["cost_available"] is False
    assert item["estimated_cost_usd"] == 3.5
    assert item["partial_cost_usd"] is None
    assert collection.updates == []


@pytest.mark.parametrize("certificate", [None, False, 1, True])
async def test_partial_cost_persists_only_with_literal_inclusive_certificate(certificate):
    storage = UsageStorage()
    storage._collection = _Collection()
    assert await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "partial"},
        {
            "input_tokens": 100,
            "output_tokens": 10,
            "cache_read_tokens": 20,
            "unknown_usage_fields": ["cache_creation_tokens"],
            "input_includes_cache": certificate,
            "partial_cost_usd": 0.25,
        },
    )
    [doc] = storage._collection.updates
    assert doc["cost_available"] is False
    assert doc["partial_cost_usd"] == (0.25 if certificate is True else None)


@pytest.mark.parametrize("amount", [True, -1, float("nan"), float("inf"), "0.5"])
async def test_partial_cost_rejects_invalid_amounts(amount):
    storage = UsageStorage()
    storage._collection = _Collection()
    await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "invalid-partial"},
        {"partial_cost_usd": amount, "input_includes_cache": True},
    )
    assert storage._collection.updates[0]["partial_cost_usd"] is None


@pytest.mark.parametrize("amount", [True, -1, float("nan"), float("inf"), "0.5"])
async def test_invalid_cost_amount_never_receives_confirmed_storage_or_listing_status(amount):
    storage = UsageStorage()
    collection = _Collection()
    storage._collection = collection
    await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "invalid-confirmed"},
        dict(
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            usage_incomplete=False,
            unknown_usage_fields=[],
            input_includes_cache=True,
            cost_usd=amount,
        ),
    )
    assert collection.updates[0]["cost_available"] is False
    collection.docs = [
        dict(
            trace_id="legacy-invalid",
            cost_usd=amount,
            cost_available=True,
            usage_incomplete=False,
            input_includes_cache=True,
        )
    ]
    [item] = await storage._fetch_items({}, 0, 10)
    assert item["cost_available"] is False


def test_api_schemas_preserve_separate_cost_certainties():
    item = UsageLog.model_validate(
        dict(
            trace_id="legacy",
            session_id="s",
            user_id="u",
            estimated_cost_usd=2.5,
            partial_cost_usd=0.25,
        )
    ).model_dump()
    assert item["estimated_cost_usd"] == 2.5
    assert item["partial_cost_usd"] == 0.25
    stats = UsageStats.model_validate(
        dict(
            partial_cost_usd=0.25, partial_requests=1, estimated_cost_usd=2.5, estimated_requests=2
        )
    ).model_dump()
    assert stats["partial_cost_usd"] == 0.25
    assert stats["estimated_requests"] == 2


def test_every_dashboard_surface_retains_partial_and_estimated_amounts():
    amounts = dict(
        partial_cost_usd=0.25, partial_requests=1, estimated_cost_usd=2.5, estimated_requests=2
    )
    doc = {
        "summary": [amounts],
        "daily": [dict(amounts, _id="2026-10-18")],
        "models": [dict(amounts, _id="model")],
    }
    dashboard = UsageDashboardResponse.model_validate(_format_dashboard(doc)).model_dump()
    for surface in (dashboard["summary"], dashboard["daily"][0], dashboard["top_models"][0]):
        for key, value in amounts.items():
            assert surface[key] == value
    for surface in (_empty_stats(), _empty_dashboard()["summary"]):
        for key in amounts:
            assert surface[key] == 0

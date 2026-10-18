"""A missing historical completeness certificate is distinct from explicit incomplete usage."""

from copy import deepcopy

import pytest

from src.infra.usage.storage import UsageStorage
from src.kernel.schemas.usage import UsageLog


class _Cursor:
    def __init__(self, doc):
        self.doc = doc

    def sort(self, *args):
        return self

    def skip(self, *args):
        return self

    def limit(self, *args):
        return self

    async def to_list(self, length):
        return [deepcopy(self.doc)]


@pytest.mark.parametrize("raw", [None, 0, 1, True, False])
async def test_listing_preserves_only_literal_boolean_usage_completeness(raw):
    doc = dict(
        trace_id="legacy",
        session_id="s",
        user_id="owner",
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=1.0,
        cost_available=True,
        input_includes_cache=True,
    )
    if raw is not None:
        doc["usage_incomplete"] = raw
    storage = UsageStorage()
    storage._collection = type("Collection", (), {"find": lambda *_: _Cursor(doc)})()
    [item] = await storage._fetch_items({}, 0, 1)
    payload = UsageLog.model_validate(item).model_dump()
    assert payload["usage_incomplete"] is (raw if isinstance(raw, bool) else None)
    assert payload["cost_available"] is (raw is False)
    assert payload["input_tokens"] == 100


def test_usage_log_schema_defaults_legacy_completeness_to_none():
    payload = UsageLog(trace_id="legacy", session_id="s", user_id="owner").model_dump()
    assert payload["usage_incomplete"] is None

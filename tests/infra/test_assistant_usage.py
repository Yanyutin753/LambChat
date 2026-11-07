"""Assistant attribution must retain unknown costs and isolate owners."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.usage.storage import UsageStorage


async def test_object_id_session_metadata_is_available_for_assistant_attribution(monkeypatch):
    from src.infra.session.storage import SessionStorage

    collection = SimpleNamespace(
        find_one=AsyncMock(
            side_effect=[None, {"user_id": "owner", "metadata": {"assistant_id": "helper"}}]
        )
    )
    monkeypatch.setattr(SessionStorage, "collection", property(lambda _: collection))
    assert await UsageStorage()._get_session_metadata(
        "123456789012345678901234", user_id="owner"
    ) == {"assistant_id": "helper"}
    collection.find_one.side_effect = None
    collection.find_one.return_value = {
        "user_id": "foreign",
        "metadata": {"assistant_id": "private"},
    }
    assert await UsageStorage()._get_session_metadata("custom", user_id="owner") == {}


async def test_assistant_filter_keeps_unknown_usage_in_existing_aggregates():
    storage = UsageStorage()
    storage._count_and_stats = AsyncMock(
        return_value=(
            1,
            {"usage_unknown_requests": 1, "unpriced_requests": 1, "partial_cost_usd": 0.03},
        )
    )
    storage._fetch_items = AsyncMock(
        return_value=[{"assistant_id": "helper", "cost_complete": False}]
    )
    _, total, stats = await storage.list_usage_logs(user_id="owner", assistant_id="helper")
    assert total == 1 and stats["usage_unknown_requests"] == 1
    assert stats["partial_cost_usd"] == 0.03
    storage._count_and_stats.assert_awaited_once_with(
        {"user_id": "owner", "assistant_id": "helper"}
    )


def test_detached_usage_attribution_is_explicit_owner_bound_and_does_not_install_graph_context():
    from langchain_core.runnables.config import var_child_runnable_config

    from src.infra.llm import quota
    from src.infra.usage.attribution import usage_attribution

    token = quota._owner.set("owner")
    config_before = var_child_runnable_config.get()
    try:
        with usage_attribution("owner", "source"):
            assert quota._usage_context() == {
                "session_id": "source",
                "run_id": None,
                "trace_id": None,
            }
            assert var_child_runnable_config.get() is config_before
        with usage_attribution("another", "private"):
            assert quota._usage_context().get("session_id") != "private"
        assert quota._usage_context().get("session_id") != "source"
    finally:
        quota._owner.reset(token)

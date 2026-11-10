"""Detached paid calls share dashboard accounting without duplicating main traces."""

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables.config import var_child_runnable_config

from src.infra.llm import quota
from src.infra.pricing.calculator import PriceRates
from src.infra.usage import auxiliary
from src.infra.usage.storage import UsageStorage


@pytest.fixture(autouse=True)
def auxiliary_user_lookup(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(auxiliary, "UserStorage", lambda: SimpleNamespace(get_by_id=lookup))
    return lookup


def reservation():
    return {
        "id": "call",
        "user_id": "owner",
        "created_at": datetime(2026, 10, 19, tzinfo=timezone.utc),
        "context": {
            "trace_id": "main",
            "session_id": "session",
            "run_id": "run",
            "model": "helper",
            "model_config_id": "helper-id",
            "provider": "openai",
        },
    }


@pytest.mark.parametrize("unknown", [True, False])
async def test_auxiliary_projection_uses_distinct_key_settled_amount_and_notifies(
    monkeypatch, unknown
):
    storage = SimpleNamespace(upsert_usage_log_from_trace_metadata=AsyncMock(return_value=True))
    notify = AsyncMock()
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        auxiliary,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=notify),
    )
    ticket = reservation()
    await auxiliary.write_auxiliary_usage(ticket, {"charged_units": 13, "unknown": unknown})
    trace, usage = storage.upsert_usage_log_from_trace_metadata.await_args.args
    assert trace["trace_id"] == "usage_call_call" != ticket["context"]["trace_id"]
    assert trace["user_id"] == "owner"
    assert trace["session_id"] == "session"
    assert trace["started_at"] == ticket["created_at"]
    assert trace["metadata"]["source"] == "auxiliary"
    assert trace["status"] == "completed"
    assert usage["cost_units"] == 13
    assert usage["cost_complete"] is not unknown
    assert usage["partial_cost_usd" if unknown else "cost_usd"] == 13 / 1e9
    assert usage["unknown_usage_fields"]
    notify.assert_awaited_once()


async def test_projection_failure_does_not_escape_or_notify(monkeypatch):
    notify = AsyncMock()
    storage = SimpleNamespace(
        upsert_usage_log_from_trace_metadata=AsyncMock(side_effect=RuntimeError("offline"))
    )
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        auxiliary,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=notify),
    )
    await auxiliary.write_auxiliary_usage(reservation(), {"charged_units": 3, "unknown": False})
    notify.assert_not_awaited()


@pytest.mark.parametrize("owned", [True, False])
async def test_quota_finish_projects_only_detached_calls(monkeypatch, owned):
    project = AsyncMock()
    monkeypatch.setattr(auxiliary, "write_auxiliary_usage", project)
    owner = SimpleNamespace(record_usage_receipt=AsyncMock()) if owned else None
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 9, "unknown": False}))
    await quota.QuotaChatMixin._quota_finish(
        object(),
        (ledger, reservation(), PriceRates(input=1, output=1), owner),
        AIMessage(content="ok"),
    )
    if owned:
        owner.record_usage_receipt.assert_awaited_once()
        project.assert_not_awaited()
    else:
        project.assert_awaited_once()
        assert project.await_args.args[1]["charged_units"] == 9


@pytest.mark.parametrize("status", ["completed", "error", "cancelled"])
async def test_unpriced_detached_calls_project_unknown_settlements(monkeypatch, status):
    project = AsyncMock()
    monkeypatch.setattr(auxiliary, "write_auxiliary_usage", project)
    monkeypatch.setattr(quota, "quota_user_id", lambda: "owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(quota, "_usage_owner", lambda: None)
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 0, "unknown": True}))
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    monkeypatch.setattr(quota, "_reserve_call", AsyncMock(return_value=reservation()))
    error = {"error": RuntimeError(), "cancelled": asyncio.CancelledError()}.get(status)
    if error is None:
        async with quota.unpriced_usage():
            pass
    else:
        with pytest.raises(type(error)):
            async with quota.unpriced_usage():
                raise error
    project.assert_awaited_once()
    assert project.await_args.args[1]["unknown"] is True
    assert project.await_args.kwargs["status"] == status


def test_recommendation_identity_falls_back_to_explicit_config(monkeypatch):
    from src.infra.logging.context import TraceContext

    monkeypatch.setattr(TraceContext, "get", lambda: SimpleNamespace(trace_id=None))
    monkeypatch.setattr(TraceContext, "get_session_id", lambda: None)
    monkeypatch.setattr(TraceContext, "get_run_id", lambda: None)
    identity = {"trace_id": "parent", "session_id": "s", "run_id": "r"}
    token = var_child_runnable_config.set({"configurable": identity})
    try:
        assert quota._usage_context() == identity
    finally:
        var_child_runnable_config.reset(token)


@pytest.mark.parametrize("complete", [True, False])
async def test_auxiliary_updates_fence_stale_partial_and_completed_receipts(monkeypatch, complete):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(storage, "_get_session_metadata", AsyncMock(return_value={}))
    await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "usage_call_call", "metadata": {"source": "auxiliary"}},
        {
            "cost_source": "provider_settlement",
            "cost_units": 7,
            "cost_complete": complete,
            "cost_usd" if complete else "partial_cost_usd": 7 / 1e9,
        },
    )
    query = storage.collection.update_one.await_args.args[0]
    assert query["cost_complete"] == {"$ne": True}
    if not complete:
        assert query["cost_units"] == {"$not": {"$gt": 7}}


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit MongoDB opt-in")
async def test_real_mongo_auxiliary_concurrent_partials_and_final_are_monotonic(monkeypatch):
    import asyncio
    from uuid import uuid4

    from pymongo import AsyncMongoClient

    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_auxiliary_{uuid4().hex}"]
    storage = UsageStorage()
    storage._collection = collection
    monkeypatch.setattr(storage, "_get_session_metadata", AsyncMock(return_value={}))

    async def save(units, complete=False):
        return await storage.upsert_usage_log_from_trace_metadata(
            {
                "trace_id": "usage_call_test",
                "event_revision": 2 if complete else 1,
                "metadata": {"source": "auxiliary"},
            },
            {
                "cost_source": "provider_settlement",
                "cost_units": units,
                "cost_complete": complete,
                "cost_usd" if complete else "partial_cost_usd": units / 1e9,
            },
        )

    try:
        await collection.create_index("trace_id", unique=True)
        await asyncio.gather(save(9), save(5), save(7))
        assert (await collection.find_one({}))["cost_units"] == 9
        await asyncio.gather(save(13, True), save(11), save(4))
        assert not await save(2)
        assert not await save(13, True)
        doc = await collection.find_one({})
        assert doc["cost_complete"] is True
        assert doc["cost_units"] == 13
        assert await collection.count_documents({}) == 1
    finally:
        await collection.drop()
        await client.close()


def test_auxiliary_owner_does_not_borrow_another_users_session(monkeypatch):
    monkeypatch.setattr(quota, "quota_user_id", lambda: "other-owner")
    token = var_child_runnable_config.set(
        {"configurable": {"user_id": "parent-owner", "session_id": "private-session"}}
    )
    try:
        assert quota._usage_context() == {}
    finally:
        var_child_runnable_config.reset(token)


@pytest.mark.parametrize("outcome", ["found", "missing", "unavailable"])
async def test_auxiliary_username_uses_billing_owner_without_blocking_logs(
    monkeypatch, auxiliary_user_lookup, outcome
):
    if outcome == "found":
        auxiliary_user_lookup.return_value = SimpleNamespace(username="billing-owner-name")
    elif outcome == "unavailable":
        auxiliary_user_lookup.side_effect = RuntimeError("lookup unavailable")
    storage = SimpleNamespace(upsert_usage_log_from_trace_metadata=AsyncMock(return_value=False))
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: storage)
    ticket = reservation()
    ticket["context"]["user_id"] = "different-parent-owner"
    await auxiliary.write_auxiliary_usage(ticket, {"charged_units": 7, "unknown": False})
    auxiliary_user_lookup.assert_awaited_once_with("owner")
    trace = storage.upsert_usage_log_from_trace_metadata.await_args.args[0]
    assert trace["user_id"] == "owner"
    assert trace["metadata"]["username"] == ("billing-owner-name" if outcome == "found" else "")


async def test_auxiliary_records_identity_duration_and_safe_http_failure(monkeypatch):
    import httpx

    storage = SimpleNamespace(upsert_usage_log_from_trace_metadata=AsyncMock(return_value=False))
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        auxiliary, "utc_now", lambda: datetime(2026, 10, 19, 0, 0, 3, tzinfo=timezone.utc)
    )
    ticket = reservation()
    ticket["context"]["operation"] = "embedding"
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test/secret"))
    error = httpx.HTTPStatusError(
        "private upstream body", request=response.request, response=response
    )
    await auxiliary.write_auxiliary_usage(
        ticket, {"charged_units": 0, "unknown": True}, status="error", error=error
    )
    trace, usage = storage.upsert_usage_log_from_trace_metadata.await_args.args
    assert usage["operation"] == "embedding"
    assert usage["provider"] == "openai"
    assert usage["duration"] == 3
    failure = storage.upsert_usage_log_from_trace_metadata.await_args.kwargs["error_data"]
    assert failure == {"type": "HTTPStatusError", "error": "HTTPStatusError (HTTP 429)"}
    assert trace["status"] == "error"


async def test_unpriced_identity_and_exception_reach_projection(monkeypatch):
    project = AsyncMock()
    reserve = AsyncMock(return_value=reservation())
    monkeypatch.setattr(auxiliary, "write_auxiliary_usage", project)
    monkeypatch.setattr(quota, "quota_user_id", lambda: "owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(quota, "_usage_owner", lambda: None)
    monkeypatch.setattr(quota, "_usage_context", lambda: {"session_id": "session"})
    monkeypatch.setattr(
        quota,
        "UsageQuota",
        lambda: SimpleNamespace(
            settle=AsyncMock(return_value={"charged_units": 0, "unknown": True})
        ),
    )
    monkeypatch.setattr(quota, "_reserve_call", reserve)
    error = TimeoutError("private details")
    with pytest.raises(TimeoutError):
        async with quota.unpriced_usage(
            operation="embedding", model="embed-model", provider="provider"
        ):
            raise error
    assert reserve.await_args.kwargs["context"] == {
        "session_id": "session",
        "operation": "embedding",
        "model": "embed-model",
        "provider": "provider",
    }
    assert project.await_args.kwargs["error"] is error


@pytest.mark.parametrize(
    ("operation", "model", "base", "payload", "expected_cost", "tokens"),
    [
        (
            "embedding",
            "Qwen/Qwen3-Embedding-0.6B",
            "https://api.siliconflow.cn",
            {"usage": {"prompt_tokens": 100, "total_tokens": 100}},
            0.000001,
            100,
        ),
        (
            "decision",
            "apus-openjev-4b-5949",
            "http://127.0.0.1:18001",
            {"usage": {"input_tokens": 100, "output_tokens": 0}},
            0.000001,
            100,
        ),
        (
            "decision",
            "apus-openjev-4b-5949",
            "http://127.0.0.1:18001",
            {"usage": {"input_tokens": 0, "output_tokens": 0}},
            None,
            None,
        ),
        (
            "rerank",
            "BAAI/bge-reranker-v2-m3",
            "https://api.siliconflow.cn",
            {"meta": {"billed_units": {"input_tokens": 12, "output_tokens": 0}}},
            0,
            12,
        ),
        (
            "embedding",
            "Qwen/Qwen3-Embedding-0.6B",
            "https://different.example",
            {"usage": {"prompt_tokens": 100}},
            None,
            100,
        ),
        (
            "embedding",
            "Qwen/Qwen3-Embedding-0.6B",
            "https://api.siliconflow.cn",
            {"usage": {"prompt_tokens": True}},
            None,
            None,
        ),
    ],
)
async def test_raw_model_cost_uses_endpoint_tariff_and_reported_tokens(
    monkeypatch, operation, model, base, payload, expected_cost, tokens
):
    project = AsyncMock()
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 0, "unknown": True}))
    monkeypatch.setattr(auxiliary, "write_auxiliary_usage", project)
    monkeypatch.setattr(quota, "quota_user_id", lambda: "owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(quota, "_usage_owner", lambda: None)
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    monkeypatch.setattr(quota, "_reserve_call", AsyncMock(return_value=reservation()))
    monkeypatch.setattr(
        "src.infra.pricing.auxiliary_models.get_fx_rates",
        AsyncMock(return_value={"base": "USD", "rates": {"CNY": 7}}),
    )
    async with quota.unpriced_usage(operation=operation, model=model, api_base=base) as observe:
        observe(payload)
    assert ledger.settle.await_args.args[1] == expected_cost
    assert project.await_args.args[1]["model_usage"]["input_tokens"] == tokens


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit MongoDB opt-in")
async def test_three_model_clients_charge_same_amount_as_logs_in_both_windows(monkeypatch):
    from functools import partial
    from uuid import uuid4

    import httpx
    from pymongo import AsyncMongoClient

    from src.infra.decision.client import judge_noul
    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.infra.memory.client.native.search import rerank_candidates
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    mongo = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    db = mongo[settings.MONGODB_DB]
    suffix = uuid4().hex
    ledger = quota.UsageQuota(db[f"test_raw_ledger_{suffix}"])
    storage = UsageStorage()
    storage._collection = db[f"test_raw_logs_{suffix}"]
    monkeypatch.setattr(quota, "quota_user_id", lambda: "metering-test")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, 2)))
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.pricing.auxiliary_models.get_fx_rates",
        AsyncMock(return_value={"base": "USD", "rates": {"CNY": 7}}),
    )
    for prefix, base, model in (
        ("NATIVE_MEMORY_EMBEDDING", "https://api.siliconflow.cn", "Qwen/Qwen3-Embedding-0.6B"),
        ("NATIVE_MEMORY_RERANK", "https://api.siliconflow.cn", "BAAI/bge-reranker-v2-m3"),
        ("SYSTEMONE", "http://127.0.0.1:18001", "apus-openjev-4b-5949"),
    ):
        monkeypatch.setattr(settings, prefix + "_API_BASE", base)
        monkeypatch.setattr(settings, prefix + "_API_KEY", "synthetic")
        monkeypatch.setattr(settings, prefix + "_MODEL", model)

    responses = {
        "/v1/embeddings": {
            "usage": {"prompt_tokens": 4, "total_tokens": 4},
            "data": [{"embedding": [1.0]}],
        },
        "/v1/rerank": {
            "meta": {"billed_units": {"input_tokens": 12, "output_tokens": 0}},
            "results": [{"index": 1}],
        },
        "/v1/systemone": {
            "usage": {"input_tokens": 87, "output_tokens": 0},
            "answers": {"q": {"noul": 0.9}},
        },
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=responses[req.url.path]))
    monkeypatch.setattr(httpx, "AsyncClient", partial(httpx.AsyncClient, transport=transport))
    backend = NativeMemoryBackend()
    try:
        backend._setup_embedding_fn()
        assert await backend._maybe_embed("blue") == [1.0]
        assert await rerank_candidates("blue", [{"text": "red"}, {"text": "blue"}], 1) == [
            {"text": "blue"}
        ]
        assert await judge_noul("blue", "Is the state blue?", transport=transport) == 0.9
        rows = {
            d["operation"]: (d["input_tokens"], d["cost_units"], d["cost_complete"])
            async for d in storage.collection.find({})
        }
        assert rows == {
            "embedding": (4, 40, True),
            "rerank": (12, 0, True),
            "decision": (87, 870, True),
        }
        account = await ledger.collection.find_one({"_id": "metering-test"})
        for name in ("five_hour", "weekly"):
            window = account["periods"][account[name]["key"]]
            assert (window["used"], window["unknown"]) == (910, 0)
    finally:
        if backend._httpx_client is not None:
            await backend._httpx_client.aclose()
        await ledger.collection.drop()
        await storage.collection.drop()
        await mongo.close()

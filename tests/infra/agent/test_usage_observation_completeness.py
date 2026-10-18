"""Omitted provider counters default to zero without discarding reported usage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.agent.events import processor as processor_module
from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import create_presenter


def processor(monkeypatch):
    price = AsyncMock(return_value=None)
    monkeypatch.setattr(processor_module, "compute_usage_cost", price)
    instance = AgentEventProcessor(create_presenter(session_id="usage-test", agent_id="search"))
    instance._presenter_emit = AsyncMock()
    return instance, price


def record(instance, *, details=None, missing_usage=False):
    usage = None if missing_usage else {"input_tokens": 100, "output_tokens": 10}
    if usage is not None and details is not None:
        usage["input_token_details"] = details
    instance._handle_token_usage(
        {"data": {"output": SimpleNamespace(usage_metadata=usage, response_metadata={})}}
    )


async def test_explicit_cache_zero_survives_sse_emission(monkeypatch):
    instance, price = processor(monkeypatch)
    record(instance, details={"cache_read": 0, "cache_creation": 0})
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["cache_read_tokens"] == 0
    assert data["cache_creation_tokens"] == 0
    price.assert_awaited_once()


async def test_missing_cache_counts_default_to_zero(monkeypatch):
    instance, price = processor(monkeypatch)
    record(instance)
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["cache_read_tokens"] == data["cache_creation_tokens"] == 0
    assert data["usage_incomplete"] is False
    price.assert_awaited_once()


async def test_missing_cache_counts_preserve_reported_aggregate_counts(monkeypatch):
    instance, price = processor(monkeypatch)
    record(instance, details={"cache_read": 70, "cache_creation": 0})
    record(instance)
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 200 and data["cache_read_tokens"] == 70
    assert data["usage_incomplete"] is False
    assert data["input_includes_cache"] is True
    price.assert_awaited_once()


@pytest.mark.parametrize("legacy", [False, True])
async def test_cache_completeness_survives_resume_and_legacy_is_conservative(monkeypatch, legacy):
    first, _ = processor(monkeypatch)
    record(first, details={"cache_read": 0, "cache_creation": 0})
    snapshot = first.usage_totals()
    if legacy:
        snapshot = {key: value for key, value in snapshot.items() if key.endswith("tokens")}
    second, price = processor(monkeypatch)
    second.seed_usage(snapshot)
    record(second, details={"cache_read": 0, "cache_creation": 0})
    assert await second.emit_token_usage()
    data = second._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 200 and data["output_tokens"] == 20
    if legacy:
        assert data["cache_read_tokens"] == 0
        assert data["usage_incomplete"] is False
        assert data.get("input_includes_cache") is not True
        price.assert_not_awaited()
    else:
        assert data["cache_read_tokens"] == data["cache_creation_tokens"] == 0
    # Token completeness cannot certify a restored snapshot without call receipts.
    price.assert_not_awaited()
    assert data["cost_complete"] is False and "cost_usd" not in data


async def test_completed_model_without_usage_counts_as_zero(monkeypatch):
    instance, price = processor(monkeypatch)
    record(instance, missing_usage=True)
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == data["output_tokens"] == 0
    assert data["usage_incomplete"] is False
    price.assert_awaited_once()


async def model_event(instance, kind, run_id, *, metadata=None, complete=False):
    data = {}
    if complete:
        data["output"] = SimpleNamespace(
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "input_token_details": {"cache_read": 70, "cache_creation": 0},
            },
            response_metadata={},
        )
    await instance.process_event(
        {"event": kind, "run_id": run_id, "metadata": metadata or {}, "data": data}
    )


@pytest.mark.parametrize("failed_terminal", ["error", "missing_end"])
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"lc_source": "summarization"},
        {"internal_tool_call": True},
        {"lambchat_subagent_id": "child"},
    ],
)
async def test_failed_attempt_preserves_successful_retry_usage(
    monkeypatch, failed_terminal, metadata
):
    instance, price = processor(monkeypatch)
    await model_event(instance, "on_chat_model_start", "failed", metadata=metadata)
    if failed_terminal == "error":
        await model_event(instance, "on_chat_model_error", "failed", metadata=metadata)
    await model_event(instance, "on_chat_model_start", "retry", metadata=metadata)
    await model_event(instance, "on_chat_model_end", "retry", metadata=metadata, complete=True)
    assert await instance.emit_token_usage() is False
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert (data["input_tokens"], data["output_tokens"], data["total_tokens"]) == (100, 10, 110)
    assert data["usage_incomplete"] is False
    assert data["input_includes_cache"] is True
    assert data["unknown_usage_fields"] == []
    assert price.await_count == (2 if failed_terminal == "error" else 1)
    restored, restored_price = processor(monkeypatch)
    restored.seed_usage(instance.usage_totals())
    await model_event(restored, "on_chat_model_start", "resumed")
    await model_event(restored, "on_chat_model_end", "resumed", complete=True)
    assert await restored.emit_token_usage() is False
    resumed = restored._presenter_emit.call_args.args[0]["data"]
    assert resumed["input_tokens"] == 200 and resumed["usage_incomplete"] is False
    restored_price.assert_not_awaited()
    assert resumed["cost_complete"] is False and "cost_usd" not in resumed


async def test_successful_parallel_attempts_do_not_poison_interim_usage(monkeypatch):
    instance, price = processor(monkeypatch)
    await model_event(instance, "on_chat_model_start", "first")
    await model_event(instance, "on_chat_model_start", "second")
    await model_event(instance, "on_chat_model_end", "first", complete=True)
    assert instance._usage_unknown_fields == set()
    assert instance.usage_totals()["unknown_usage_fields"] == []
    await model_event(instance, "on_chat_model_end", "second", complete=True)
    assert await instance.emit_token_usage() is False
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 200
    assert data["input_includes_cache"] is True
    assert data.get("usage_incomplete") is not True
    assert price.await_count == 2


async def test_started_attempt_without_reported_usage_counts_as_zero(monkeypatch):
    instance, price = processor(monkeypatch)
    await model_event(instance, "on_chat_model_start", "interrupted")
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == data["output_tokens"] == 0
    assert data["usage_incomplete"] is False
    assert data["input_includes_cache"] is True
    price.assert_awaited_once()


async def test_finalizing_quick_stream_preserves_received_usage(monkeypatch):
    instance, price = processor(monkeypatch)
    record(instance, details={"cache_read": 70, "cache_creation": 0})
    await model_event(instance, "on_chat_model_start", "interrupted")
    await instance.finalize()
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 100 and data["cache_read_tokens"] == 70
    assert data["usage_incomplete"] is False
    price.assert_awaited_once()


async def test_error_without_started_attempt_does_not_poison_complete_usage(monkeypatch):
    instance, price = processor(monkeypatch)
    await model_event(instance, "on_chat_model_error", "guard-denied")
    await model_event(instance, "on_chat_model_start", "success")
    await model_event(instance, "on_chat_model_end", "success", complete=True)
    assert await instance.emit_token_usage() is False
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["usage_incomplete"] is False
    assert data["input_includes_cache"] is True
    price.assert_awaited_once()


async def test_duplicate_model_terminal_callbacks_do_not_double_count_usage(monkeypatch):
    instance, price = processor(monkeypatch)
    await model_event(instance, "on_chat_model_start", "success")
    await model_event(instance, "on_chat_model_end", "success", complete=True)
    await model_event(instance, "on_chat_model_end", "success", complete=True)
    await model_event(instance, "on_chat_model_error", "success")
    assert await instance.emit_token_usage() is False
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["total_tokens"] == 110
    assert data["usage_incomplete"] is False
    price.assert_awaited_once()


@pytest.mark.parametrize("bad_write", [None, True, -1])
async def test_resume_defaults_missing_cache_write_and_rejects_invalid_counts(
    monkeypatch, bad_write
):
    instance, price = processor(monkeypatch)
    prior = dict(
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=70,
        unknown_usage_fields=[],
        input_includes_cache=True,
        usage_observed=True,
    )
    if bad_write is not None:
        prior["cache_creation_tokens"] = bad_write
    instance.seed_usage(prior)
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 100 and data["cache_read_tokens"] == 70
    if bad_write is None:
        assert data["cache_creation_tokens"] == 0
        assert data["usage_incomplete"] is False
        price.assert_not_awaited()
        assert data["cost_complete"] is False and "cost_usd" not in data
    else:
        assert "cache_creation_tokens" in data["unknown_usage_fields"]
        assert "cache_creation_tokens" not in data
        assert data["usage_incomplete"] is True and "cost_usd" not in data
        price.assert_not_awaited()


@pytest.mark.parametrize("invalid", [True, -1])
async def test_invalid_native_usage_is_unknown_not_a_measured_count(monkeypatch, invalid):
    instance, price = processor(monkeypatch)
    record(instance, details={"cache_read": 0, "cache_creation": invalid})
    assert await instance.emit_token_usage()
    data = instance._presenter_emit.call_args.args[0]["data"]
    assert "cache_creation_tokens" in data["unknown_usage_fields"]
    assert "cache_creation_tokens" not in data
    price.assert_not_awaited()


async def test_raw_provider_counts_without_inclusive_input_cannot_certify_cost(monkeypatch):
    instance, price = processor(monkeypatch)
    instance._handle_token_usage(
        {
            "data": {
                "output": SimpleNamespace(
                    usage_metadata=None,
                    response_metadata={
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 10,
                            "total_tokens": 110,
                            "cache_read_input_tokens": 70,
                            "cache_creation_input_tokens": 0,
                        }
                    },
                )
            }
        }
    )
    assert await instance.emit_token_usage()
    assert (
        instance._presenter_emit.call_args.args[0]["data"].get("input_includes_cache") is not True
    )
    price.assert_not_awaited()

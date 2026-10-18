from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.agent.events import processor as module
from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import create_presenter


def make_processor(monkeypatch):
    monkeypatch.setattr(module, "compute_usage_cost", AsyncMock(return_value=None))
    presenter = create_presenter(session_id="shared-usage", agent_id="search")
    presenter.emit = AsyncMock()
    return AgentEventProcessor(presenter)


async def event(processor, kind, run):
    data = {}
    if kind == "on_chat_model_end":
        data["output"] = SimpleNamespace(
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "input_token_details": {"cache_read": 70, "cache_creation": 0},
            },
            response_metadata={},
        )
    await processor.process_event({"event": kind, "run_id": run, "metadata": {}, "data": data})


async def test_outer_summary_and_interrupted_inner_preserve_reported_total(monkeypatch):
    outer = make_processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    await event(outer, "on_chat_model_start", "summary")
    await event(outer, "on_chat_model_end", "summary")
    await event(inner, "on_chat_model_start", "interrupted-main")

    assert await inner.emit_token_usage()
    data = outer.presenter.emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 100 and data["cache_read_tokens"] == 70
    assert data["usage_incomplete"] is False
    assert data.get("input_includes_cache") is True
    assert data["unknown_usage_fields"] == []
    assert await outer.emit_token_usage() is False


async def test_native_uuid_seen_by_outer_and_inner_is_counted_once(monkeypatch):
    outer = make_processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    for processor in (outer, inner):
        await event(processor, "on_chat_model_start", "same-native-call")
        await event(processor, "on_chat_model_end", "same-native-call")
    assert outer.usage_totals()["input_tokens"] == 100
    assert inner.usage_totals() == outer.usage_totals()
    assert await inner.emit_token_usage() is False
    assert await outer.emit_token_usage() is False
    assert outer.presenter.emit.call_args.args[0]["data"]["input_includes_cache"] is True


async def test_separate_presenters_never_share_incomplete_attempts(monkeypatch):
    first, second = make_processor(monkeypatch), make_processor(monkeypatch)
    await event(first, "on_chat_model_start", "same-native-call")
    await event(second, "on_chat_model_start", "same-native-call")
    await event(second, "on_chat_model_end", "same-native-call")
    assert await first.emit_token_usage()
    assert await second.emit_token_usage() is False
    assert first.presenter.emit.call_args.args[0]["data"]["usage_incomplete"] is False
    assert second.presenter.emit.call_args.args[0]["data"]["usage_incomplete"] is False


def test_resume_snapshot_is_seeded_once_across_nested_processors(monkeypatch):
    outer = make_processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    prior = {
        "input_tokens": 100,
        "output_tokens": 10,
        "total_tokens": 110,
        "cache_read_tokens": 70,
        "cache_creation_tokens": 0,
        "usage_observed": True,
        "unknown_usage_fields": [],
        "input_includes_cache": True,
    }
    outer.seed_usage(prior)
    inner.seed_usage(prior)
    assert outer.usage_totals()["input_tokens"] == 100
    assert inner.usage_totals() == outer.usage_totals()


async def test_interrupted_stream_without_start_callback_preserves_summary_usage(monkeypatch):
    from langchain_core.messages import AIMessageChunk

    processor = make_processor(monkeypatch)
    await event(processor, "on_chat_model_start", "summary")
    await event(processor, "on_chat_model_end", "summary")
    await processor.process_event(
        {
            "event": "on_chat_model_stream",
            "run_id": "missing-start-main",
            "metadata": {},
            "data": {
                "chunk": AIMessageChunk(
                    content="", additional_kwargs={"reasoning_content": "Still working"}
                )
            },
        }
    )
    assert await processor.emit_token_usage()
    data = processor.presenter.emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 100
    assert data.get("input_includes_cache") is True
    assert data["unknown_usage_fields"] == []


async def test_delayed_outer_end_after_inner_snapshot_adds_known_usage_once(monkeypatch):
    outer = make_processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    await event(outer, "on_chat_model_start", "queued-summary")
    await event(inner, "on_chat_model_start", "inner-main")
    await event(inner, "on_chat_model_end", "inner-main")
    assert await inner.emit_token_usage() is False
    assert outer.usage_totals()["input_tokens"] == 100
    assert outer.usage_totals()["unknown_usage_fields"] == []
    await event(outer, "on_chat_model_end", "queued-summary")
    await event(inner, "on_chat_model_end", "queued-summary")
    assert outer.usage_totals()["input_tokens"] == 200
    assert outer.usage_totals()["cache_read_tokens"] == 140
    assert await outer.emit_token_usage() is False
    data = outer.presenter.emit.call_args.args[0]["data"]
    assert data["input_tokens"] == 200 and data["usage_incomplete"] is False


async def test_end_during_snapshot_delivery_publishes_both_snapshots_in_order(monkeypatch):
    import asyncio

    outer = make_processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    entered, release = asyncio.Event(), asyncio.Event()
    snapshots = []

    async def deliver(value):
        snapshots.append(value["data"])
        if len(snapshots) == 1:
            entered.set()
            await release.wait()

    outer._presenter_emit = deliver
    await event(outer, "on_chat_model_start", "late")
    emitting = asyncio.create_task(event(inner, "on_chat_model_end", "main"))
    await entered.wait()
    late = asyncio.create_task(event(outer, "on_chat_model_end", "late"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(emitting, late)
    assert snapshots[0]["input_tokens"] == 100
    assert await outer.emit_token_usage() is False
    assert snapshots[-1]["input_tokens"] == 200
    assert snapshots[-1]["total_tokens"] == 220
    assert snapshots[-1]["usage_incomplete"] is False


async def test_end_during_pricing_does_not_mix_two_ledger_snapshots(monkeypatch):
    import asyncio

    outer = make_processor(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def price(**kwargs):
        entered.set()
        await release.wait()
        return None

    monkeypatch.setattr(module, "compute_usage_cost", price)
    emitting = asyncio.create_task(event(outer, "on_chat_model_end", "first"))
    await entered.wait()
    second = asyncio.create_task(event(outer, "on_chat_model_end", "second"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(emitting, second)
    snapshot = outer.presenter.emit.call_args_list[0].args[0]["data"]
    assert snapshot["input_tokens"] == 100
    assert snapshot["total_tokens"] == 110
    assert await outer.emit_token_usage() is False
    assert outer.presenter.emit.call_args.args[0]["data"]["input_tokens"] == 200

"""Each completed model call is visible before the enclosing agent finishes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.writer.present import create_presenter


def model_end(run_id):
    return {
        "event": "on_chat_model_end",
        "run_id": run_id,
        "metadata": {},
        "data": {
            "output": SimpleNamespace(
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                    "input_token_details": {"cache_read": 0, "cache_creation": 0},
                },
                response_metadata={},
            )
        },
    }


def processor(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.events.processor.compute_usage_cost", AsyncMock(return_value=None)
    )
    presenter = create_presenter(session_id="s", agent_id="search", model="chosen", model_id="m")
    presenter.emit = AsyncMock()
    return AgentEventProcessor(presenter)


async def test_each_call_emits_cumulative_usage_and_duplicate_child_callback_is_harmless(
    monkeypatch,
):
    outer = processor(monkeypatch)
    inner = AgentEventProcessor(outer.presenter)
    await inner.process_event(model_end("first"))
    first = outer.presenter.emit.call_args.args[0]
    assert first["event"] == "token:usage"
    assert first["data"]["input_tokens"] == 100
    assert first["data"]["model_id"] == "m"
    await outer.process_event(model_end("first"))
    assert outer.presenter.emit.call_count == 1
    await outer.process_event(model_end("second"))
    assert outer.presenter.emit.call_args.args[0]["data"]["input_tokens"] == 200
    await outer.emit_token_usage(duration=12)
    assert outer.presenter.emit.call_args.args[0]["data"]["duration"] == 12
    assert outer.presenter.emit.call_args.args[0]["data"]["input_tokens"] == 200
    await outer.process_event(model_end("late"))
    assert outer.presenter.emit.call_args.args[0]["data"]["duration"] == 12
    assert outer.presenter.emit.call_args.args[0]["data"]["input_tokens"] == 300


async def test_concurrent_completions_never_publish_an_older_total_after_a_newer_one(monkeypatch):
    outer = processor(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    totals = []

    async def deliver(event):
        if event["data"]["input_tokens"] == 100:
            entered.set()
            await release.wait()
        totals.append(event["data"]["input_tokens"])

    outer._presenter_emit = deliver
    first = asyncio.create_task(outer.process_event(model_end("first")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(outer.process_event(model_end("second")))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        assert totals == [100, 200]
    finally:
        release.set()
        await first

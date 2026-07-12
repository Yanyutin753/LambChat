import asyncio
from typing import Any

import pytest

from src.agents.core import base as base_module
from src.infra.task.exceptions import TaskInterruptedError


class _FakePresenter:
    run_id = "run-usage-cancel"
    trace_id = "trace-usage-cancel"

    def __init__(self) -> None:
        self.emitted_events: list[dict[str, Any]] = []

    async def _ensure_trace(self) -> None:
        return None

    async def build_langsmith_metadata(self) -> dict[str, Any]:
        return {}

    def metadata(self) -> dict[str, Any]:
        return {"event": "metadata", "data": {"run_id": self.run_id}}

    def done(self) -> dict[str, Any]:
        return {"event": "done", "data": {}}

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        self.emitted_events.append(event)
        return event


class _FakeGraph:
    async def astream_events(self, *_args, **_kwargs):
        yield {"event": "on_chat_model_end", "data": {"output": object()}}
        while True:
            await asyncio.sleep(60)


class _BurstGraph:
    async def astream_events(self, *_args, **_kwargs):
        index = 0
        while True:
            yield {"event": "on_chain_stream", "data": {"chunk": index}}
            index += 1


class _TestAgent(base_module.BaseGraphAgent):
    def build_graph(self, builder) -> None:
        return None


@pytest.mark.asyncio
async def test_cancelled_base_agent_emits_accumulated_token_usage(monkeypatch) -> None:
    processed = asyncio.Event()
    instances = []

    class FakeProcessor:
        def __init__(self, presenter, base_url: str = "") -> None:
            self.presenter = presenter
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_tokens = 0
            self.total_cache_creation_tokens = 0
            self.total_cache_read_tokens = 0
            self.usage_calls: list[dict[str, Any]] = []
            instances.append(self)

        async def process_event(self, event: dict[str, Any]) -> None:
            self.total_input_tokens = 11
            self.total_output_tokens = 4
            processed.set()

        async def finalize(self) -> None:
            return None

        async def emit_token_usage(self, **kwargs) -> bool:
            self.usage_calls.append(kwargs)
            await self.presenter.emit({"event": "token:usage", "data": kwargs})
            return True

    async def no_interrupt(_run_id: str) -> None:
        return None

    monkeypatch.setattr(base_module, "AgentEventProcessor", FakeProcessor)
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt",
        no_interrupt,
    )
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt_fast",
        lambda _run_id: False,
    )

    agent = _TestAgent()
    agent._initialized = True
    agent._graph = _FakeGraph()

    presenter = _FakePresenter()
    stream = agent._stream(
        "hello",
        "session-1",
        "user-1",
        presenter=presenter,
        agent_options={"model_id": "model-config-1", "model": "openai/gpt-4.1"},
    )

    assert await stream.__anext__() == {"event": "metadata", "data": {"run_id": "run-usage-cancel"}}

    next_event = asyncio.create_task(stream.__anext__())
    await asyncio.wait_for(processed.wait(), timeout=1)

    next_event.cancel()
    with pytest.raises(asyncio.CancelledError):
        await next_event

    assert instances[0].usage_calls == [
        {
            "model_id": "model-config-1",
            "model": "openai/gpt-4.1",
        }
    ]
    assert [event["event"] for event in presenter.emitted_events] == ["token:usage"]


@pytest.mark.asyncio
async def test_closed_inner_stream_persists_done_before_yielding_terminal_event(
    monkeypatch,
) -> None:
    processed = asyncio.Event()

    class FakeProcessor:
        def __init__(self, presenter, base_url: str = "") -> None:
            self.presenter = presenter
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_tokens = 0

        async def process_event(self, event: dict[str, Any]) -> None:
            self.total_input_tokens = 11
            self.total_output_tokens = 4
            processed.set()

        async def finalize(self) -> None:
            return None

        async def emit_token_usage(self, **kwargs) -> bool:
            await self.presenter.emit({"event": "token:usage", "data": kwargs})
            return True

    async def no_interrupt(_run_id: str) -> None:
        return None

    monkeypatch.setattr(base_module, "AgentEventProcessor", FakeProcessor)
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt",
        no_interrupt,
    )

    agent = _TestAgent()
    agent._initialized = True
    agent._graph = _FakeGraph()

    presenter = _FakePresenter()
    stream = agent._stream("hello", "session-1", "user-1", presenter=presenter)

    assert await stream.__anext__() == {"event": "metadata", "data": {"run_id": "run-usage-cancel"}}

    next_event = asyncio.create_task(stream.__anext__())
    await asyncio.wait_for(processed.wait(), timeout=1)
    await agent.close(presenter.run_id)

    assert await next_event == {"event": "done", "data": {}}
    assert [event["event"] for event in presenter.emitted_events] == ["token:usage", "done"]


@pytest.mark.asyncio
async def test_interrupted_inner_done_raises_after_persisting_terminal_events(
    monkeypatch,
) -> None:
    processed = asyncio.Event()

    class FakeProcessor:
        def __init__(self, presenter, base_url: str = "") -> None:
            self.presenter = presenter
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_tokens = 0

        async def process_event(self, event: dict[str, Any]) -> None:
            self.total_input_tokens = 11
            self.total_output_tokens = 4
            processed.set()

        async def finalize(self) -> None:
            return None

        async def emit_token_usage(self, **kwargs) -> bool:
            await self.presenter.emit({"event": "token:usage", "data": kwargs})
            return True

    async def no_interrupt(_run_id: str) -> None:
        return None

    monkeypatch.setattr(base_module, "AgentEventProcessor", FakeProcessor)
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt",
        no_interrupt,
    )
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt_fast",
        lambda _run_id: True,
    )

    agent = _TestAgent()
    agent._initialized = True
    agent._graph = _FakeGraph()

    presenter = _FakePresenter()
    stream = agent._stream("hello", "session-1", "user-1", presenter=presenter)

    assert await stream.__anext__() == {"event": "metadata", "data": {"run_id": "run-usage-cancel"}}

    next_event = asyncio.create_task(stream.__anext__())
    await asyncio.wait_for(processed.wait(), timeout=1)
    await agent.close(presenter.run_id)

    with pytest.raises(TaskInterruptedError):
        await next_event
    assert [event["event"] for event in presenter.emitted_events] == ["token:usage"]


@pytest.mark.asyncio
async def test_cancelled_full_event_queue_does_not_deadlock(monkeypatch) -> None:
    processor_started = asyncio.Event()

    class BlockingProcessor:
        def __init__(self, presenter, base_url: str = "") -> None:
            self.presenter = presenter

        async def process_event(self, event: dict[str, Any]) -> None:
            processor_started.set()
            await asyncio.sleep(60)

        async def finalize(self) -> None:
            return None

        async def emit_token_usage(self, **kwargs) -> bool:
            return True

    async def no_interrupt(_run_id: str) -> None:
        return None

    monkeypatch.setattr(base_module, "AgentEventProcessor", BlockingProcessor)
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt",
        no_interrupt,
    )
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt_fast",
        lambda _run_id: False,
    )

    agent = _TestAgent()
    agent._initialized = True
    agent._graph = _BurstGraph()

    presenter = _FakePresenter()
    stream = agent._stream("hello", "session-1", "user-1", presenter=presenter)

    assert await stream.__anext__() == {"event": "metadata", "data": {"run_id": "run-usage-cancel"}}

    next_event = asyncio.create_task(stream.__anext__())
    await asyncio.wait_for(processor_started.wait(), timeout=1)
    await asyncio.sleep(0)

    next_event.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(next_event, timeout=1)

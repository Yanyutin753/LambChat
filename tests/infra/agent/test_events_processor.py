from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.agent import AgentEventProcessor


class FakePresenter:
    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.emitted.append(event)

    def present_text(
        self,
        content: str,
        text_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "message:chunk",
            "data": {
                "content": content,
                "text_id": text_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }

    def present_summary(
        self,
        content: str,
        summary_id: str | None = None,
        depth: int = 0,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "summary",
            "data": {
                "content": content,
                "summary_id": summary_id,
                "depth": depth,
                "agent_id": agent_id,
            },
        }


def chat_stream(content: str, chunk_id: str = "chunk-1", metadata: dict[str, Any] | None = None):
    return {
        "event": "on_chat_model_stream",
        "name": "chat_model",
        "data": {"chunk": SimpleNamespace(content=content, id=chunk_id)},
        "metadata": metadata or {},
    }


@pytest.mark.asyncio
async def test_finalize_flushes_pending_summary_chunk() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(
        chat_stream("summarized intent", "summary-1", {"lc_source": "summarization"})
    )

    assert presenter.emitted == []

    await processor.finalize()

    assert presenter.emitted == [
        {
            "event": "summary",
            "data": {
                "content": "summarized intent",
                "summary_id": "summary-1",
                "depth": 0,
                "agent_id": None,
            },
        }
    ]


@pytest.mark.asyncio
async def test_text_chunk_key_change_flushes_previous_chunk_without_dropping_current() -> None:
    presenter = FakePresenter()
    processor = AgentEventProcessor(presenter)

    await processor.process_event(chat_stream("hello", "chunk-1"))
    await processor.process_event(chat_stream("world", "chunk-2"))
    await processor.process_event({"event": "on_chat_model_end", "data": {"output": None}})

    assert [event["data"]["content"] for event in presenter.emitted] == ["hello", "world"]

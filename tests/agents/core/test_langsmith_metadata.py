from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agents.core.base import BaseGraphAgent
from src.infra.writer.present import Presenter


class _FakeGraph:
    def __init__(self) -> None:
        self.captured_config = None

    async def astream_events(self, initial_state, config, version="v2"):
        self.captured_config = config
        if False:
            yield


class _TestAgent(BaseGraphAgent):
    def build_graph(self, builder) -> None:
        raise NotImplementedError


class _FakeUserStorage:
    async def get_by_id(self, user_id: str):
        return SimpleNamespace(username="alice")


@pytest.mark.asyncio
async def test_stream_includes_user_identity_in_runnable_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _TestAgent()
    fake_graph = _FakeGraph()
    agent._initialized = True
    agent._graph = fake_graph

    async def fake_ensure_trace(self) -> None:
        return None

    async def fake_complete(self, status: str) -> None:
        return None

    monkeypatch.setattr(Presenter, "_ensure_trace", fake_ensure_trace)
    monkeypatch.setattr(Presenter, "complete", fake_complete)
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage",
        lambda: _FakeUserStorage(),
    )

    events = []
    async for event in agent.stream("hello", session_id="session-1", user_id="user-123"):
        events.append(event)

    assert events[0]["event"] == "metadata"
    assert fake_graph.captured_config is not None
    assert fake_graph.captured_config["metadata"]["user_id"] == "user-123"
    assert fake_graph.captured_config["metadata"]["username"] == "alice"

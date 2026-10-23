from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import agent as agent_routes
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("close_early", [False, True])
async def test_direct_agent_stream_owns_heartbeat_until_closed(monkeypatch, close_early):
    heartbeat = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr("src.infra.task.heartbeat.TaskHeartbeat", lambda: heartbeat)

    async def stream(*args, **kwargs):
        yield {"event": "metadata", "data": {"run_id": "r1", "trace_id": "t1"}}
        heartbeat.start.assert_awaited_once_with("r1", trace_id="t1")
        heartbeat.stop.assert_not_awaited()
        yield {"event": "done", "data": {}}

    monkeypatch.setattr(
        agent_routes.AgentFactory, "get", AsyncMock(return_value=SimpleNamespace(stream=stream))
    )
    monkeypatch.setattr(agent_routes, "validate_agent_model_access", AsyncMock())
    response = await agent_routes.chat_stream(
        "search",
        AgentRequest(message="hello"),
        SimpleNamespace(base_url="https://test.local"),
        user=TokenPayload(sub="u1", username="test"),
    )
    iterator = response.body_iterator
    await anext(iterator)
    heartbeat.start.assert_awaited_once_with("r1", trace_id="t1")
    heartbeat.stop.assert_not_awaited()
    if not close_early:
        async for _ in iterator:
            pass
    await iterator.aclose()
    heartbeat.stop.assert_awaited_once_with("r1")

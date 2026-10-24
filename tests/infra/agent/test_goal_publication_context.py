"""Goal metadata and execution guards must compose with detached execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.agents.core import base as base_module
from src.infra.goal_runtime import (
    GOAL_RUN_LEASE,
    BackgroundLeaseCallback,
    GoalRunMetrics,
    GoalUsageCallback,
)
from src.kernel.schemas.session import clone_session_metadata
from tests.agents.core.test_base_agent_usage_cancellation import _FakePresenter, _TestAgent


def test_fork_does_not_inherit_goal_publication_revision():
    copied = clone_session_metadata(
        {
            "persistent_goal_id": "g",
            "persistent_goal_revision": 30,
            "persistent_goal_status": "paused",
            "persistent_goal_run_id": "r",
            "persistent_goal_version": 3,
            "agent_id": "fast",
        }
    )
    assert copied == {"agent_id": "fast"}


async def test_goal_usage_callback_preserves_background_ownership_guard(monkeypatch):
    from src.kernel.schemas.user import TokenPayload

    user = TokenPayload(sub="u", username="runner", roles=["runner"], permissions=["chat:write"])
    role = SimpleNamespace(id="role", name="runner", unrestricted_models=True)
    monkeypatch.setattr("src.api.deps._load_user_payload", AsyncMock(return_value=user))
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: SimpleNamespace(get_roles_by_names=AsyncMock(return_value=[role])),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: SimpleNamespace(
            get_role_agents_by_ids=AsyncMock(return_value={"role": ["base"]}),
            get_role_models_by_ids=AsyncMock(return_value={}),
        ),
    )
    monkeypatch.setattr(
        base_module.AgentFactory, "get_filtered_agents", AsyncMock(return_value=[{"id": "base"}])
    )
    captured = []

    class Graph:
        async def astream_events(self, _state, config, **_kwargs):
            captured.extend(config["callbacks"])
            if False:
                yield {}

    monkeypatch.setattr(base_module, "langfuse_tracer", SimpleNamespace(enabled=False))
    monkeypatch.setattr(
        base_module,
        "AgentEventProcessor",
        lambda *_args, **_kwargs: SimpleNamespace(
            finalize=AsyncMock(), emit_token_usage=AsyncMock()
        ),
    )
    monkeypatch.setattr(
        "src.infra.task.manager.BackgroundTaskManager.check_interrupt_fast", lambda _: False
    )
    agent = _TestAgent()
    agent._initialized = True
    agent._graph = Graph()
    presenter = _FakePresenter()
    presenter.persistent_goal_metrics = GoalRunMetrics()
    token = GOAL_RUN_LEASE.set({"kind": "background", "failure": "", "expires_at": float("inf")})
    try:
        async for _event in agent._stream("work", "s", "u", presenter=presenter):
            pass
    finally:
        GOAL_RUN_LEASE.reset(token)
    assert any(isinstance(callback, BackgroundLeaseCallback) for callback in captured)
    assert any(isinstance(callback, GoalUsageCallback) for callback in captured)

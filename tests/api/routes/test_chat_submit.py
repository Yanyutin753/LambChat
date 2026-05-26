from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers

from src.api.routes import chat as chat_module
from src.infra.task.concurrency import ConcurrencyResult
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.user import TokenPayload


@pytest.mark.asyncio
async def test_chat_stream_persists_visible_message_before_background_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    presenter_messages: list[str] = []

    class _FakeLimiter:
        async def acquire(self, **kwargs):
            return SimpleNamespace(result=ConcurrencyResult.STARTED)

    class _FakeExecutor:
        async def ensure_session(self, *args, **kwargs):
            return None

        async def _update_session_status(self, *args, **kwargs):
            return None

    class _FakeTaskManager:
        def __init__(self):
            self._run_info = {}
            self._executor = _FakeExecutor()
            self._heartbeat = None

        def _ensure_executor(self):
            return self._executor

        async def submit(self, **kwargs):
            captured.update(kwargs)
            return kwargs["run_id"], ""

    class _FakePresenter:
        def __init__(self, config):
            self.trace_id = "trace-1"

        async def _ensure_trace(self):
            return None

        async def emit_user_message(self, message: str, attachments=None):
            presenter_messages.append(message)

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_module, "get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter", lambda: _FakeLimiter()
    )
    monkeypatch.setattr(chat_module, "resolve_persona_request", _noop)
    monkeypatch.setattr(chat_module, "validate_agent_model_access", _noop)
    monkeypatch.setattr(chat_module, "_update_session_config", _noop)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr(
        "src.infra.writer.present.PresenterConfig",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    response = await chat_module.chat_stream(
        AgentRequest(message="hello"),
        SimpleNamespace(headers=Headers({"accept-language": "en"})),
        agent_id="search",
        user=TokenPayload(sub="user-1", username="tester", permissions=["chat:write"]),
    )

    assert response["status"] == "pending"
    assert presenter_messages == ["hello"]
    assert captured["user_message_written"] is True

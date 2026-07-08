from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.api.routes import chat as chat_routes
from src.infra.task.concurrency import ConcurrencyResult
from src.kernel.schemas.agent import AgentRequest


class _Request:
    headers: dict[str, str] = {}


class _User:
    sub = "user-1"
    roles: list[str] = []
    permissions: list[str] = ["chat:write"]


class _Session:
    metadata: dict = {}


class _SessionManager:
    async def get_session(self, session_id: str):
        return _Session()


class _Limiter:
    async def acquire(self, **kwargs):
        return type(
            "ConcurrencyResponse",
            (),
            {
                "result": ConcurrencyResult.STARTED,
                "queue_position": 0,
                "max_concurrent": 0,
                "active_count": 0,
                "queue_length": 0,
            },
        )()


class _TaskManager:
    def __init__(self) -> None:
        self.submit_kwargs: dict | None = None

    async def submit(self, **kwargs):
        self.submit_kwargs = kwargs
        return kwargs["run_id"], kwargs.get("trace_id") or "trace-1"


@pytest.fixture
def chat_stream_harness(monkeypatch: pytest.MonkeyPatch):
    manager = _TaskManager()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_routes, "SessionManager", lambda: _SessionManager())
    monkeypatch.setattr(chat_routes, "verify_session_ownership", lambda session, user: None)
    monkeypatch.setattr(chat_routes, "resolve_persona_request", _noop)
    monkeypatch.setattr(chat_routes, "validate_agent_model_access", _noop)
    monkeypatch.setattr(chat_routes, "_update_session_config", _noop)
    monkeypatch.setattr(chat_routes, "get_task_manager", lambda: manager)
    monkeypatch.setattr(chat_routes.settings, "TASK_BACKEND", "memory", raising=False)

    import src.infra.task.concurrency as concurrency

    monkeypatch.setattr(concurrency, "get_concurrency_limiter", lambda: _Limiter())
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retry_user_message", "expected_write", "expected_written"),
    [(False, True, False), (True, False, True)],
)
async def test_chat_stream_controls_user_message_write_for_retry(
    chat_stream_harness: _TaskManager,
    retry_user_message: bool,
    expected_write: bool,
    expected_written: bool,
) -> None:
    response = await chat_routes.chat_stream(
        AgentRequest(
            message="retry this prompt",
            session_id="session-1",
            retry_user_message=retry_user_message,
        ),
        http_request=_Request(),
        agent_id="fast",
        user=_User(),
    )

    assert response["status"] == "pending"
    assert chat_stream_harness.submit_kwargs is not None
    assert chat_stream_harness.submit_kwargs["display_message"] == "retry this prompt"
    assert chat_stream_harness.submit_kwargs["write_user_message_immediately"] is expected_write
    assert chat_stream_harness.submit_kwargs["user_message_written"] is expected_written


@pytest.mark.asyncio
async def test_chat_stream_requires_existing_session_for_retry() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await chat_routes.chat_stream(
            AgentRequest(message="retry", retry_user_message=True),
            http_request=_Request(),
            agent_id="fast",
            user=_User(),
        )

    assert getattr(exc_info.value, "status_code", None) == 400

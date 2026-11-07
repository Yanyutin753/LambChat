"""聊天链路 base_url 传递：排队/直发/arq 执行器必须把请求基址带给 Agent。

reveal_file 与产物投递按 configurable.base_url 生成文件 URL；排队执行路径
（chat.py 的 agent_stream 执行器）此前不传 base_url，APP_BASE_URL 未配置时
生成相对地址——Web 同源可用，打包客户端（webview origin 无意义）全部 404。
取值与既有 SSE 路由一致：优先 APP_BASE_URL，回退 request.base_url。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat, chat_agent_execution
from src.infra.task.concurrency import ConcurrencyResponse, ConcurrencyResult
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.user import TokenPayload


@pytest.fixture(autouse=True)
def ordinary_assistant_lookup(monkeypatch):
    from src.infra.assistant.store import AssistantStore

    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.infra.scheduler.results.append_result_context",
        AsyncMock(side_effect=lambda message, *args: message),
    )


def _http_request(
    base_url: str = "https://chat.example.com/",
) -> SimpleNamespace:
    return SimpleNamespace(headers={}, base_url=base_url)


class _Agent:
    def __init__(self) -> None:
        self.stream_kwargs: dict[str, Any] | None = None

    async def stream(self, *args: Any, **kwargs: Any):
        self.stream_kwargs = kwargs
        return
        yield  # pragma: no cover - 使其成为 async generator


async def test_execute_agent_stream_forwards_base_url_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _Agent()

    async def _get_agent(_agent_id: str) -> _Agent:
        return agent

    monkeypatch.setattr(chat_agent_execution.AgentFactory, "get", _get_agent)

    gen = chat._execute_agent_stream(
        "session-1",
        "fast",
        "hello",
        "user-1",
        base_url="https://chat.example.com",
    )
    async for _ in gen:
        pass

    assert agent.stream_kwargs is not None
    assert agent.stream_kwargs.get("base_url") == "https://chat.example.com"


@pytest.mark.parametrize("interrupted_resume", [False, True])
async def test_execute_agent_stream_preserves_recovery_mode(monkeypatch, interrupted_resume):
    agent = _Agent()
    monkeypatch.setattr(chat_agent_execution.AgentFactory, "get", AsyncMock(return_value=agent))
    async for _ in chat_agent_execution._execute_agent_stream(
        "session-1", "fast", "hello", "user-1", interrupted_resume=interrupted_resume
    ):
        pass
    assert agent.stream_kwargs["interrupted_resume"] is interrupted_resume


class _Limiter:
    def __init__(self, result: ConcurrencyResult) -> None:
        self.result = result
        self.acquire_calls: list[dict[str, Any]] = []

    async def acquire(self, **kwargs: Any) -> ConcurrencyResponse:
        self.acquire_calls.append(kwargs)
        return ConcurrencyResponse(
            result=self.result,
            queue_position=1,
            max_concurrent=1,
            active_count=1,
            queue_length=1,
        )

    async def release(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def remove_queued_run(self, *args: Any, **kwargs: Any) -> int:
        return 1

    async def mark_queued_run_ready(self, *args: Any, **kwargs: Any) -> bool:
        return True


class _Executor:
    def __init__(self):
        self.session_calls = []

    async def ensure_session(self, *args: Any, **kwargs: Any) -> None:
        self.session_calls.append(kwargs)
        return None

    async def _update_session_status(self, *args: Any, **kwargs: Any) -> None:
        return None


class _TaskManager:
    def __init__(self) -> None:
        self._executor = _Executor()
        self._run_info: dict[str, dict[str, Any]] = {}
        self.submit_calls: list[dict[str, Any]] = []
        self.submit_arq_calls: list[dict[str, Any]] = []

    async def submit(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_calls.append(kwargs)
        return kwargs["run_id"], kwargs["trace_id"]

    async def submit_arq(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_arq_calls.append(kwargs)
        return kwargs["run_id"], kwargs["trace_id"]


class _Presenter:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.trace_id = "trace-1"

    async def _ensure_trace(self) -> None:
        return None

    async def emit_user_message(self, *args: Any, **kwargs: Any) -> None:
        return None


async def _invoke_chat(
    monkeypatch: pytest.MonkeyPatch,
    *,
    limiter_result: ConcurrencyResult,
    task_backend: str = "local",
    app_base_url: str = "",
    http_request: SimpleNamespace | None = None,
    memory_append=None,
    session_id: str | None = None,
    project_id: str | None = None,
    identity_build=None,
    memory_permission=True,
    disabled_tools=None,
) -> _TaskManager:
    limiter = _Limiter(limiter_result)
    task_manager = _TaskManager()

    async def _noop_async(*args: Any, **kwargs: Any) -> None:
        return None

    def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(chat, "resolve_persona_request", _noop_async)
    monkeypatch.setattr(chat, "build_assistant_identity", identity_build or _noop_async)
    monkeypatch.setattr(chat, "validate_agent_model_access", _noop_async)
    monkeypatch.setattr(chat, "validate_user_agent_access", _noop_async)
    monkeypatch.setattr(chat, "validate_team_agent_request", _noop)
    monkeypatch.setattr(chat, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(chat, "_get_language", lambda request: "en")
    monkeypatch.setattr(chat, "_update_session_config", _noop_async)
    monkeypatch.setattr(chat, "Presenter", _Presenter, raising=False)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _Presenter)
    monkeypatch.setattr(chat.settings, "TASK_BACKEND", task_backend)
    monkeypatch.setattr(chat.settings, "APP_BASE_URL", app_base_url)
    monkeypatch.setattr("src.infra.task.concurrency.get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr("src.infra.task.manager._generate_run_id", lambda: "run-1")
    monkeypatch.setattr(chat, "_generate_run_id", lambda: "run-1", raising=False)
    if memory_append is not None:
        monkeypatch.setattr(chat, "append_memory_context", memory_append)

    request = AgentRequest(
        message="hello", session_id=session_id, project_id=project_id, disabled_tools=disabled_tools
    )
    await chat.chat_stream(
        request,
        http_request or _http_request(),
        user=TokenPayload(
            sub="owner-1",
            username="owner",
            roles=["member"],
            permissions=[
                "chat:write",
                "session:read",
                "session:write",
                "file:read",
                *(["memory:read"] if memory_permission else []),
            ],
        ),
    )
    return task_manager


@pytest.mark.parametrize(
    "task_backend,limiter_result",
    [
        ("local", ConcurrencyResult.STARTED),
        ("arq", ConcurrencyResult.STARTED),
        ("local", ConcurrencyResult.QUEUED),
    ],
)
@pytest.mark.parametrize("project_id", [None, "new-project"])
async def test_assistant_persists_configuration_before_a_worker_can_start(
    monkeypatch, task_backend, limiter_result, project_id
):
    from contextlib import asynccontextmanager

    from src.infra.assistant.service import AssistantService
    from src.infra.assistant.store import AssistantStore
    from src.infra.session.manager import SessionManager
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.assistant import Assistant

    @asynccontextmanager
    async def submission(*_args):
        yield

    monkeypatch.setattr(chat, "conversation_submission", submission)
    assistant = Assistant(
        id="helper",
        session_id="assistant-session",
        user_id="owner-1",
        name="Researcher",
        instructions="Verify sources",
        status="active",
        revision=1,
        project_id=project_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=assistant))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner-1", metadata={})),
    )
    monkeypatch.setattr(
        "src.infra.backend.workspace_selection.resolve_workspace_options",
        AsyncMock(return_value={}),
    )

    async def memory_context(message, *args, **kwargs):
        assert kwargs["project_id"] == "assistant-memory:helper", (
            "Assistant memory must stay separate from personal and project history"
        )
        return message

    manager = await _invoke_chat(
        monkeypatch,
        limiter_result=limiter_result,
        task_backend=task_backend,
        session_id="assistant-session",
        memory_append=memory_context,
    )
    if limiter_result == ConcurrencyResult.QUEUED:
        call = manager._executor.session_calls[0]
    else:
        call = (manager.submit_arq_calls if task_backend == "arq" else manager.submit_calls)[0]
    metadata = call["session_metadata"]
    assert metadata["executor_key"] == "assistant_stream"
    assert metadata["assistant_id"] == "helper"
    assert metadata["current_run_id"] == "run-1"
    assert metadata["agent_options"] == {}


async def test_chat_prepares_identity_and_model_context_concurrently_without_changing_payload(
    monkeypatch,
):
    import asyncio

    recalled = asyncio.Event()
    identity = {"seed": "persona", "name": "Persona", "avatar": None}

    async def build_identity(*args, **kwargs):
        await asyncio.sleep(0)
        assert recalled.is_set(), "identity lookup must overlap independent context recall"
        return identity

    async def recall(message, *args, **kwargs):
        recalled.set()
        return message + "\ncomplete memory hints"

    manager = await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        memory_append=recall,
        identity_build=build_identity,
    )
    submitted = manager.submit_calls[0]
    assert submitted["assistant_identity"] == identity
    assert submitted["message"].endswith("\ncomplete memory hints")
    assert submitted["display_message"] == "hello"


async def test_identity_error_keeps_priority_over_independent_context_error(monkeypatch):
    async def identity(*args, **kwargs):
        raise RuntimeError("identity unavailable")

    async def context(*args, **kwargs):
        raise ValueError("context unavailable")

    with pytest.raises(RuntimeError, match="identity unavailable"):
        await _invoke_chat(
            monkeypatch,
            limiter_result=ConcurrencyResult.STARTED,
            memory_append=context,
            identity_build=identity,
        )


async def test_identity_failure_does_not_wait_for_slow_context_and_leaves_no_recall_task(
    monkeypatch,
):
    import asyncio

    active = set()

    async def identity(*args, **kwargs):
        await asyncio.sleep(0)
        raise RuntimeError("identity unavailable")

    async def context(*args, **kwargs):
        task = asyncio.current_task()
        active.add(task)
        try:
            await asyncio.Event().wait()
        finally:
            active.discard(task)

    with pytest.raises(RuntimeError, match="identity unavailable"):
        await asyncio.wait_for(
            _invoke_chat(
                monkeypatch,
                limiter_result=ConcurrencyResult.STARTED,
                memory_append=context,
                identity_build=identity,
            ),
            timeout=0.2,
        )
    assert not active


async def test_chat_stream_appends_memory_to_model_message_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    async def _append(message: str, user_id: str, **kwargs: Any) -> str:
        calls.update({"message": message, "user_id": user_id, **kwargs})
        return f"{message}\n\n<memory_context>hint</memory_context>"

    task_manager = await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        memory_append=_append,
    )

    submitted = task_manager.submit_calls[0]
    assert submitted["message"].endswith("<memory_context>hint</memory_context>")
    assert submitted["display_message"] == "hello"
    assert calls["message"].endswith("hello")
    assert calls["user_id"] == "owner-1"
    assert calls["raw_query"] == "hello"
    assert calls["project_id"] is None
    assert calls["session_id"]


async def test_existing_session_uses_persisted_project_scope_for_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    async def _append(message: str, user_id: str, **kwargs: Any) -> str:
        calls.update({"message": message, "user_id": user_id, **kwargs})
        return message

    class _SessionManager:
        async def get_session(self, _session_id: str):
            return SimpleNamespace(user_id="owner-1", metadata={})

    monkeypatch.setattr(chat, "SessionManager", lambda: _SessionManager())
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _SessionManager())
    lease = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        renew=AsyncMock(return_value=True),
        release=AsyncMock(),
    )
    monkeypatch.setattr("src.infra.channel.chat_lease.ChatLease", lambda *_args, **_kwargs: lease)
    monkeypatch.setattr(chat, "verify_session_ownership", lambda *_args: None)

    await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        memory_append=_append,
        session_id="existing-session",
        project_id="untrusted-request-project",
    )

    assert calls["project_id"] is None
    assert calls["session_id"] == "existing-session"


async def test_chat_stream_passes_base_url_to_local_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = await _invoke_chat(monkeypatch, limiter_result=ConcurrencyResult.STARTED)
    assert task_manager.submit_calls, "STARTED 路径应调用 task_manager.submit"
    assert task_manager.submit_calls[0].get("base_url") == "https://chat.example.com"


async def test_chat_stream_prefers_app_base_url_over_request_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        app_base_url="https://lambchat.com",
    )
    assert task_manager.submit_calls[0].get("base_url") == "https://lambchat.com"


async def test_chat_stream_passes_empty_base_url_when_request_base_degenerate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        http_request=_http_request("http://None/"),
    )
    assert task_manager.submit_calls[0].get("base_url") == ""


async def test_chat_stream_passes_base_url_to_arq_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_manager = await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        task_backend="arq",
    )
    assert task_manager.submit_arq_calls, "arq 路径应调用 submit_arq"
    assert task_manager.submit_arq_calls[0].get("base_url") == "https://chat.example.com"


async def test_chat_stream_passes_base_url_in_queued_task_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter(ConcurrencyResult.QUEUED)

    async def _noop_async(*args: Any, **kwargs: Any) -> None:
        return None

    def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    task_manager = _TaskManager()
    monkeypatch.setattr(chat, "resolve_persona_request", _noop_async)
    monkeypatch.setattr(chat, "build_assistant_identity", _noop_async)
    monkeypatch.setattr(chat, "validate_agent_model_access", _noop_async)
    monkeypatch.setattr(chat, "validate_user_agent_access", _noop_async)
    monkeypatch.setattr(chat, "validate_team_agent_request", _noop)
    monkeypatch.setattr(chat, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(chat, "_get_language", lambda request: "en")
    monkeypatch.setattr(chat, "_update_session_config", _noop_async)
    monkeypatch.setattr(chat, "Presenter", _Presenter, raising=False)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _Presenter)
    monkeypatch.setattr(chat.settings, "TASK_BACKEND", "local")
    monkeypatch.setattr(chat.settings, "APP_BASE_URL", "")
    monkeypatch.setattr("src.infra.task.concurrency.get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr("src.infra.task.manager._generate_run_id", lambda: "run-1")
    monkeypatch.setattr(chat, "_generate_run_id", lambda: "run-1", raising=False)

    request = AgentRequest(message="hello")
    await chat.chat_stream(
        request,
        _http_request(),
        user=TokenPayload(
            sub="owner-1",
            username="owner",
            roles=["member"],
            permissions=["chat:write", "session:read", "session:write", "file:read"],
        ),
    )

    assert limiter.acquire_calls, "应经过并发限制器"
    task_context = limiter.acquire_calls[0]["task_context"]
    assert task_context.get("base_url") == "https://chat.example.com"


@pytest.mark.parametrize(
    "task_backend,limiter_result",
    [
        ("local", ConcurrencyResult.STARTED),
        ("arq", ConcurrencyResult.STARTED),
        ("local", ConcurrencyResult.QUEUED),
    ],
)
async def test_assistant_task_followup_authorizes_bound_execution_before_dispatch(
    monkeypatch, task_backend, limiter_result
):
    from contextlib import asynccontextmanager

    from src.infra.session.manager import SessionManager
    from src.infra.task.background_task_store import BackgroundTaskStore
    from src.infra.task.background_tasks import execute_background_stream
    from src.infra.utils.datetime import utc_now

    @asynccontextmanager
    async def submission(*args):
        yield

    monkeypatch.setattr(chat, "conversation_submission", submission)
    metadata = {"background_task_id": "task", "current_run_id": "old", "task_status": "completed"}
    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner-1", metadata=metadata)),
    )
    record = {
        "_id": "task",
        "user_id": "owner-1",
        "session_id": "child",
        "assistant_id": "helper",
        "parent_session_id": "coordinator",
        "run_id": "old",
        "state": "submitted",
        "agent_id": "search",
        "agent_options": {"sandbox": "cloud"},
        "config": {"project_id": None},
        "assistant_instructions": "Keep evidence",
        "created_at": utc_now(),
        "timeout_seconds": 300,
    }
    collection = SimpleNamespace(
        find_one=AsyncMock(return_value=record),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: collection))
    from src.infra.assistant.store import AssistantStore

    monkeypatch.setattr(
        AssistantStore,
        "get",
        AsyncMock(
            return_value=SimpleNamespace(
                id="helper", session_id="coordinator", memory_mode="private", status="active"
            )
        ),
    )

    async def memory_context(message, *args, **kwargs):
        assert kwargs["project_id"] == "assistant-memory:helper"
        return message

    manager = await _invoke_chat(
        monkeypatch,
        limiter_result=limiter_result,
        task_backend=task_backend,
        session_id="child",
        memory_append=memory_context,
    )
    call = (
        manager._executor.session_calls[0]
        if limiter_result == ConcurrencyResult.QUEUED
        else (manager.submit_arq_calls if task_backend == "arq" else manager.submit_calls)[0]
    )
    assert call["session_metadata"]["executor_key"] == "background_agent_stream"
    assert call["session_metadata"]["background_task_id"] == "task"
    assert call["session_metadata"]["project_id"] is None
    if limiter_result != ConcurrencyResult.QUEUED:
        assert call["persona_system_prompt"] == "Keep evidence"
        if task_backend == "local":
            assert call["executor"] is execute_background_stream
    assert collection.update_one.call_args.args[1]["$set"]["authorized_run_id"] == "run-1"


@pytest.mark.parametrize(
    "memory_permission,disabled_tools", [(False, []), (True, ["memory_recall"])]
)
async def test_assistant_context_cannot_bypass_memory_permissions_or_disabled_tools(
    monkeypatch, memory_permission, disabled_tools
):
    from contextlib import asynccontextmanager

    from src.infra.assistant.service import AssistantService
    from src.infra.assistant.store import AssistantStore
    from src.infra.session.manager import SessionManager
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.assistant import Assistant

    @asynccontextmanager
    async def submission(*_args):
        yield

    monkeypatch.setattr(chat, "conversation_submission", submission)
    assistant = Assistant(
        id="helper",
        session_id="assistant-session",
        user_id="owner-1",
        name="Researcher",
        status="active",
        revision=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=assistant))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner-1", metadata={})),
    )
    monkeypatch.setattr(
        "src.infra.backend.workspace_selection.resolve_workspace_options",
        AsyncMock(return_value={}),
    )
    recall = AsyncMock(side_effect=lambda message, *args, **kwargs: message)
    await _invoke_chat(
        monkeypatch,
        limiter_result=ConcurrencyResult.STARTED,
        session_id="assistant-session",
        memory_append=recall,
        memory_permission=memory_permission,
        disabled_tools=disabled_tools,
    )
    recall.assert_not_awaited()

"""聊天链路 base_url 传递：排队/直发/arq 执行器必须把请求基址带给 Agent。

reveal_file 与产物投递按 configurable.base_url 生成文件 URL；排队执行路径
（chat.py 的 agent_stream 执行器）此前不传 base_url，APP_BASE_URL 未配置时
生成相对地址——Web 同源可用，打包客户端（webview origin 无意义）全部 404。
取值与既有 SSE 路由一致：优先 APP_BASE_URL，回退 request.base_url。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes import chat
from src.infra.task.concurrency import ConcurrencyResponse, ConcurrencyResult
from src.kernel.schemas.agent import AgentRequest


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

    monkeypatch.setattr(chat, "AgentFactory", SimpleNamespace(get=_get_agent))

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
    async def ensure_session(self, *args: Any, **kwargs: Any) -> None:
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
) -> _TaskManager:
    limiter = _Limiter(limiter_result)
    task_manager = _TaskManager()

    async def _noop_async(*args: Any, **kwargs: Any) -> None:
        return None

    def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(chat, "resolve_persona_request", _noop_async)
    monkeypatch.setattr(chat, "validate_agent_model_access", _noop_async)
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

    request = AgentRequest(message="hello")
    await chat.chat_stream(
        request,
        http_request or _http_request(),
        user=SimpleNamespace(sub="owner-1", roles=["member"]),
    )
    return task_manager


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
    monkeypatch.setattr(chat, "validate_agent_model_access", _noop_async)
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
        user=SimpleNamespace(sub="owner-1", roles=["member"]),
    )

    assert limiter.acquire_calls, "应经过并发限制器"
    task_context = limiter.acquire_calls[0]["task_context"]
    assert task_context.get("base_url") == "https://chat.example.com"

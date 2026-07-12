from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.main_agent_context import (
    CompressibleMarkdownLog,
    MainAgentContextMiddleware,
)


@pytest.mark.asyncio
async def test_compressible_markdown_log_compresses_older_entries_and_keeps_recent() -> None:
    log = CompressibleMarkdownLog(
        token_limit=5,
        keep_recent=1,
        max_log_chars=10_000,
        compressed_heading="Earlier context",
    )
    log.append("first entry " + ("x" * 40))
    log.append("second entry")

    async def _compress(text: str) -> str:
        assert "first entry" in text
        assert "second entry" not in text
        return "summary of first entry"

    await log.check_and_compress(_compress)

    rendered = log.render("# Title\n")

    assert "## [COMPRESSED] Earlier context" in rendered
    assert "summary of first entry" in rendered
    assert "second entry" in rendered
    assert "first entry x" not in rendered


@pytest.mark.asyncio
async def test_main_agent_context_middleware_writes_context_file_for_task_call() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=f"/workflow/session{path}")

    class _Request(SimpleNamespace):
        def override(self, **overrides: Any):
            values = dict(self.__dict__)
            values.update(overrides)
            return _Request(**values)

    middleware = MainAgentContextMiddleware(
        backend=_Backend(),
        token_limit=10_000,
        run_id_factory=lambda: "ctx123",
    )
    request = _Request(
        runtime=SimpleNamespace(
            state={
                "messages": [
                    HumanMessage(content="Please inspect the auth flow"),
                    AIMessage(content="I will check the relevant files."),
                ]
            }
        ),
        state={},
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {
                "subagent_type": "general-purpose",
                "description": "Find auth regressions.",
            },
        },
    )
    captured_description = ""

    async def _handler(next_request: Any) -> str:
        nonlocal captured_description
        captured_description = next_request.tool_call["args"]["description"]
        return "ok"

    result = await middleware.awrap_tool_call(request, _handler)

    assert result == "ok"
    assert len(writes) == 1
    path, content = writes[0]
    assert path == "/subagent_context/main_agent_messages_ctx123.md"
    assert "Please inspect the auth flow" in content
    assert "I will check the relevant files" in content
    assert (
        "/workflow/session/subagent_context/main_agent_messages_ctx123.md" in captured_description
    )
    assert (
        "Read it when the assignment depends on prior user/main-agent context"
        in captured_description
    )


@pytest.mark.asyncio
async def test_main_agent_context_middleware_writes_context_under_backend_workspace() -> None:
    writes: list[tuple[str, str]] = []

    class _DefaultBackend:
        work_dir = "/sandbox/sessions/session-1"

    class _Backend:
        default = _DefaultBackend()

        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    class _Request(SimpleNamespace):
        def override(self, **overrides: Any):
            values = dict(self.__dict__)
            values.update(overrides)
            return _Request(**values)

    middleware = MainAgentContextMiddleware(
        backend=_Backend(),
        token_limit=10_000,
        run_id_factory=lambda: "ctxsandbox",
    )
    request = _Request(
        runtime=SimpleNamespace(
            state={"messages": [HumanMessage(content="Use the sandbox workspace")]},
        ),
        state={},
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {
                "subagent_type": "general-purpose",
                "description": "Inspect sandbox state.",
            },
        },
    )

    async def _handler(next_request: Any) -> str:
        return next_request.tool_call["args"]["description"]

    description = await middleware.awrap_tool_call(request, _handler)

    assert len(writes) == 1
    assert (
        writes[0][0]
        == "/sandbox/sessions/session-1/subagent_context/main_agent_messages_ctxsandbox.md"
    )
    assert (
        "/sandbox/sessions/session-1/subagent_context/main_agent_messages_ctxsandbox.md"
        in description
    )


@pytest.mark.asyncio
async def test_main_agent_context_middleware_continues_when_compression_fails() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    class _Request(SimpleNamespace):
        def override(self, **overrides: Any):
            values = dict(self.__dict__)
            values.update(overrides)
            return _Request(**values)

    middleware = MainAgentContextMiddleware(
        backend=_Backend(),
        token_limit=1,
        keep_recent=1,
        run_id_factory=lambda: "ctxfail",
    )

    async def _raise(_text: str) -> str:
        raise RuntimeError("llm unavailable")

    middleware._compress_with_llm = _raise
    request = _Request(
        runtime=SimpleNamespace(
            state={
                "messages": [
                    HumanMessage(content="older context " + ("x" * 40)),
                    HumanMessage(content="latest context"),
                ]
            }
        ),
        state={},
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {"subagent_type": "general-purpose", "description": "Work."},
        },
    )
    called = False

    async def _handler(next_request: Any) -> str:
        nonlocal called
        called = True
        assert "main_agent_messages_ctxfail.md" in next_request.tool_call["args"]["description"]
        return "ok"

    result = await middleware.awrap_tool_call(request, _handler)

    assert result == "ok"
    assert called is True
    assert len(writes) == 1
    assert "latest context" in writes[0][1]


@pytest.mark.asyncio
async def test_main_agent_context_middleware_reuses_snapshot_for_same_message_state() -> None:
    writes: list[tuple[str, str]] = []
    ids = iter(["first", "second"])

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    class _Request(SimpleNamespace):
        def override(self, **overrides: Any):
            values = dict(self.__dict__)
            values.update(overrides)
            return _Request(**values)

    messages = [HumanMessage(content="shared context")]
    runtime = SimpleNamespace(state={"messages": messages})
    middleware = MainAgentContextMiddleware(
        backend=_Backend(),
        token_limit=10_000,
        run_id_factory=lambda: next(ids),
    )

    async def _handler(next_request: Any) -> str:
        return next_request.tool_call["args"]["description"]

    first = await middleware.awrap_tool_call(
        _Request(
            runtime=runtime,
            state={},
            tool_call={
                "id": "call-1",
                "name": "task",
                "args": {"subagent_type": "general-purpose", "description": "First."},
            },
        ),
        _handler,
    )
    second = await middleware.awrap_tool_call(
        _Request(
            runtime=runtime,
            state={},
            tool_call={
                "id": "call-2",
                "name": "task",
                "args": {"subagent_type": "general-purpose", "description": "Second."},
            },
        ),
        _handler,
    )

    assert len(writes) == 1
    assert "main_agent_messages_first.md" in first
    assert "main_agent_messages_first.md" in second


@pytest.mark.asyncio
async def test_main_agent_context_middleware_redacts_common_secret_values() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    class _Request(SimpleNamespace):
        def override(self, **overrides: Any):
            values = dict(self.__dict__)
            values.update(overrides)
            return _Request(**values)

    middleware = MainAgentContextMiddleware(
        backend=_Backend(),
        token_limit=10_000,
        run_id_factory=lambda: "secrets",
    )
    request = _Request(
        runtime=SimpleNamespace(
            state={
                "messages": [
                    HumanMessage(
                        content=(
                            "Authorization: Bearer abc.def.ghi\n"
                            "api_key=sk-live-secret\n"
                            "password: hunter2"
                        )
                    )
                ]
            }
        ),
        state={},
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {"subagent_type": "general-purpose", "description": "Check."},
        },
    )

    async def _handler(_request: Any) -> str:
        return "ok"

    await middleware.awrap_tool_call(request, _handler)

    content = writes[0][1]
    assert "abc.def.ghi" not in content
    assert "sk-live-secret" not in content
    assert "hunter2" not in content
    assert "[REDACTED]" in content

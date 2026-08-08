from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, ClassVar, Sequence

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from src.agents.search_agent import nodes as search_nodes
from src.agents.search_agent.context import SearchAgentContext
from src.agents.search_agent.graph import SearchAgent
from src.infra.agent.middleware.main_agent_context import write_subagent_handoff_file
from src.infra.backend.lazy_sandbox import LazySandboxBackend
from src.infra.writer.present import Presenter, PresenterConfig


class _RecordingPresenter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit_sandbox_starting(self) -> None:
        self.events.append(("starting", {}))

    async def emit_sandbox_ready(self, sandbox_id: str, work_dir: str) -> None:
        self.events.append(("ready", {"sandbox_id": sandbox_id, "work_dir": work_dir}))

    async def emit_sandbox_error(self, error: str) -> None:
        self.events.append(("error", {"error": error}))


class _RecordingSandbox(BaseSandbox):
    def __init__(self, work_dir: str = "/provider/session-1") -> None:
        self.work_dir = work_dir
        self.files: dict[str, str] = {}
        self.write_calls: list[tuple[str, str]] = []
        self.glob_calls: list[tuple[str, str | None]] = []

    @property
    def id(self) -> str:
        return "provider-sandbox-1"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del command, timeout
        return ExecuteResponse(output="", exit_code=0, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path) for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=path, content=b"") for path in paths]

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        self.write_calls.append((file_path, content))
        self.files[file_path] = content
        return WriteResult(path=file_path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        self.glob_calls.append((pattern, path))
        matches: list[FileInfo] = [
            {
                "path": file_path,
                "is_dir": False,
                "size": len(content),
                "modified_at": "2026-08-09T00:00:00Z",
            }
            for file_path, content in self.files.items()
            if path is None or file_path.startswith(path.rstrip("/") + "/")
        ]
        return GlobResult(matches=matches)


class _RecordingManager:
    def __init__(self, sandbox: _RecordingSandbox) -> None:
        self.sandbox = sandbox
        self.calls: list[tuple[str, str]] = []

    async def get_or_create(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> tuple[CompositeBackend, str]:
        self.calls.append((session_id, user_id))
        return CompositeBackend(default=self.sandbox, routes={}), self.sandbox.work_dir


class _RouteBackend:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []

    async def awrite(self, path: str, content: str) -> WriteResult:
        self.writes.append((path, content))
        return WriteResult(path=path)


class _ScriptedChatModel(BaseChatModel):
    mode: str
    calls: ClassVar[list[list[tuple[str, str]]]] = []
    call_count: ClassVar[int] = 0

    @property
    def _llm_type(self) -> str:
        return "search-lazy-scripted"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | Any] | None = None,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> _ScriptedChatModel:
        del tools, tool_choice, kwargs
        return self

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.call_count = 0

    def _next_message(self, messages: list[BaseMessage]) -> AIMessage:
        type(self).call_count += 1
        type(self).calls.append([(message.type, str(message.content)) for message in messages])
        if self.mode == "model-only":
            return AIMessage(content="model-only final")
        if self.mode == "write-file":
            if any(isinstance(message, ToolMessage) for message in messages):
                return AIMessage(content="write final")
            return AIMessage(
                content="content before tool",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/workspace/session-1/result.tmp",
                            "content": "result",
                        },
                        "id": "write-1",
                        "type": "tool_call",
                    }
                ],
            )
        if self.mode == "subagent":
            match type(self).call_count:
                case 1:
                    return AIMessage(
                        content="delegating",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "description": "Inspect the workspace",
                                    "prompt": "Return a short report without using tools.",
                                    "subagent_type": "general-purpose",
                                },
                                "id": "task-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                case 2:
                    return AIMessage(content="subagent report")
                case _:
                    return AIMessage(content="subagent final")
        raise AssertionError(f"unsupported model mode: {self.mode}")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self._next_message(messages))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, kwargs
        message = self._next_message(messages)
        if run_manager is not None:
            chunk = AIMessageChunk(
                content=message.content,
                tool_call_chunks=[
                    {
                        "name": call["name"],
                        "args": json.dumps(call["args"]),
                        "id": call["id"],
                        "index": index,
                        "type": "tool_call_chunk",
                    }
                    for index, call in enumerate(message.tool_calls)
                ],
            )
            await run_manager.on_llm_new_token(
                str(message.content),
                chunk=ChatGenerationChunk(message=chunk),
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _TimelinePresenter(Presenter):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__(
            PresenterConfig(
                session_id="session-1",
                agent_id="search",
                agent_name="Search Agent",
                user_id="user-1",
                enable_storage=False,
            )
        )
        self.timeline = timeline

    async def build_langsmith_metadata(self, _context=None) -> dict[str, Any]:
        return {}

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        self.timeline.append(str(event["event"]))
        if event["event"] == "message:chunk":
            self.timeline.append(f"content:{event.get('data', {}).get('content', '')}")
        return await super().emit(event)

    async def emit_sandbox_starting(self) -> dict[str, Any]:
        self.timeline.append("sandbox:starting")
        return await super().emit_sandbox_starting()

    async def emit_sandbox_ready(
        self, sandbox_id: str, work_dir: str | None = None
    ) -> dict[str, Any]:
        self.timeline.append("sandbox:ready")
        return await super().emit_sandbox_ready(sandbox_id, work_dir)


def _patch_graph_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model: _ScriptedChatModel,
    manager_factory,
    timeline: list[str],
) -> None:
    async def fake_setup(self: SearchAgentContext) -> None:
        del self

    original_close = SearchAgentContext.close

    async def recording_close(self: SearchAgentContext) -> None:
        lazy = getattr(self, "run_sandbox", None)
        if lazy is not None:
            timeline.append(f"context:closing:{lazy.id}")
        await original_close(self)
        timeline.append("context:closed")

    async def fake_get_model(**_kwargs: Any) -> _ScriptedChatModel:
        return model

    async def fake_checkpointer(**_kwargs: Any) -> MemorySaver:
        return MemorySaver()

    async def fake_store() -> InMemoryStore:
        return InMemoryStore()

    async def fake_emit_token_usage(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def fake_env_var_prompt_sections(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return ()

    from src.infra.tool import env_var_prompt

    original_artifact_init = search_nodes.ArtifactDeliveryMiddleware.__init__

    def recording_artifact_init(self: Any, *args: Any, **kwargs: Any) -> None:
        timeline.append(f"artifact-workspace:{kwargs.get('workspace_path')}")
        original_artifact_init(self, *args, **kwargs)

    monkeypatch.setattr(SearchAgentContext, "setup", fake_setup)
    monkeypatch.setattr(SearchAgentContext, "close", recording_close)
    monkeypatch.setattr(search_nodes.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(search_nodes, "get_async_checkpointer", fake_checkpointer)
    monkeypatch.setattr(search_nodes, "acreate_store", fake_store)
    monkeypatch.setattr(search_nodes, "emit_token_usage", fake_emit_token_usage)
    monkeypatch.setattr(
        env_var_prompt,
        "build_env_var_prompt_sections",
        fake_env_var_prompt_sections,
    )
    monkeypatch.setattr(
        search_nodes.ArtifactDeliveryMiddleware,
        "__init__",
        recording_artifact_init,
    )
    monkeypatch.setattr(search_nodes, "get_session_sandbox_manager", manager_factory)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_SANDBOX", True)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_SKILLS", False)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_MCP", False)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", False)


async def _run_search_graph(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_mode: str,
    manager_factory,
) -> tuple[list[dict[str, Any]], list[str], _ScriptedChatModel]:
    timeline: list[str] = []
    model = _ScriptedChatModel(mode=model_mode)
    model.reset()
    _patch_graph_dependencies(
        monkeypatch,
        model=model,
        manager_factory=manager_factory,
        timeline=timeline,
    )
    presenter = _TimelinePresenter(timeline)
    agent = SearchAgent()
    events: list[dict[str, Any]] = []
    async for event in agent._stream(
        "hello",
        "session-1",
        user_id="user-1",
        presenter=presenter,
        agent_options={
            "_resolved_fallback_model": None,
            "_resolved_supports_vision": False,
            "_resolved_image_url_to_base64": False,
        },
    ):
        events.append(event)
        timeline.append(f"yield:{event['event']}")
    return events, timeline, model


def _replace_routes(backend: CompositeBackend) -> dict[str, _RouteBackend]:
    routes = {prefix: _RouteBackend() for prefix in ("/skills/", "/memories/")}
    backend.routes = routes
    backend.sorted_routes = sorted(routes.items(), key=lambda item: len(item[0]), reverse=True)
    return routes


async def _create_search_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    presenter: _RecordingPresenter,
    manager_factory,
) -> tuple[CompositeBackend, LazySandboxBackend, SearchAgentContext, str | None]:
    async def fake_store() -> object:
        return object()

    monkeypatch.setattr(search_nodes, "acreate_store", fake_store)
    monkeypatch.setattr(search_nodes, "get_session_sandbox_manager", manager_factory)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_SANDBOX", True)

    context = SearchAgentContext(session_id="session-1", user_id="user-1")
    backend, _prompt, _store, lazy, work_dir = await search_nodes._create_backend_and_prompt(
        state={"session_id": "session-1"},
        context=context,
        presenter=presenter,  # type: ignore[arg-type]
        assistant_id="assistant-user-1",
    )
    assert isinstance(backend, CompositeBackend)
    assert isinstance(lazy, LazySandboxBackend)
    return backend, lazy, context, work_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["e2b", "cubesandbox", "daytona"])
async def test_search_backend_construction_is_provider_neutral_and_lazy(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    presenter = _RecordingPresenter()
    manager = _RecordingManager(_RecordingSandbox())
    manager_factory_calls = 0

    def manager_factory() -> _RecordingManager:
        nonlocal manager_factory_calls
        manager_factory_calls += 1
        return manager

    monkeypatch.setattr(search_nodes.settings, "SANDBOX_PLATFORM", platform)
    backend, lazy, context, work_dir = await _create_search_backend(
        monkeypatch,
        presenter=presenter,
        manager_factory=manager_factory,
    )

    assert manager_factory_calls == 0
    assert backend.default is lazy
    assert backend.artifacts_root == "/workspace/session-1"
    assert lazy.work_dir == work_dir == "/workspace/session-1"
    assert presenter.events == []
    assert context.run_sandbox is lazy

    result = await backend.awrite("/workspace/session-1/report.txt", "report")

    assert manager_factory_calls == 1
    assert manager.calls == [("session-1", "user-1")]
    assert result.path == "/workspace/session-1/report.txt"
    assert manager.sandbox.write_calls == [("/provider/session-1/report.txt", "report")]
    assert presenter.events == [
        ("starting", {}),
        (
            "ready",
            {"sandbox_id": "provider-sandbox-1", "work_dir": "/provider/session-1"},
        ),
    ]


@pytest.mark.asyncio
async def test_outer_composite_routes_virtual_files_without_initializing_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = _RecordingPresenter()

    def manager_factory() -> _RecordingManager:
        raise AssertionError("virtual routes must not initialize the sandbox")

    backend, lazy, _context, _work_dir = await _create_search_backend(
        monkeypatch,
        presenter=presenter,
        manager_factory=manager_factory,
    )
    routes = _replace_routes(backend)

    skills_result = await backend.awrite("/skills/demo/SKILL.md", "skill")
    memories_result = await backend.awrite("/memories/note.md", "memory")

    assert skills_result.path == "/skills/demo/SKILL.md"
    assert memories_result.path == "/memories/note.md"
    assert routes["/skills/"].writes == [("/demo/SKILL.md", "skill")]
    assert routes["/memories/"].writes == [("/note.md", "memory")]
    assert lazy.id == "pending"
    assert presenter.events == []


@pytest.mark.asyncio
async def test_artifact_snapshot_and_subagent_handoff_share_one_lazy_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = _RecordingPresenter()
    manager = _RecordingManager(_RecordingSandbox())
    manager_factory_calls = 0

    def manager_factory() -> _RecordingManager:
        nonlocal manager_factory_calls
        manager_factory_calls += 1
        return manager

    backend, _lazy, _context, _work_dir = await _create_search_backend(
        monkeypatch,
        presenter=presenter,
        manager_factory=manager_factory,
    )

    await backend.awrite(f"{backend.artifacts_root}/artifact.txt", "artifact")
    snapshot = await backend.aglob("**/*", backend.artifacts_root)
    handoff_path = await write_subagent_handoff_file(
        backend,
        dirname="subagent_reports",
        filename="handoff.md",
        content="handoff",
        log_context="test",
    )

    assert manager_factory_calls == 1
    assert manager.calls == [("session-1", "user-1")]
    assert [call[0] for call in manager.sandbox.write_calls] == [
        "/provider/session-1/artifact.txt",
        "/provider/session-1/subagent_reports/handoff.md",
    ]
    assert manager.sandbox.glob_calls == [("**/*", "/provider/session-1")]
    assert [info["path"] for info in snapshot.matches or []] == [
        "/workspace/session-1/artifact.txt"
    ]
    assert handoff_path == "/workspace/session-1/subagent_reports/handoff.md"


@pytest.mark.asyncio
async def test_disabled_sandbox_keeps_persistent_backend_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistent = object()

    async def fake_store() -> object:
        return object()

    monkeypatch.setattr(search_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(search_nodes, "acreate_store", fake_store)
    monkeypatch.setattr(
        search_nodes,
        "create_persistent_backend",
        lambda assistant_id, user_id, session_id: (
            persistent,
            assistant_id,
            user_id,
            session_id,
        ),
    )
    monkeypatch.setattr(
        search_nodes,
        "get_session_sandbox_manager",
        lambda: (_ for _ in ()).throw(AssertionError("sandbox manager must stay unused")),
    )

    backend, prompt, _store, sandbox, work_dir = await search_nodes._create_backend_and_prompt(
        state={"session_id": "session-1"},
        context=SearchAgentContext(session_id="session-1"),
        presenter=SimpleNamespace(),
        assistant_id="assistant-default",
    )

    assert backend == (persistent, "assistant-default", "default", "session-1")
    assert prompt == search_nodes.DEFAULT_SYSTEM_PROMPT
    assert sandbox is None
    assert work_dir is None


@pytest.mark.asyncio
async def test_search_stream_model_only_never_initializes_and_closes_before_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def manager_factory() -> _RecordingManager:
        raise AssertionError("model-only run must not obtain the sandbox manager")

    events, timeline, _model = await _run_search_graph(
        monkeypatch,
        model_mode="model-only",
        manager_factory=manager_factory,
    )

    assert events[-1]["event"] == "done"
    assert "content:model-only final" in timeline
    assert not any(item.startswith("sandbox:") for item in timeline)
    artifact_workspaces = [item for item in timeline if item.startswith("artifact-workspace:")]
    assert len(artifact_workspaces) >= 2
    assert set(artifact_workspaces) == {"artifact-workspace:/workspace/session-1"}
    assert "context:closing:pending" in timeline
    assert timeline.index("context:closed") < timeline.index("yield:done")


@pytest.mark.asyncio
async def test_search_stream_first_write_initializes_after_pre_tool_content_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events_timeline: list[str] = []
    manager = _RecordingManager(_RecordingSandbox())

    def manager_factory() -> _RecordingManager:
        events_timeline.append("manager:requested")
        return manager

    model = _ScriptedChatModel(mode="write-file")
    model.reset()
    _patch_graph_dependencies(
        monkeypatch,
        model=model,
        manager_factory=manager_factory,
        timeline=events_timeline,
    )
    presenter = _TimelinePresenter(events_timeline)
    agent = SearchAgent()
    events: list[dict[str, Any]] = []
    async for event in agent._stream(
        "write a file",
        "session-1",
        user_id="user-1",
        presenter=presenter,
        agent_options={
            "_resolved_fallback_model": None,
            "_resolved_supports_vision": False,
            "_resolved_image_url_to_base64": False,
        },
    ):
        events.append(event)
        events_timeline.append(f"yield:{event['event']}")

    assert "content:content before tool" in events_timeline
    assert "content:write final" in events_timeline
    assert events_timeline.index("message:chunk") < events_timeline.index("sandbox:starting")
    assert events_timeline.count("sandbox:starting") == 1
    assert events_timeline.count("sandbox:ready") == 1
    assert events_timeline.count("manager:requested") == 1
    assert events_timeline.index("sandbox:starting") < events_timeline.index("manager:requested")
    assert events_timeline.index("manager:requested") < events_timeline.index("sandbox:ready")
    assert manager.calls == [("session-1", "user-1")]
    assert manager.sandbox.write_calls == [("/provider/session-1/result.tmp", "result")]


@pytest.mark.asyncio
async def test_search_stream_subagent_receives_public_workspace_before_handoff_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    manager = _RecordingManager(_RecordingSandbox())

    def manager_factory() -> _RecordingManager:
        timeline.append("manager:requested")
        return manager

    events, graph_timeline, model = await _run_search_graph(
        monkeypatch,
        model_mode="subagent",
        manager_factory=manager_factory,
    )

    assert events[-1]["event"] == "done"
    assert len(model.calls) >= 3
    main_prompt = "\n".join(content for _kind, content in model.calls[0])
    subagent_prompt = "\n".join(content for _kind, content in model.calls[1])
    assert "/workspace/session-1" in main_prompt
    assert "/workspace/session-1" in subagent_prompt
    artifact_workspaces = [
        item for item in graph_timeline if item.startswith("artifact-workspace:")
    ]
    assert len(artifact_workspaces) >= 2
    assert set(artifact_workspaces) == {"artifact-workspace:/workspace/session-1"}
    assert graph_timeline.count("sandbox:starting") == 1
    assert graph_timeline.count("sandbox:ready") == 1
    assert timeline == ["manager:requested"]
    assert manager.calls == [("session-1", "user-1")]
    written_paths = [path for path, _content in manager.sandbox.write_calls]
    assert any(path.startswith("/provider/session-1/subagent_context/") for path in written_paths)
    assert any(path.startswith("/provider/session-1/subagent_reports/") for path in written_paths)


def test_uninitialized_lazy_backend_rejects_sync_file_operations() -> None:
    backend = LazySandboxBackend(
        session_id="session-1",
        user_id="user-1",
        presenter=_RecordingPresenter(),
        manager_factory=lambda: (_ for _ in ()).throw(
            AssertionError("sync operation must not obtain manager")
        ),
    )

    with pytest.raises(RuntimeError, match="use async operations first"):
        backend.write("/workspace/session-1/result.txt", "result")

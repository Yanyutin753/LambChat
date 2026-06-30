import json
from types import SimpleNamespace
from typing import Any, ClassVar, Sequence

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from src.infra.agent.middleware.artifact_delivery import ArtifactDeliveryMiddleware
from src.infra.tool import reveal_file_tool


class FakeFileSnapshotBackend:
    def __init__(self, before, after):
        self._snapshots = [before, after]
        self.calls: list[tuple[str, str]] = []

    async def aglob_info(self, pattern: str, path: str = "/"):
        self.calls.append((pattern, path))
        return self._snapshots.pop(0)


class FakeDownloadBackend:
    async def aget_file_size(self, _path: str) -> int:
        return 9

    async def adownload_files(self, paths):
        return [
            SimpleNamespace(
                path=paths[0],
                content=b"pdf-bytes",
                error=None,
            )
        ]


class WriteFileChatModel(BaseChatModel):
    calls: ClassVar[int] = 0

    @property
    def _llm_type(self) -> str:
        return "write-file-chat"

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict | Any] | None = None,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> "WriteFileChatModel":
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        type(self).calls += 1
        if type(self).calls == 1:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "write_file",
                                    "args": {
                                        "file_path": "/workspace/cute_dog.svg",
                                        "content": "<svg/>",
                                    },
                                    "id": "write-1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.mark.asyncio
async def test_artifact_delivery_flush_deduplicates_paths_and_reveals_latest() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps(
            {
                "key": "revealed/report.pdf",
                "url": "/api/upload/file/revealed/report.pdf",
                "name": "report.pdf",
                "type": "document",
                "mime_type": "application/pdf",
                "size": 123,
                "_meta": {
                    "path": kwargs["file_path"],
                    "description": kwargs.get("description") or "",
                },
            }
        )

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def write_handler(request):
        return ToolMessage(content="ok", tool_call_id=request.tool_call["id"], name="write_file")

    async def edit_handler(request):
        return ToolMessage(
            content="updated", tool_call_id=request.tool_call["id"], name="edit_file"
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {
                    "file_path": "/workspace/report.pdf",
                    "content": "draft",
                },
            },
            runtime=SimpleNamespace(config={}),
        ),
        write_handler,
    )
    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "edit_file",
                "id": "edit-1",
                "args": {
                    "path": "/workspace/report.pdf",
                    "old_string": "draft",
                    "new_string": "final",
                },
            },
            runtime=SimpleNamespace(config={}),
        ),
        edit_handler,
    )

    update = await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls[0]["file_path"] == "/workspace/report.pdf"
    assert reveal_calls[0]["description"] == "File modified by the agent"
    assert getattr(reveal_calls[0]["runtime"], "config") == {
        "configurable": {"delivery_source": "artifact_auto"}
    }
    messages = update["messages"]
    assert messages == []


@pytest.mark.asyncio
async def test_artifact_delivery_indexes_auto_delivered_file_in_file_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    indexed_calls: list[dict] = []

    class FakeStorage:
        async def upload_file(
            self,
            *,
            file,
            folder: str,
            filename: str,
            content_type: str,
            skip_size_limit: bool = False,
        ):
            del file, skip_size_limit
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url=f"https://storage.example.com/{folder}/{filename}",
                content_type=content_type,
                size=9,
            )

    class FakeIndex:
        async def upsert_by_name(self, **kwargs):
            indexed_calls.append(kwargs)

    async def get_storage():
        return FakeStorage()

    async def lookup_session_project_id(_session_id):
        return None

    monkeypatch.setattr(reveal_file_tool, "_get_storage", get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: FakeIndex())
    monkeypatch.setattr(reveal_file_tool, "_lookup_session_project_id", lookup_session_project_id)

    middleware = ArtifactDeliveryMiddleware()
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "backend": FakeDownloadBackend(),
                "base_url": "https://app.example.com",
                "context": SimpleNamespace(user_id="user-1", session_id="session-1"),
                "trace_id": "trace-1",
            }
        }
    )

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/report.pdf", "content": "report"},
            },
            runtime=runtime,
        ),
        handler,
    )

    await middleware.aafter_agent({"messages": []}, runtime)

    assert indexed_calls == [
        {
            "user_id": "user-1",
            "file_name": "report.pdf",
            "source": "reveal_file",
            "file_key": "revealed_files/report.pdf",
            "trace_id": "trace-1",
            "data": {
                "file_type": "document",
                "mime_type": "application/pdf",
                "file_size": 9,
                "url": "https://app.example.com/api/upload/file/revealed_files/report.pdf",
                "session_id": "session-1",
                "project_id": None,
                "description": "File created by the agent",
                "original_path": "/workspace/report.pdf",
                "delivery_source": "artifact_auto",
            },
        }
    ]


@pytest.mark.asyncio
async def test_artifact_delivery_captures_deepagent_builtin_write_file() -> None:
    WriteFileChatModel.calls = 0
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps(
            {
                "key": "revealed_files/cute_dog.svg",
                "url": "https://app.example.com/api/upload/file/revealed_files/cute_dog.svg",
                "name": "cute_dog.svg",
                "type": "image",
                "mime_type": "image/svg+xml",
                "size": 6,
                "_meta": {"path": kwargs["file_path"]},
            }
        )

    graph = create_deep_agent(
        model=WriteFileChatModel(),
        middleware=[ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)],
        checkpointer=MemorySaver(),
    )

    async for _event in graph.astream_events(
        {"messages": [{"role": "user", "content": "make svg"}]},
        {"configurable": {"thread_id": "artifact-write-test"}, "recursion_limit": 20},
        version="v2",
    ):
        pass

    assert [call["file_path"] for call in reveal_calls] == ["/workspace/cute_dog.svg"]


@pytest.mark.asyncio
async def test_artifact_delivery_skips_already_revealed_path() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return "{}"

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def write_handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/chart.png", "content": "png"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        write_handler,
    )

    async def reveal_handler(_request):
        return ToolMessage(
            content=json.dumps(
                {
                    "key": "revealed/chart.png",
                    "url": "/api/upload/file/revealed/chart.png",
                    "name": "chart.png",
                    "_meta": {"path": "/workspace/chart.png"},
                }
            ),
            tool_call_id="reveal-1",
            name="reveal_file",
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "reveal_file",
                "id": "reveal-1",
                "args": {"file_path": "/workspace/chart.png"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        reveal_handler,
    )

    update = await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_deduplicates_external_url_after_direct_reveal() -> None:
    reveal_calls: list[dict] = []
    external_url = "https://cdn.example.com/assets/image.png"

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return "{}"

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def reveal_handler(_request):
        return ToolMessage(
            content=json.dumps(
                {
                    "key": external_url,
                    "url": external_url,
                    "name": "image.png",
                    "_meta": {"path": external_url},
                }
            ),
            tool_call_id="reveal-url",
            name="reveal_file",
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "reveal_file",
                "id": "reveal-url",
                "args": {"file_path": external_url},
            },
            runtime=SimpleNamespace(config={}),
        ),
        reveal_handler,
    )

    update = await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_emits_presenter_events_during_flush() -> None:
    emitted: list[dict] = []

    class FakePresenter:
        async def emit(self, event):
            emitted.append(event)

        def present_artifact_result(
            self,
            artifact,
            *,
            success=True,
            error=None,
            depth=0,
            agent_id=None,
        ):
            return {
                "event": "artifact:result",
                "data": {
                    "artifact": artifact,
                    "success": success,
                    "error": error,
                    "depth": depth,
                    "agent_id": agent_id,
                },
            }

    async def fake_reveal_file(**kwargs):
        return json.dumps(
            {
                "key": "revealed/report.pdf",
                "url": "/api/upload/file/revealed/report.pdf",
                "name": "report.pdf",
                "_meta": {"path": kwargs["file_path"]},
            }
        )

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/report.pdf", "content": "report"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    await middleware.aafter_agent(
        {"messages": []},
        SimpleNamespace(
            config={"configurable": {"presenter": FakePresenter()}},
        ),
    )

    assert [event["event"] for event in emitted] == ["artifact:result"]
    assert emitted[0]["data"]["artifact"]["kind"] == "file"
    assert emitted[0]["data"]["artifact"]["path"] == "/workspace/report.pdf"
    assert emitted[0]["data"]["artifact"]["preview"]["previewKey"] == "revealed/report.pdf"


@pytest.mark.asyncio
async def test_artifact_delivery_emits_artifact_when_write_file_finishes() -> None:
    emitted: list[dict] = []
    reveal_calls: list[dict] = []

    class FakePresenter:
        async def emit(self, event):
            emitted.append(event)

        def present_artifact_result(
            self,
            artifact,
            *,
            success=True,
            error=None,
            depth=0,
            agent_id=None,
        ):
            return {
                "event": "artifact:result",
                "data": {
                    "artifact": artifact,
                    "success": success,
                    "error": error,
                    "depth": depth,
                    "agent_id": agent_id,
                },
            }

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps(
            {
                "key": "revealed/cute_dog.svg",
                "url": "/api/upload/file/revealed/cute_dog.svg",
                "name": "cute_dog.svg",
                "_meta": {"path": kwargs["file_path"]},
            }
        )

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)
    runtime = SimpleNamespace(config={"configurable": {"presenter": FakePresenter()}})

    async def handler(_request):
        return ToolMessage(
            content="Updated file /workspace/cute_dog.svg",
            tool_call_id="write-1",
            name="write_file",
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/cute_dog.svg", "content": "<svg/>"},
            },
            runtime=runtime,
        ),
        handler,
    )

    assert [call["file_path"] for call in reveal_calls] == ["/workspace/cute_dog.svg"]
    assert [event["event"] for event in emitted] == ["artifact:result"]

    update = await middleware.aafter_agent({"messages": []}, runtime)

    assert [call["file_path"] for call in reveal_calls] == ["/workspace/cute_dog.svg"]
    assert [event["event"] for event in emitted] == ["artifact:result"]
    assert emitted[0]["data"]["artifact"]["path"] == "/workspace/cute_dog.svg"
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_emits_failed_artifact_when_internal_reveal_returns_error() -> None:
    emitted: list[dict] = []

    class FakePresenter:
        async def emit(self, event):
            emitted.append(event)

        def present_artifact_result(
            self,
            artifact,
            *,
            success=True,
            error=None,
            depth=0,
            agent_id=None,
        ):
            return {
                "event": "artifact:result",
                "data": {
                    "artifact": artifact,
                    "success": success,
                    "error": error,
                    "depth": depth,
                    "agent_id": agent_id,
                },
            }

    async def fake_reveal_file(**kwargs):
        return json.dumps(
            {
                "type": "file_reveal",
                "file": {
                    "path": kwargs["file_path"],
                    "error": "file_not_found_or_empty",
                },
            }
        )

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/missing.pdf", "content": "report"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    await middleware.aafter_agent(
        {"messages": []},
        SimpleNamespace(config={"configurable": {"presenter": FakePresenter()}}),
    )

    assert emitted[0]["event"] == "artifact:result"
    assert emitted[0]["data"]["success"] is False
    assert emitted[0]["data"]["error"] == "file_not_found_or_empty"
    assert emitted[0]["data"]["artifact"]["path"] == "/workspace/missing.pdf"


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_successful_write_file() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {
                    "file_path": "/workspace/report.md",
                    "content": "# Report",
                },
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls[0]["file_path"] == "/workspace/report.md"


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_successful_edit_file() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(content="updated", tool_call_id="edit-1", name="edit_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "edit_file",
                "id": "edit-1",
                "args": {
                    "path": "/workspace/report.md",
                    "old_string": "draft",
                    "new_string": "final",
                },
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls[0]["file_path"] == "/workspace/report.md"


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_successful_upload_url_to_sandbox() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(
            content=json.dumps({"success": True, "path": "/workspace/input.png"}),
            tool_call_id="upload-1",
            name="upload_url_to_sandbox",
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "upload_url_to_sandbox",
                "id": "upload-1",
                "args": {
                    "url": "https://cdn.example.com/input.png",
                    "file_path": "/workspace/input.png",
                },
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls[0]["file_path"] == "/workspace/input.png"


@pytest.mark.asyncio
async def test_artifact_delivery_does_not_auto_stage_failed_write_file() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return "{}"

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(
            content=json.dumps({"success": False, "error": "permission denied"}),
            tool_call_id="write-1",
            name="write_file",
            status="error",
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/report.md"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    update = await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_skips_sensitive_auto_staged_write_file() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return "{}"

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/.env", "content": "TOKEN=secret"},
            },
            runtime=SimpleNamespace(config={}),
        ),
        handler,
    )

    update = await middleware.aafter_agent({"messages": []}, SimpleNamespace(config={}))

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_files_created_by_execute() -> None:
    reveal_calls: list[dict] = []
    backend = FakeFileSnapshotBackend(
        before=[
            {"path": "/workspace/existing.txt", "size": 1, "modified_at": "1"},
        ],
        after=[
            {"path": "/workspace/existing.txt", "size": 1, "modified_at": "1"},
            {"path": "/workspace/report.csv", "size": 12, "modified_at": "2"},
        ],
    )

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(
        reveal_file=fake_reveal_file,
        workspace_path="/workspace",
    )

    async def handler(_request):
        return ToolMessage(content="created report.csv", tool_call_id="exec-1", name="execute")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "execute",
                "id": "exec-1",
                "args": {"command": "python generate_report.py"},
            },
            runtime=SimpleNamespace(config={"configurable": {"backend": backend}}),
        ),
        handler,
    )

    await middleware.aafter_agent(
        {"messages": []},
        SimpleNamespace(config={"configurable": {"backend": backend}}),
    )

    assert backend.calls == [("**/*", "/workspace"), ("**/*", "/workspace")]
    assert reveal_calls[0]["file_path"] == "/workspace/report.csv"


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_files_modified_by_execute() -> None:
    reveal_calls: list[dict] = []
    backend = FakeFileSnapshotBackend(
        before=[
            {"path": "/workspace/report.csv", "size": 12, "modified_at": "1"},
        ],
        after=[
            {"path": "/workspace/report.csv", "size": 13, "modified_at": "2"},
        ],
    )

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(
        reveal_file=fake_reveal_file,
        workspace_path="/workspace",
    )

    async def handler(_request):
        return ToolMessage(content="updated report.csv", tool_call_id="exec-1", name="execute")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "execute",
                "id": "exec-1",
                "args": {"command": "python update_report.py"},
            },
            runtime=SimpleNamespace(config={"configurable": {"backend": backend}}),
        ),
        handler,
    )

    await middleware.aafter_agent(
        {"messages": []},
        SimpleNamespace(config={"configurable": {"backend": backend}}),
    )

    assert reveal_calls[0]["file_path"] == "/workspace/report.csv"


@pytest.mark.asyncio
async def test_artifact_delivery_execute_snapshot_skips_ignored_outputs() -> None:
    reveal_calls: list[dict] = []
    backend = FakeFileSnapshotBackend(
        before=[],
        after=[
            {"path": "/workspace/node_modules/pkg/index.js", "size": 1, "modified_at": "1"},
            {"path": "/workspace/.cache/tmp.log", "size": 1, "modified_at": "1"},
        ],
    )

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return "{}"

    middleware = ArtifactDeliveryMiddleware(
        reveal_file=fake_reveal_file,
        workspace_path="/workspace",
    )

    async def handler(_request):
        return ToolMessage(content="installed deps", tool_call_id="exec-1", name="execute")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "execute",
                "id": "exec-1",
                "args": {"command": "npm install"},
            },
            runtime=SimpleNamespace(config={"configurable": {"backend": backend}}),
        ),
        handler,
    )

    update = await middleware.aafter_agent(
        {"messages": []},
        SimpleNamespace(config={"configurable": {"backend": backend}}),
    )

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_auto_stages_file_urls_from_final_messages() -> None:
    reveal_calls: list[dict] = []
    file_url = "https://cdn.example.com/generated/cute_dog.svg?download=1"

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps(
            {
                "key": kwargs["file_path"],
                "url": kwargs["file_path"],
                "name": "cute_dog.svg",
                "_meta": {"path": kwargs["file_path"]},
            }
        )

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    await middleware.aafter_agent(
        {
            "messages": [
                AIMessage(
                    content=(
                        f"Generated file: {file_url} and docs https://example.com/landing-page"
                    )
                )
            ]
        },
        SimpleNamespace(config={}),
    )

    assert [call["file_path"] for call in reveal_calls] == [file_url]
    assert reveal_calls[0]["description"] == "External file linked by the agent"


@pytest.mark.asyncio
async def test_artifact_delivery_does_not_auto_stage_plain_webpage_urls() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    update = await middleware.aafter_agent(
        {"messages": [AIMessage(content="Read more at https://example.com/blog/post")]},
        SimpleNamespace(config={}),
    )

    assert reveal_calls == []
    assert update is None


@pytest.mark.asyncio
async def test_artifact_delivery_does_not_auto_stage_sensitive_external_urls() -> None:
    reveal_calls: list[dict] = []

    async def fake_reveal_file(**kwargs):
        reveal_calls.append(kwargs)
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=fake_reveal_file)

    update = await middleware.aafter_agent(
        {"messages": [AIMessage(content="Do not expose https://cdn.example.com/.env?download=1")]},
        SimpleNamespace(config={}),
    )

    assert reveal_calls == []
    assert update is None

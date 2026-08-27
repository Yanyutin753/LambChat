from __future__ import annotations

import pytest
from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    WriteResult,
)

from src.infra.backend.deepagent import (
    WorkflowScopedBackend,
    create_persistent_backend,
)


def _namespace_for(backend: CompositeBackend) -> tuple[str, ...]:
    return backend.default._backend._namespace(None)


def test_persistent_backend_is_concrete_and_scoped_by_session_id() -> None:
    first = create_persistent_backend(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-1",
    )
    second = create_persistent_backend(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-2",
    )

    assert isinstance(first, CompositeBackend)
    assert not callable(first)
    assert _namespace_for(first) == ("assistant-user-1", "workflow", "session-1")
    assert _namespace_for(second) == ("assistant-user-1", "workflow", "session-2")


class _FakeStore:
    def __init__(self) -> None:
        self.items: dict[tuple[tuple[str, ...], str], object] = {}

    def get(self, namespace, key):
        return self.items.get((namespace, key))

    def put(self, namespace, key, value):
        self.items[(namespace, key)] = value


def test_persistent_backend_exposes_session_workflow_as_initial_path() -> None:
    backend = create_persistent_backend(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-1",
    )
    backend.default._backend._store = _FakeStore()

    result = backend.write("/workflow/session-1/report.md", "hello")

    assert result.path == "/workflow/session-1/report.md"
    assert backend.default._backend._get_store().get(
        ("assistant-user-1", "workflow", "session-1"),
        "/report.md",
    )


class _RecordingBackend(BackendProtocol):
    def __init__(self) -> None:
        self.grep_calls: list[tuple[str, str | None, str | None, int | None]] = []
        self.delete_calls: list[str] = []
        self.edit_calls: list[str] = []

    def ls(self, path: str) -> LsResult:
        return LsResult(entries=[{"path": f"{path.rstrip('/')}/report.md"}])

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        self.grep_calls.append((pattern, path, glob, max_count))
        return GrepResult(
            matches=[{"path": "/src/app.py", "line": 3, "text": "needle"}],
            truncated=True,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return GlobResult(matches=[{"path": "/src/app.py"}], truncated=True)

    def delete(self, file_path: str) -> DeleteResult:
        self.delete_calls.append(file_path)
        return DeleteResult(path=file_path)

    def write(self, file_path: str, content: str) -> WriteResult:
        del content
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        del old_string, new_string, replace_all
        self.edit_calls.append(file_path)
        return EditResult(path=file_path, occurrences=1)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path) for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=path, content=b"data") for path in paths]


def test_workflow_backend_remaps_v0_7_structured_results() -> None:
    recording = _RecordingBackend()
    backend = WorkflowScopedBackend(recording, "/workflow/session-1")

    listed = backend.ls("/workflow/session-1/src")
    grep = backend.grep(
        "needle",
        "/workflow/session-1/src",
        "*.py",
        max_count=3,
    )
    glob = backend.glob("*.py", "/workflow/session-1/src")
    deleted = backend.delete("/workflow/session-1/report.md")

    assert listed.entries == [{"path": "/workflow/session-1/src/report.md"}]
    assert recording.grep_calls == [("needle", "/src", "*.py", 3)]
    assert grep.matches == [{"path": "/workflow/session-1/src/app.py", "line": 3, "text": "needle"}]
    assert grep.truncated is True
    assert glob.matches == [{"path": "/workflow/session-1/src/app.py"}]
    assert glob.truncated is True
    assert recording.delete_calls == ["/report.md"]
    assert deleted.path == "/workflow/session-1/report.md"


def test_workflow_backend_preserves_structured_errors() -> None:
    class _ErrorBackend(_RecordingBackend):
        def ls(self, path: str) -> LsResult:
            return LsResult(error="list failed")

        def delete(self, file_path: str) -> DeleteResult:
            return DeleteResult(error="delete failed")

    backend = WorkflowScopedBackend(_ErrorBackend(), "/workflow/session-1")

    assert backend.ls("/workflow/session-1").error == "list failed"
    assert backend.delete("/workflow/session-1/report.md").error == "delete failed"


@pytest.mark.asyncio
async def test_workflow_backend_remaps_mutation_and_transfer_result_paths() -> None:
    recording = _RecordingBackend()
    backend = WorkflowScopedBackend(recording, "/workflow/session-1")

    written = backend.write("/workflow/session-1/report.md", "hello")
    edited = backend.edit("/workflow/session-1/report.md", "old", "new")
    async_edited = await backend.aedit("/workflow/session-1/report.md", "new", "final")
    uploaded = backend.upload_files([("/workflow/session-1/upload.txt", b"data")])
    downloaded = backend.download_files(["/workflow/session-1/download.txt"])

    assert written.path == "/workflow/session-1/report.md"
    assert edited.path == "/workflow/session-1/report.md"
    assert async_edited.path == "/workflow/session-1/report.md"
    assert recording.edit_calls == ["/report.md", "/report.md"]
    assert uploaded[0].path == "/workflow/session-1/upload.txt"
    assert downloaded[0].path == "/workflow/session-1/download.txt"


def test_memories_route_namespace_aligned_with_memory_store_family() -> None:
    backend = create_persistent_backend(
        assistant_id="assistant-user-1",
        user_id="user-1",
        session_id="session-1",
    )

    memories_backend = backend.routes["/memories/"]
    assert memories_backend._namespace(None) == ("memories", "user-1", "vfs")

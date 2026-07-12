import asyncio
import gc
import json
import weakref
from types import SimpleNamespace

import pytest

from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.tool import reveal_project_tool


def test_reveal_project_tool_description_mentions_folder_reveal() -> None:
    description = reveal_project_tool.reveal_project.description
    project_path_description = reveal_project_tool.reveal_project.args["project_path"][
        "description"
    ]

    assert "文件夹" in description
    assert "非前端" in description
    assert "folder" in description
    assert "index.html 或 package.json" not in project_path_description
    assert "文件夹" in project_path_description


def test_subagent_workflow_allows_folder_reveal() -> None:
    from src.agents.core.subagent_prompts import WORKFLOW_SECTION

    assert "Project / Folder Reveal" in WORKFLOW_SECTION
    assert "ordinary folders with many files" in WORKFLOW_SECTION
    assert 'mode: "folder"' in WORKFLOW_SECTION
    assert "Use reveal_file for single files" in WORKFLOW_SECTION


def test_reveal_project_default_upload_concurrency_bounds_download_buffers() -> None:
    assert reveal_project_tool.UPLOAD_CONCURRENCY <= 4


def test_reveal_project_runtime_is_injected_not_model_argument() -> None:
    assert "runtime" not in reveal_project_tool.reveal_project.args


class _Runtime:
    def __init__(
        self,
        backend: object,
        *,
        user_id: str | None = "user-1",
        base_url: str = "https://app.example.com",
    ) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {
            "configurable": {
                "backend": backend,
                "context": context,
                "base_url": base_url,
            }
        }


class _FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload_file(
        self,
        file,
        folder: str,
        filename: str,
        content_type: str,
        *,
        skip_size_limit: bool = False,
    ):
        del skip_size_limit
        data = file.read()
        self.uploads.append((filename, data, content_type))
        return SimpleNamespace(
            key=f"{folder}/{filename}",
            size=len(data),
            content_type=content_type,
        )

    async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
        raise AssertionError("reveal_project should upload file streams, not bytes")

    async def list_files(self, prefix: str) -> list[str]:
        return []

    async def delete_file(self, key: str) -> None:
        return None


class _FakeRevealedFileStorage:
    async def upsert_by_name(self, **kwargs) -> None:
        return None


class _TrackableBytes(bytearray):
    pass


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def write(self, chunk: bytes) -> int:
        if not getattr(reveal_project_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("reveal_project spool writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(reveal_project_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("reveal_project spool seek must run in blocking IO executor")
        self.position = position
        return position

    def read(self) -> bytes:
        return bytes(self.data)


def _install_common_patches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    files: list[str],
    contents: dict[str, bytes],
) -> _FakeStorage:
    fake_storage = _FakeStorage()

    async def _get_storage():
        return fake_storage

    async def _list_project_files(_backend: object, _project_path: str) -> list[str]:
        return files

    async def _download_file_from_backend(_backend: object, file_path: str) -> bytes | None:
        return contents.get(file_path)

    monkeypatch.setattr(reveal_project_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_project_tool, "_list_project_files", _list_project_files)
    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download_file_from_backend,
    )
    monkeypatch.setattr(
        reveal_project_tool,
        "get_revealed_file_storage",
        lambda: _FakeRevealedFileStorage(),
    )

    return fake_storage


@pytest.mark.asyncio
async def test_reveal_project_backend_unavailable_offloads_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def _get_storage():
        return _FakeStorage()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(reveal_project_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_project_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path="/workspace/demo-folder",
            runtime=_Runtime(None),
        )
    )

    assert result["error"] == "backend_not_available"
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_reveal_project_keeps_common_folder_text_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [
        f"{project_path}/README.md",
        f"{project_path}/main.py",
        f"{project_path}/scripts/deploy.sh",
        f"{project_path}/config/app.yaml",
        f"{project_path}/data/sample.json",
    ]
    contents = {
        files[0]: b"# Demo\n",
        files[1]: b"print('hello')\n",
        files[2]: b"#!/bin/sh\necho deploy\n",
        files[3]: b"port: 8080\n",
        files[4]: b'{"ok": true}\n',
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["type"] == "project_reveal"
    assert "/README.md" in result["files"]
    assert "/main.py" in result["files"]
    assert "/scripts/deploy.sh" in result["files"]
    assert "/config/app.yaml" in result["files"]
    assert "/data/sample.json" in result["files"]


@pytest.mark.asyncio
async def test_reveal_project_returns_folder_mode_without_frontend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/backend-service"
    files = [
        f"{project_path}/README.md",
        f"{project_path}/src/app.py",
        f"{project_path}/pyproject.toml",
    ]
    contents = {
        files[0]: b"# Backend Service\n",
        files[1]: b"print('service')\n",
        files[2]: b"[project]\nname='backend-service'\n",
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["mode"] == "folder"
    assert result["entry"] is None


@pytest.mark.asyncio
async def test_reveal_project_offloads_final_manifest_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/backend-service"
    files = [f"{project_path}/README.md"]
    contents = {files[0]: b"# Backend Service\n"}
    _install_common_patches(monkeypatch, files=files, contents=contents)
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    async def fake_upload_project_files_bounded(
        storage,
        backend,
        upload_tasks,
        folder_name,
        base_url,
    ):
        del storage, backend, upload_tasks, folder_name, base_url
        return [
            (
                "/README.md",
                {"url": "https://app.example.com/file", "is_binary": False, "size": 18},
                None,
                None,
            )
        ]

    monkeypatch.setattr(reveal_project_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        reveal_project_tool,
        "_upload_project_files_bounded",
        fake_upload_project_files_bounded,
    )

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["type"] == "project_reveal"
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_reveal_project_keeps_project_mode_for_frontend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/site"
    files = [
        f"{project_path}/index.html",
        f"{project_path}/src/main.jsx",
        f"{project_path}/package.json",
    ]
    contents = {
        files[0]: b'<!doctype html><div id="root"></div>',
        files[1]: b"import React from 'react';\n",
        files[2]: b'{"dependencies":{"react":"^19.0.0"}}',
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["mode"] == "project"
    assert result["entry"] == "/src/main.jsx"


@pytest.mark.asyncio
async def test_reveal_project_handles_single_html_file_path_as_static_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = "/workspace/daily-news-2025-07-05.html"
    _install_common_patches(
        monkeypatch,
        files=[file_path],
        contents={file_path: b"<!doctype html><title>News</title>"},
    )

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=file_path,
            runtime=_Runtime(object()),
            template="static",
        )
    )

    assert result["type"] == "project_reveal"
    assert result["mode"] == "project"
    assert result["entry"] == "/daily-news-2025-07-05.html"
    assert "/daily-news-2025-07-05.html" in result["files"]
    assert result["file_count"] == 1


@pytest.mark.asyncio
async def test_reveal_project_uploads_with_bounded_worker_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/large"
    file_count = reveal_project_tool.UPLOAD_CONCURRENCY * 3
    files = [f"{project_path}/file-{index}.txt" for index in range(file_count)]
    contents = {file_path: f"{file_path}\n".encode() for file_path in files}
    _install_common_patches(monkeypatch, files=files, contents=contents)

    unawaited_uploads = 0
    max_unawaited_uploads = 0

    def fake_upload_file(
        storage,
        backend,
        file_path: str,
        rel_path: str,
        folder_name: str,
        base_url: str,
        semaphore,
    ):
        del storage, backend, file_path, folder_name, base_url, semaphore
        nonlocal unawaited_uploads, max_unawaited_uploads
        unawaited_uploads += 1
        max_unawaited_uploads = max(max_unawaited_uploads, unawaited_uploads)

        async def _run():
            nonlocal unawaited_uploads
            unawaited_uploads -= 1
            return (
                rel_path,
                {"url": "https://app.example.com/file", "is_binary": False, "size": 1},
                None,
                None,
            )

        return _run()

    monkeypatch.setattr(reveal_project_tool, "_upload_file", fake_upload_file)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["file_count"] == file_count
    assert max_unawaited_uploads <= reveal_project_tool.UPLOAD_CONCURRENCY


@pytest.mark.asyncio
async def test_reveal_project_caps_upload_task_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/huge"
    files = [f"{project_path}/file-{index}.txt" for index in range(6)]
    contents = {file_path: f"{file_path}\n".encode() for file_path in files}
    _install_common_patches(monkeypatch, files=files, contents=contents)
    monkeypatch.setattr(reveal_project_tool, "MAX_PROJECT_FILES", 3, raising=False)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["file_count"] == 3
    assert result["filtered_file_count"] == 3
    assert result["skipped_file_count"] == 3
    assert result["skipped_due_to_file_limit_count"] == 3


@pytest.mark.asyncio
async def test_reveal_project_cleanup_tasks_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/site"
    files = [f"{project_path}/index.html"]
    contents = {files[0]: b"<!doctype html>"}
    _install_common_patches(monkeypatch, files=files, contents=contents)
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def fake_cleanup_old_versions(storage, project_name: str) -> None:
        del storage
        calls.append(project_name)
        started.set()
        await release.wait()

    monkeypatch.setattr(reveal_project_tool, "_cleanup_old_versions", fake_cleanup_old_versions)
    monkeypatch.setattr(
        reveal_project_tool,
        "_project_cleanup_tasks",
        BestEffortTaskLimiter("test project cleanup", max_tasks=1),
    )

    await reveal_project_tool.reveal_project.coroutine(
        project_path=project_path,
        runtime=_Runtime(object()),
        name="demo",
    )
    await started.wait()
    await reveal_project_tool.reveal_project.coroutine(
        project_path=project_path,
        runtime=_Runtime(object()),
        name="demo",
    )
    await asyncio.sleep(0)

    assert calls == ["demo"]

    release.set()


@pytest.mark.asyncio
async def test_list_project_files_via_glob_caps_materialized_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeGlobResult:
        matches = [{"path": f"/workspace/huge/file-{index}.txt"} for index in range(1000)]

    class _FakeBackend:
        async def aglob(self, _pattern: str, *, path: str):
            assert path == "/workspace/huge"
            return _FakeGlobResult()

    monkeypatch.setattr(reveal_project_tool, "MAX_PROJECT_FILES", 25, raising=False)

    files = await reveal_project_tool._list_project_files_via_glob(
        _FakeBackend(),
        "/workspace/huge",
    )

    assert len(files) == 25
    assert files[-1] == "/workspace/huge/file-24.txt"


@pytest.mark.asyncio
async def test_list_project_files_sandbox_find_uses_configured_scan_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[str] = []

    class _FakeBackend:
        async def aexecute(self, command: str):
            commands.append(command)
            return SimpleNamespace(output="")

        async def als(self, path: str):
            assert path == "/workspace/huge"
            return SimpleNamespace(entries=[])

    monkeypatch.setattr(reveal_project_tool, "MAX_PROJECT_FILES", 25, raising=False)

    files = await reveal_project_tool._list_project_files(
        _FakeBackend(),
        "/workspace/huge",
    )

    assert files == []
    assert commands
    assert "head -25" in commands[0]


@pytest.mark.asyncio
async def test_reveal_project_offloads_template_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _Backend:
        pass

    async def fake_list_project_files(_backend: object, project_path: str):
        assert project_path == "/workspace/app"
        return ["/workspace/app/package.json", "/workspace/app/src/main.jsx"]

    async def fake_upload_project_files_bounded(
        _storage,
        _backend,
        upload_tasks,
        _folder_name,
        _base_url,
    ):
        assert upload_tasks == [
            ("/workspace/app/package.json", "/package.json"),
            ("/workspace/app/src/main.jsx", "/src/main.jsx"),
        ]
        return [
            (
                "/package.json",
                {"url": "https://app.example.com/package.json", "size": 18},
                '{"dependencies":{"react":"latest"}}',
                None,
            ),
            (
                "/src/main.jsx",
                {"url": "https://app.example.com/src/main.jsx", "size": 4},
                None,
                None,
            ),
        ]

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(reveal_project_tool, "_list_project_files", fake_list_project_files)
    monkeypatch.setattr(
        reveal_project_tool,
        "_upload_project_files_bounded",
        fake_upload_project_files_bounded,
    )

    async def fake_get_storage():
        return _FakeStorage()

    monkeypatch.setattr(reveal_project_tool, "_get_storage", fake_get_storage)
    monkeypatch.setattr(
        reveal_project_tool,
        "get_revealed_file_storage",
        lambda: _FakeRevealedFileStorage(),
    )
    monkeypatch.setattr(reveal_project_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path="/workspace/app",
            runtime=_Runtime(_Backend()),
        )
    )

    assert calls == [reveal_project_tool.detect_template, json.dumps]
    assert result["template"] == "react"


@pytest.mark.asyncio
async def test_upload_file_releases_download_buffer_before_upload_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released_before_upload_completed = False
    blocking_calls: list[str] = []
    buffer_ref: weakref.ReferenceType[_TrackableBytes] | None = None

    async def _download_file_from_backend(_backend: object, _file_path: str):
        return _TrackableBytes(b"x" * 32)

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str,
            *,
            skip_size_limit: bool = False,
        ):
            del file, folder, filename, content_type, skip_size_limit
            nonlocal released_before_upload_completed
            gc.collect()
            released_before_upload_completed = buffer_ref() is None
            return SimpleNamespace(
                key="revealed_projects/demo/main.txt",
                size=32,
                content_type="text/plain",
            )

    buffer_ref: weakref.ReferenceType[_TrackableBytes]

    async def _wrapped_download(_backend: object, _file_path: str):
        nonlocal buffer_ref
        data = await _download_file_from_backend(_backend, _file_path)
        buffer_ref = weakref.ref(data)
        return data

    monkeypatch.setattr(reveal_project_tool, "_download_file_from_backend", _wrapped_download)
    monkeypatch.setattr(reveal_project_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        monkeypatch.setattr(reveal_project_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(
                reveal_project_tool, "_inside_fake_blocking_io", False, raising=False
            )

    monkeypatch.setattr(reveal_project_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(reveal_project_tool, "_inside_fake_blocking_io", False, raising=False)

    result = await reveal_project_tool._upload_file(
        storage=_FakeStorage(),
        backend=object(),
        file_path="/workspace/main.txt",
        rel_path="/main.txt",
        folder_name="revealed_projects/demo",
        base_url="https://app.example.com",
        semaphore=asyncio.Semaphore(1),
    )

    assert result is not None
    assert released_before_upload_completed is True
    assert blocking_calls == ["write", "seek"]


@pytest.mark.asyncio
async def test_upload_file_rejects_known_oversize_backend_file_before_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Backend:
        async def aget_file_size(self, file_path: str) -> int:
            assert file_path == "/workspace/huge.bin"
            return 11

    class _Storage:
        _config = SimpleNamespace(internal_max_upload_size=10)

        async def upload_file(self, *args, **kwargs):
            raise AssertionError("oversized project file must not be uploaded")

    async def _download_file_from_backend(_backend: object, _file_path: str):
        raise AssertionError("oversized project file must not be downloaded")

    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download_file_from_backend,
    )

    result = await reveal_project_tool._upload_file(
        storage=_Storage(),
        backend=_Backend(),
        file_path="/workspace/huge.bin",
        rel_path="/huge.bin",
        folder_name="revealed_projects/demo",
        base_url="https://app.example.com",
        semaphore=asyncio.Semaphore(1),
    )

    assert result is None

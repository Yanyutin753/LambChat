import asyncio
import gc
import io
import json
import subprocess
import tarfile
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.protocol import GlobResult, LsResult

from src.infra.async_utils.background_tasks import BestEffortTaskLimiter
from src.infra.tool import reveal_project_tool


def test_reveal_project_tool_description_mentions_folder_reveal() -> None:
    description = reveal_project_tool.reveal_project.description
    project_path_description = reveal_project_tool.reveal_project.args["project_path"][
        "description"
    ]

    assert "folder" in description
    assert "folder tree" in description
    assert "index.html 或 package.json" not in project_path_description
    assert "folder" in project_path_description


def test_subagent_workflow_allows_folder_reveal() -> None:
    from src.agents.core.subagent_prompts import WORKFLOW_SECTION

    assert "Use `reveal_project` for a multi-file project or folder" in WORKFLOW_SECTION
    assert "Use `reveal_file` for an external HTTP(S) URL or one file" in WORKFLOW_SECTION


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

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(reveal_project_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_project_tool, "run_long_blocking_io", fake_run_long_blocking_io)

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

    async def fake_run_long_blocking_io(func, *args, **kwargs):
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

    monkeypatch.setattr(reveal_project_tool, "run_long_blocking_io", fake_run_long_blocking_io)
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
    class _FakeBackend:
        async def aglob(self, _pattern: str, *, path: str):
            assert path == "/workspace/huge"
            return GlobResult(
                matches=[{"path": f"/workspace/huge/file-{index}.txt"} for index in range(1000)]
            )

    monkeypatch.setattr(reveal_project_tool, "MAX_PROJECT_FILES", 25, raising=False)

    files = await reveal_project_tool._list_project_files_via_glob(
        _FakeBackend(),
        "/workspace/huge",
    )

    assert len(files) == 25
    assert files[-1] == "/workspace/huge/file-24.txt"


@pytest.mark.asyncio
async def test_list_project_files_raises_when_glob_and_ls_return_errors() -> None:
    class _FailedBackend:
        async def aglob(self, _pattern: str, *, path: str) -> GlobResult:
            return GlobResult(error=f"glob failed for {path}")

        def glob(self, _pattern: str, path: str) -> GlobResult:
            return GlobResult(error=f"sync glob failed for {path}")

        async def als(self, path: str) -> LsResult:
            return LsResult(error=f"ls failed for {path}")

    with pytest.raises(RuntimeError, match="could not list project files"):
        await reveal_project_tool._list_project_files(_FailedBackend(), "/workspace/project")


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

    async def fake_run_long_blocking_io(func, *args, **kwargs):
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
    monkeypatch.setattr(reveal_project_tool, "run_long_blocking_io", fake_run_long_blocking_io)

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

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        monkeypatch.setattr(reveal_project_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(
                reveal_project_tool, "_inside_fake_blocking_io", False, raising=False
            )

    monkeypatch.setattr(reveal_project_tool, "run_long_blocking_io", fake_run_long_blocking_io)
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


# --- 沙箱 bundle 打包上传（P0：跨洋逐文件往返 → 单包单流） ---


class _SandboxBackend:
    """带 aexecute 的假沙箱 backend：记录命令，输出可注入。"""

    def __init__(self, *, output: str = "") -> None:
        self.commands: list[str] = []
        self._output = output

    async def aexecute(self, command: str, **_kwargs) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(output=self._output)

    async def aget_file_size(self, _file_path: str) -> int:
        return 1024


def _build_targz(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _install_bundle_patches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    files: list[str],
    bundle: bytes | None,
    contents: dict[str, bytes] | None = None,
    storage: _FakeStorage | None = None,
) -> tuple[_SandboxBackend, _FakeStorage]:
    """沙箱 bundle 路径测试通用装配：记录下载调用，tar 包与逐文件内容分流。"""

    async def _download(_backend: object, file_path: str) -> bytes | None:
        if file_path.startswith("/workspace/.reveal-bundle-"):
            return bundle
        return (contents or {}).get(file_path)

    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download,
    )
    return _install_common_patches(monkeypatch, files=files, contents=contents or {})


@pytest.mark.asyncio
async def test_reveal_project_batches_sandbox_files_through_single_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [f"{project_path}/file-{index}.txt" for index in range(6)]
    entries = {f"./file-{index}.txt": f"content-{index}\n".encode() for index in range(6)}
    bundle = _build_targz(entries)

    async def _download(_backend: object, file_path: str) -> bytes | None:
        assert file_path.startswith("/workspace/.reveal-bundle-"), (
            f"must download the bundle only, got {file_path}"
        )
        return bundle

    fake_storage = _install_common_patches(monkeypatch, files=files, contents={})
    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download,
    )
    backend = _SandboxBackend()

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(backend),
        )
    )

    assert result["file_count"] == 6
    assert set(result["files"]) == {f"/file-{index}.txt" for index in range(6)}
    # 单次 bundle 下载替代 6 次逐文件跨洋往返
    tar_commands = [cmd for cmd in backend.commands if cmd.startswith("tar ")]
    assert len(tar_commands) == 1
    assert "-C" in tar_commands[0] and "czf" in tar_commands[0]
    # daemon 侧打包产物被清理
    assert any("rm -f" in cmd and ".reveal-bundle-" in cmd for cmd in backend.commands)
    assert len(fake_storage.uploads) == 6


@pytest.mark.parametrize(
    "directory_name", ["project", "project ' $(touch injected) `touch injected`"]
)
def test_bundle_command_archives_visible_files_with_literal_paths(
    tmp_path: Path, directory_name: str
) -> None:
    project = tmp_path / directory_name
    project.mkdir()
    (project / "index.html").write_text("hello")
    (project / "src").mkdir()
    (project / "src" / "app.ts").write_text("app")
    for ignored in [".env", ".hidden/secret.txt", "src/.hidden/secret.txt", "node_modules/lib.js"]:
        target = project / ignored
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("excluded")
    bundle = tmp_path / f"{directory_name}.tar.gz"

    subprocess.run(
        reveal_project_tool._build_bundle_command(
            str(project), str(bundle), ["/index.html", "/src/app.ts"]
        ),
        shell=True,
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert not (tmp_path / "injected").exists()
    with tarfile.open(bundle) as archive:
        assert {member.name for member in archive if member.isfile()} == {
            "./index.html",
            "./src/app.ts",
        }


def test_bundle_command_only_archives_selected_files_without_recursing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "index.html").write_text("hello")
    (project / "unselected.bin").write_bytes(b"unused")
    (project / "changed-to-directory").mkdir()
    (project / "changed-to-directory" / "large.bin").write_bytes(b"unused")
    bundle = tmp_path / "bundle.tar.gz"

    subprocess.run(
        reveal_project_tool._build_bundle_command(
            str(project), str(bundle), selected_paths=["/index.html", "/changed-to-directory"]
        ),
        shell=True,
        check=True,
        capture_output=True,
    )

    with tarfile.open(bundle) as archive:
        assert {member.name for member in archive if member.isfile()} == {"./index.html"}


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [None, 257 * 1024 * 1024])
async def test_bundle_download_requires_known_bounded_archive_size(
    monkeypatch: pytest.MonkeyPatch, size: int | None
) -> None:
    async def get_size(_backend: object, _file_path: str) -> int | None:
        return size

    downloads = []

    async def download(_backend: object, file_path: str) -> bytes:
        downloads.append(file_path)
        return _build_targz({"./index.html": b"hello"})

    monkeypatch.setattr(reveal_project_tool, "_get_backend_file_size", get_size)
    monkeypatch.setattr(reveal_project_tool, "_download_file_from_backend", download)

    result = await reveal_project_tool._upload_project_files_via_bundle(
        _FakeStorage(),
        _SandboxBackend(),
        "/workspace/project",
        [("/workspace/project/index.html", "/index.html")],
        "folder",
        "https://example.com",
    )

    assert result is None
    assert downloads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["download", "corrupt", "extraction_limit"])
async def test_failed_bundle_attempt_removes_daemon_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "index.html").write_text("hello")

    class LocalBackend:
        async def aexecute(self, command: str, **_kwargs) -> SimpleNamespace:
            result = await asyncio.to_thread(
                subprocess.run, command, shell=True, check=True, capture_output=True
            )
            return SimpleNamespace(output=result.stdout.decode())

    async def download(_backend: object, file_path: str) -> bytes | None:
        assert Path(file_path).exists()
        if failure == "download":
            return None
        if failure == "corrupt":
            return b"not a tar archive"
        return _build_targz({"./index.html": b"hello" * 200})

    monkeypatch.setattr(reveal_project_tool, "_download_file_from_backend", download)
    monkeypatch.setattr(reveal_project_tool, "BUNDLE_EXTRACT_TOTAL_LIMIT", 512)

    result = await reveal_project_tool._upload_project_files_via_bundle(
        _FakeStorage(),
        LocalBackend(),
        str(project),
        [(str(project / "index.html"), "/index.html")],
        "folder",
        "https://example.com",
    )

    assert result is None
    assert list(tmp_path.glob(".reveal-bundle-*")) == []


@pytest.mark.asyncio
async def test_bundle_missing_members_fall_back_to_per_file_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [f"{project_path}/file-{index}.txt" for index in range(6)]
    # bundle 只带 5 个文件，file-5 缺失 → 走逐文件补传
    entries = {f"./file-{index}.txt": f"content-{index}\n".encode() for index in range(5)}
    bundle = _build_targz(entries)
    contents = {files[5]: b"content-5\n"}

    async def _download(_backend: object, file_path: str) -> bytes | None:
        if file_path.startswith("/workspace/.reveal-bundle-"):
            return bundle
        return contents.get(file_path)

    _install_common_patches(monkeypatch, files=files, contents=contents)
    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download,
    )
    backend = _SandboxBackend()

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(backend),
        )
    )

    assert result["file_count"] == 6
    assert "/file-5.txt" in result["files"]


@pytest.mark.asyncio
async def test_bundle_download_failure_falls_back_to_per_file_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [f"{project_path}/file-{index}.txt" for index in range(6)]
    contents = {file_path: f"{file_path}\n".encode() for file_path in files}

    async def _download(_backend: object, file_path: str) -> bytes | None:
        if file_path.startswith("/workspace/.reveal-bundle-"):
            return None  # daemon 侧 tar 不可用/失败
        return contents.get(file_path)

    _install_common_patches(monkeypatch, files=files, contents=contents)
    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download,
    )
    backend = _SandboxBackend()

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(backend),
        )
    )

    assert result["file_count"] == 6


def test_extract_bundle_members_skips_unsafe_entries() -> None:
    entries = {
        "./README.md": b"# demo\n",
        "../escape.txt": b"evil",
        "/absolute.txt": b"evil",
        "./nested/ok.txt": b"ok\n",
    }
    bundle = _build_targz(entries)

    members = reveal_project_tool._extract_bundle_members(
        bundle, wanted={"/README.md", "/nested/ok.txt", "/escape.txt", "/absolute.txt"}
    )

    assert members == {"/README.md": b"# demo\n", "/nested/ok.txt": b"ok\n"}


def test_extract_bundle_members_returns_none_over_total_limit() -> None:
    bundle = _build_targz({"./a.txt": b"x" * 6, "./b.txt": b"y" * 6})

    assert (
        reveal_project_tool._extract_bundle_members(
            bundle, wanted={"/a.txt", "/b.txt"}, max_total_size=8
        )
        is None
    )


def test_extract_bundle_members_skips_oversize_single_member() -> None:
    bundle = _build_targz({"./small.txt": b"ok\n", "./huge.bin": b"x" * 100})

    members = reveal_project_tool._extract_bundle_members(
        bundle, wanted={"/small.txt", "/huge.bin"}, max_member_size=10
    )

    assert members == {"/small.txt": b"ok\n"}


@pytest.mark.asyncio
async def test_small_sandbox_projects_skip_bundle_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [f"{project_path}/file-{index}.txt" for index in range(2)]
    contents = {file_path: f"{file_path}\n".encode() for file_path in files}
    _install_common_patches(monkeypatch, files=files, contents=contents)
    backend = _SandboxBackend()

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(backend),
        )
    )

    assert result["file_count"] == 2
    assert backend.commands == []

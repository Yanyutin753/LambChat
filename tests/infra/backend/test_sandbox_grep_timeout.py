from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import deepagents.backends.protocol as deepagents_protocol
import deepagents.backends.utils as deepagents_utils
import pytest

from src.kernel.config import settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def _load_module_from_path(module_name: str, relative_path: str):
    path = Path(__file__).parents[3] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


for _missing_name in ("GlobResult", "LsResult", "ReadResult", "WriteResult"):
    if not hasattr(deepagents_protocol, _missing_name):
        setattr(deepagents_protocol, _missing_name, dict)

for _missing_name in (
    "create_file_data",
    "format_content_with_line_numbers",
    "slice_read_response",
):
    if not hasattr(deepagents_utils, _missing_name):
        setattr(deepagents_utils, _missing_name, lambda *args, **kwargs: "")


daytona_module = _load_module_from_path(
    "test_daytona_backend_module", "src/infra/backend/daytona.py"
)
e2b_module = _load_module_from_path("test_e2b_backend_module", "src/infra/backend/e2b.py")
DaytonaBackend = daytona_module.DaytonaBackend
E2BBackend = e2b_module.E2BBackend
sandbox_grep_module = _load_module_from_path(
    "test_sandbox_grep_module", "src/infra/sandbox_grep.py"
)
build_grep_command = sandbox_grep_module.build_grep_command


class _FakeDaytonaProcess:
    def __init__(self, result: SimpleNamespace) -> None:
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    def exec(self, command: str, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


class _FakeDaytonaSandbox:
    def __init__(self, result: SimpleNamespace) -> None:
        self.id = "daytona-test"
        self.process = _FakeDaytonaProcess(result)

    def get_work_dir(self) -> str:
        return "/workspace"


class _FakeDaytonaFS:
    def __init__(self) -> None:
        self.download_calls: list[list] = []
        self.upload_calls: list[list] = []

    def download_files(self, requests):
        self.download_calls.append(list(requests))
        return [SimpleNamespace(source=requests[0].source, result=b"x" * 1024)]

    def upload_files(self, requests):
        self.upload_calls.append(list(requests))


class _FakeDaytonaSandboxWithFS:
    def __init__(self) -> None:
        self.id = "daytona-test"
        self.fs = _FakeDaytonaFS()
        self.process = _FakeDaytonaProcess(SimpleNamespace(result="9", exit_code=0))

    def get_work_dir(self) -> str:
        return "/workspace"


class _FakeE2BCommands:
    def __init__(self, result: SimpleNamespace) -> None:
        self.result = result
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _FakeE2BSandbox:
    def __init__(self, result: SimpleNamespace) -> None:
        self.sandbox_id = "e2b-test"
        self.commands = _FakeE2BCommands(result)


class _FakeE2BFiles:
    def __init__(self) -> None:
        self.list_calls: list[str] = []
        self.read_calls: list[tuple[str, str]] = []
        self.write_calls: list[tuple[str, bytes | str]] = []

    def list(self, path: str):
        self.list_calls.append(path)
        return []

    def read(self, path: str, format: str):
        self.read_calls.append((path, format))
        return b"x"

    def write(self, path: str, data: bytes | str):
        self.write_calls.append((path, data))


class _FakeE2BSandboxWithFiles:
    def __init__(self) -> None:
        self.sandbox_id = "e2b-test"
        self.files = _FakeE2BFiles()
        self.commands = _FakeE2BCommands(SimpleNamespace(stdout="", stderr="", exit_code=0))


def test_sandbox_grep_timeout_setting_defaults_to_30_seconds() -> None:
    assert SETTING_DEFINITIONS["SANDBOX_GREP_TIMEOUT"]["default"] == 30
    assert hasattr(settings, "SANDBOX_GREP_TIMEOUT")


def test_build_grep_command_prefers_rg_and_excludes_large_directories() -> None:
    command = build_grep_command("needle", path="/workspace")

    assert "if command -v rg >/dev/null 2>&1; then" in command
    assert "rg -nH --no-heading --color=never --no-messages -F" in command
    assert "-g '!node_modules/**'" in command
    assert "-g '!.git/**'" in command
    assert "-g '!dist/**'" in command
    assert "-g '!build/**'" in command
    assert "-g '!.venv/**'" in command
    assert "--glob" not in command
    assert "/workspace" in command


def test_build_grep_command_passes_user_glob_to_rg() -> None:
    command = build_grep_command("needle", path="/workspace", glob="*.py")

    assert "-g '*.py'" in command
    assert "--glob" not in command


def test_build_grep_command_does_not_run_grep_when_rg_finds_no_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("/bin/sh") is None:
        pytest.skip("requires a POSIX shell")

    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    rg_path = bin_path / "rg"
    grep_path = bin_path / "grep"
    rg_path.write_text("#!/bin/sh\nexit 1\n")
    grep_path.write_text("#!/bin/sh\necho fallback-ran\nexit 0\n")
    rg_path.chmod(0o755)
    grep_path.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_path))

    result = subprocess.run(
        build_grep_command("missing", path=str(tmp_path)),
        shell=True,
        executable="/bin/sh",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "fallback-ran" not in result.stdout


def test_daytona_backend_grep_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SANDBOX_GREP_TIMEOUT", 30, raising=False)
    sandbox = _FakeDaytonaSandbox(SimpleNamespace(result="/tmp/app.py:3:needle", exit_code=0))
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    matches = backend.grep_raw("needle", path="/tmp", glob="*.py")

    assert matches == [{"path": "/tmp/app.py", "line": 3, "text": "needle"}]
    assert sandbox.process.calls[0][1]["timeout"] == 30


def test_daytona_backend_relative_commands_run_inside_configured_work_dir() -> None:
    sandbox = _FakeDaytonaSandbox(SimpleNamespace(result="ok", exit_code=0))
    backend = DaytonaBackend(sandbox=sandbox, timeout=180, work_dir="/workspace/sessions/session-1")

    response = backend.execute("touch report.md")

    assert response.exit_code == 0
    command = sandbox.process.calls[0][0]
    assert (
        command
        == "mkdir -p /workspace/sessions/session-1 && cd /workspace/sessions/session-1 && touch report.md"
    )


def test_daytona_download_files_skips_large_file_before_sdk_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daytona_module, "SANDBOX_DOWNLOAD_MAX_BYTES", 8)
    sandbox = _FakeDaytonaSandboxWithFS()
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    responses = backend.download_files(["/workspace/large.bin"])

    assert responses[0].content is None
    assert sandbox.fs.download_calls == []
    assert any("stat -c %s" in call[0] for call in sandbox.process.calls)


def test_daytona_download_files_rejects_too_many_paths_before_preflight() -> None:
    sandbox = _FakeDaytonaSandboxWithFS()
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    responses = backend.download_files([f"/workspace/file-{index}.txt" for index in range(101)])

    assert len(responses) == 101
    assert {response.error for response in responses} == {"too_many_files"}
    assert sandbox.fs.download_calls == []
    assert sandbox.process.calls == []


def test_daytona_upload_files_rejects_too_many_files_before_sdk_upload() -> None:
    sandbox = _FakeDaytonaSandboxWithFS()
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    responses = backend.upload_files(
        [(f"/workspace/file-{index}.txt", b"x") for index in range(101)]
    )

    assert len(responses) == 101
    assert {response.error for response in responses} == {"too_many_files"}
    assert sandbox.fs.upload_calls == []
    assert sandbox.process.calls == []


def test_daytona_upload_files_rejects_large_file_before_sdk_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daytona_module, "SANDBOX_UPLOAD_MAX_BYTES", 8, raising=False)
    sandbox = _FakeDaytonaSandboxWithFS()
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    responses = backend.upload_files([("/workspace/large.bin", b"x" * 9)])

    assert responses[0].error == "file_too_large"
    assert sandbox.fs.upload_calls == []
    assert sandbox.process.calls == []


@pytest.mark.asyncio
async def test_daytona_backend_async_grep_returns_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SANDBOX_GREP_TIMEOUT", 30, raising=False)
    sandbox = _FakeDaytonaSandbox(
        SimpleNamespace(result="Command timed out after 30 seconds", exit_code=-1)
    )
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    result = await backend.agrep_raw("needle", path="/tmp")

    assert (
        result == "Error: grep timed out after 30s. Try a more specific pattern or a narrower path."
    )
    assert sandbox.process.calls[0][1]["timeout"] == 30


def test_e2b_backend_grep_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SANDBOX_GREP_TIMEOUT", 30, raising=False)
    sandbox = _FakeE2BSandbox(
        SimpleNamespace(stdout="/tmp/app.py:3:needle", stderr="", exit_code=0)
    )
    backend = E2BBackend(sandbox=sandbox, timeout=180)

    matches = backend.grep_raw("needle", path="/tmp", glob="*.py")

    assert matches == [{"path": "/tmp/app.py", "line": 3, "text": "needle"}]
    assert sandbox.commands.calls[0]["timeout"] == 30


def test_e2b_backend_relative_commands_run_inside_configured_work_dir() -> None:
    sandbox = _FakeE2BSandbox(SimpleNamespace(stdout="ok", stderr="", exit_code=0))
    backend = E2BBackend(sandbox=sandbox, timeout=180, work_dir="/home/user/sessions/session-1")

    response = backend.execute("touch report.md")

    assert response.exit_code == 0
    assert (
        sandbox.commands.calls[0]["cmd"]
        == "mkdir -p /home/user/sessions/session-1 && cd /home/user/sessions/session-1 && touch report.md"
    )


def test_e2b_backend_relative_file_tools_use_configured_work_dir() -> None:
    sandbox = _FakeE2BSandboxWithFiles()
    backend = E2BBackend(sandbox=sandbox, timeout=180, work_dir="/home/user/sessions/session-1")

    result = backend.write("report.md", "hello")

    assert result.path == "/home/user/sessions/session-1/report.md"
    assert sandbox.files.write_calls == [("/home/user/sessions/session-1/report.md", "hello")]


def test_e2b_download_files_rejects_too_many_paths_before_preflight() -> None:
    sandbox = _FakeE2BSandboxWithFiles()
    backend = E2BBackend(sandbox=sandbox, timeout=180)

    responses = backend.download_files([f"/home/user/file-{index}.txt" for index in range(101)])

    assert len(responses) == 101
    assert {response.error for response in responses} == {"too_many_files"}
    assert sandbox.files.list_calls == []
    assert sandbox.files.read_calls == []


def test_e2b_upload_files_rejects_too_many_files_before_writing() -> None:
    sandbox = _FakeE2BSandboxWithFiles()
    backend = E2BBackend(sandbox=sandbox, timeout=180)

    responses = backend.upload_files(
        [(f"/home/user/file-{index}.txt", b"x") for index in range(101)]
    )

    assert len(responses) == 101
    assert {response.error for response in responses} == {"too_many_files"}
    assert sandbox.files.write_calls == []


def test_e2b_upload_files_rejects_large_file_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(e2b_module, "SANDBOX_UPLOAD_MAX_BYTES", 8, raising=False)
    sandbox = _FakeE2BSandboxWithFiles()
    backend = E2BBackend(sandbox=sandbox, timeout=180)

    responses = backend.upload_files([("/home/user/large.bin", b"x" * 9)])

    assert responses[0].error == "file_too_large"
    assert sandbox.files.write_calls == []


@pytest.mark.asyncio
async def test_e2b_backend_async_grep_returns_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SANDBOX_GREP_TIMEOUT", 30, raising=False)
    sandbox = _FakeE2BSandbox(
        SimpleNamespace(stdout="Command timed out after 30 seconds", stderr="", exit_code=-1)
    )
    backend = E2BBackend(sandbox=sandbox, timeout=180)

    result = await backend.agrep_raw("needle", path="/tmp")

    assert (
        result == "Error: grep timed out after 30s. Try a more specific pattern or a narrower path."
    )
    assert sandbox.commands.calls[0]["timeout"] == 30

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import deepagents.backends.protocol as deepagents_protocol
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


def test_sandbox_grep_timeout_setting_defaults_to_30_seconds() -> None:
    assert SETTING_DEFINITIONS["SANDBOX_GREP_TIMEOUT"]["default"] == 30
    assert hasattr(settings, "SANDBOX_GREP_TIMEOUT")


def test_build_grep_command_prefers_rg_and_excludes_large_directories() -> None:
    command = build_grep_command("needle", path="/workspace")

    assert "command -v rg >/dev/null 2>&1" in command
    assert "rg --fixed-strings --line-number --with-filename --no-heading --color never" in command
    assert "--glob '!node_modules/**'" in command
    assert "--glob '!.git/**'" in command
    assert "--glob '!dist/**'" in command
    assert "--glob '!build/**'" in command
    assert "--glob '!.venv/**'" in command
    assert "/workspace" in command


def test_build_grep_command_passes_user_glob_to_rg() -> None:
    command = build_grep_command("needle", path="/workspace", glob="*.py")

    assert "--glob '*.py'" in command


def test_daytona_backend_grep_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SANDBOX_GREP_TIMEOUT", 30, raising=False)
    sandbox = _FakeDaytonaSandbox(SimpleNamespace(result="/tmp/app.py:3:needle", exit_code=0))
    backend = DaytonaBackend(sandbox=sandbox, timeout=180)

    matches = backend.grep_raw("needle", path="/tmp", glob="*.py")

    assert matches == [{"path": "/tmp/app.py", "line": 3, "text": "needle"}]
    assert sandbox.process.calls[0][1]["timeout"] == 30


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

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_module_from_path(module_name: str, relative_path: str):
    path = Path(__file__).parents[3] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


daytona_module = _load_module_from_path(
    "test_daytona_backend_glob_module", "src/infra/backend/daytona.py"
)
DaytonaBackend = daytona_module.DaytonaBackend


class _FakeDaytonaProcess:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def exec(self, command: str, **kwargs):
        self.calls.append((command, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return SimpleNamespace(result="", exit_code=1)


class _FakeDaytonaSandbox:
    def __init__(self, process: _FakeDaytonaProcess) -> None:
        self.id = "daytona-test"
        self.process = process

    def get_work_dir(self) -> str:
        return "/workspace"


def test_daytona_glob_prefers_rg_or_find_command_search() -> None:
    process = _FakeDaytonaProcess(
        [
            SimpleNamespace(
                result=(
                    "__LAMBCHAT_GLOB_MODE__:rg\n"
                    "/workspace/hello.py\n"
                    "/workspace/project/hello.py\n"
                    "/workspace/project/lib/hello.py\n"
                ),
                exit_code=0,
            )
        ]
    )
    backend = DaytonaBackend(sandbox=_FakeDaytonaSandbox(process))

    result = backend.glob("**/hello.py", path="/")

    command = process.calls[0][0]
    assert "rg --files" in command
    assert result.matches == [
        {"path": "/workspace/hello.py"},
        {"path": "/workspace/project/hello.py"},
        {"path": "/workspace/project/lib/hello.py"},
    ]


def test_daytona_glob_find_fallback_matches_recursive_glob_segments() -> None:
    process = _FakeDaytonaProcess(
        [
            SimpleNamespace(
                result=(
                    "__LAMBCHAT_GLOB_MODE__:find\n"
                    "/workspace/src/tests/root.py\n"
                    "/workspace/src/pkg/tests/nested.py\n"
                    "/workspace/src/pkg/deep/tests/deep.py\n"
                    "/workspace/src/pkg/not-tests/deep.py\n"
                    "/workspace/tests/outside.py\n"
                ),
                exit_code=0,
            )
        ]
    )
    backend = DaytonaBackend(sandbox=_FakeDaytonaSandbox(process))

    result = backend.glob("src/**/tests/*.py", path="/")

    assert result.matches == [
        {"path": "/workspace/src/tests/root.py"},
        {"path": "/workspace/src/pkg/tests/nested.py"},
        {"path": "/workspace/src/pkg/deep/tests/deep.py"},
    ]

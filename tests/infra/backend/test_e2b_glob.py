from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import deepagents.backends.protocol as deepagents_protocol


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


e2b_module = _load_module_from_path("test_e2b_backend_glob_module", "src/infra/backend/e2b.py")
E2BBackend = e2b_module.E2BBackend


class _FakeFilesAPI:
    def __init__(self, responses: dict[str, list[SimpleNamespace]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def list(self, path: str):
        self.calls.append(path)
        return self.responses.get(path, [])


class _FakeE2BSandbox:
    def __init__(self, files_api: _FakeFilesAPI) -> None:
        self.sandbox_id = "e2b-test"
        self.files = files_api


def test_e2b_glob_scopes_root_search_to_work_dir() -> None:
    files_api = _FakeFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/home/user/project", is_dir=True, size=0),
                SimpleNamespace(path="/home/user/readme.md", is_dir=False, size=12),
            ],
            "/home/user/project": [
                SimpleNamespace(path="/home/user/project/app.py", is_dir=False, size=42),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    result = backend.glob("*.py", path="/")

    assert files_api.calls[0] == "/home/user"
    assert result["matches"] == [{"path": "/home/user/project/app.py", "size": 42}]


def test_e2b_glob_skips_sys_dev_proc_dirs() -> None:
    files_api = _FakeFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/proc/1/cwd", is_dir=True, size=0),
                SimpleNamespace(path="/sys/kernel", is_dir=True, size=0),
                SimpleNamespace(path="/dev/null", is_dir=False, size=0),
                SimpleNamespace(path="/home/user/normal.txt", is_dir=False, size=5),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    result = backend.glob("*", path="/")

    assert [m["path"] for m in result["matches"]] == ["/home/user/normal.txt"]


def test_e2b_glob_skips_symlink_dirs() -> None:
    import os

    original_islink = os.path.islink

    def _patched_islink(path: str) -> bool:
        if path == "/home/user/link_dir":
            return True
        return original_islink(path)

    os.path.islink = _patched_islink
    try:
        files_api = _FakeFilesAPI(
            {
                "/home/user": [
                    SimpleNamespace(path="/home/user/link_dir", is_dir=True, size=0),
                    SimpleNamespace(path="/home/user/real_dir", is_dir=True, size=0),
                    SimpleNamespace(path="/home/user/file.txt", is_dir=False, size=3),
                ],
                "/home/user/real_dir": [
                    SimpleNamespace(path="/home/user/real_dir/inner.py", is_dir=False, size=10),
                ],
            }
        )
        backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

        result = backend.glob("*", path="/")

        matched_paths = [m["path"] for m in result["matches"]]
        assert "/home/user/link_dir" not in matched_paths
        assert "/home/user/real_dir/inner.py" in matched_paths
    finally:
        os.path.islink = original_islink


def test_e2b_glob_no_infinite_loop_on_visited_paths() -> None:
    files_api = _FakeFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/home/user/a", is_dir=True, size=0),
            ],
            "/home/user/a": [
                SimpleNamespace(path="/home/user/a/file.txt", is_dir=False, size=1),
                SimpleNamespace(path="/home/user", is_dir=True, size=0),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    result = backend.glob("*", path="/")

    assert len(files_api.calls) < 20  # would blow up without visited guard
    assert any(m["path"] == "/home/user/a/file.txt" for m in result["matches"])

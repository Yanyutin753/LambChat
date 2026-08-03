from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeSkillStorage:
    def __init__(self) -> None:
        self.files = {
            "visible": {
                "SKILL.md": "visible skill",
                "notes.txt": "needle in visible notes",
            },
        }

    async def get_effective_skills(self, user_id: str) -> dict:
        return {
            "skills": {
                name: {
                    "name": name,
                    "description": f"Skill: {name}",
                    "files": files,
                    "enabled": True,
                }
                for name, files in self.files.items()
            }
        }

    async def get_skill_file(self, skill_name: str, file_name: str, user_id: str) -> str | None:
        return self.files.get(skill_name, {}).get(file_name)

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        return list(self.files.get(skill_name, {}).keys())

    async def batch_get_skill_files(self, skill_keys: list[tuple[str, str]]) -> dict:
        return {
            (skill_name, user_id): self.files.get(skill_name, {})
            for skill_name, user_id in skill_keys
        }

    async def get_all_user_skill_names(self, user_id: str, limit: int | None = None) -> list[str]:
        names = sorted(self.files.keys())
        return names[:limit] if limit is not None else names


class _FakeFilesAPI:
    def __init__(
        self,
        responses: dict[str, list[SimpleNamespace]],
        file_contents: dict[str, str] | None = None,
    ) -> None:
        self.responses = responses
        self.file_contents = file_contents or {}

    def list(self, path: str):
        return self.responses.get(path, [])

    def read(self, path: str, format: str = "text"):
        if format != "text":
            raise AssertionError(f"unexpected format: {format}")
        return self.file_contents[path]


class _FakeDownloadFilesAPI:
    def __init__(self, entries: dict[str, list[SimpleNamespace]]) -> None:
        self.entries = entries
        self.read_calls: list[tuple[str, str]] = []

    def list(self, path: str):
        return self.entries.get(path, [])

    def read(self, path: str, format: str = "text"):
        self.read_calls.append((path, format))
        return b"x" * 1024


class _FakeE2BSandbox:
    def __init__(self, files_api: _FakeFilesAPI) -> None:
        self.sandbox_id = "e2b-test"
        self.files = files_api


def test_skills_store_backend_supports_current_deepagents_protocol() -> None:
    from src.infra.backend import SkillsStoreBackend

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    entries = backend.ls_info("/skills/")
    assert entries == [{"path": "/visible/", "is_dir": True}]

    content = backend.read("/skills/visible/SKILL.md")
    assert "visible skill" in content

    matches = backend.glob_info("*", "/skills/")
    assert matches == [{"path": "/visible/", "is_dir": True}]


def test_e2b_backend_supports_current_deepagents_protocol() -> None:
    from src.infra.backend.e2b import E2BBackend

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

    entries = backend.ls_info("/home/user")
    assert entries == [
        {"path": "/home/user/project", "is_dir": True, "size": 0},
        {"path": "/home/user/readme.md", "size": 12},
    ]

    matches = backend.glob_info("*.py", path="/")
    assert matches == [{"path": "/home/user/project/app.py", "size": 42}]


def test_e2b_backend_read_slices_file_data_for_offset_reads() -> None:
    from src.infra.backend.e2b import E2BBackend

    files_api = _FakeFilesAPI(
        responses={},
        file_contents={
            "/home/user/readme.md": "alpha\nbeta\ngamma\ndelta\n",
        },
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    result = backend.read("/home/user/readme.md", offset=1, limit=2)

    assert result.file_data["content"] == "beta\ngamma\n"
    assert "2\tbeta" in str(result)
    assert "3\tgamma" in str(result)


def test_e2b_download_files_skips_large_file_before_reading(monkeypatch) -> None:
    from src.infra.backend.e2b import E2BBackend

    monkeypatch.setattr("src.infra.backend.e2b.SANDBOX_DOWNLOAD_MAX_BYTES", 8)
    files_api = _FakeDownloadFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/home/user/large.bin", is_dir=False, size=9),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    responses = backend.download_files(["/home/user/large.bin"])

    assert responses[0].content is None
    assert files_api.read_calls == []


def test_e2b_read_skips_large_file_before_text_read(monkeypatch) -> None:
    from src.infra.backend.e2b import E2BBackend

    monkeypatch.setattr("src.infra.backend.e2b.SANDBOX_READ_MAX_BYTES", 8)
    files_api = _FakeDownloadFilesAPI(
        {
            "/home/user": [
                SimpleNamespace(path="/home/user/large.txt", is_dir=False, size=9),
            ],
        }
    )
    backend = E2BBackend(sandbox=_FakeE2BSandbox(files_api))

    result = backend.read("/home/user/large.txt")

    assert "too large" in str(result)
    assert files_api.read_calls == []


def test_sandbox_backend_factory_anchors_artifacts_at_work_dir(monkeypatch) -> None:
    """The E2B sandbox CompositeBackend must use work_dir as artifacts_root.

    Regression test for issue #195: artifacts_root defaulted to '/', so the
    summarization middleware offloaded history to /conversation_history and hit
    a PermissionError on the non-root sandbox (exit code 1, empty error).
    """
    from src.infra.backend.deepagent import create_sandbox_backend_factory
    from src.infra.backend.e2b import E2BBackend

    monkeypatch.setattr(
        "src.infra.backend.skills_store.create_skills_backend",
        lambda **_kw: SimpleNamespace(),
    )

    backend = E2BBackend(sandbox=_FakeE2BSandbox(_FakeFilesAPI({})))
    composite = create_sandbox_backend_factory(backend, "asst-1", "user-1")(object())

    assert composite.artifacts_root == backend.work_dir
    assert composite.artifacts_root != "/"


def test_e2b_execute_surfaces_command_stderr_on_failure() -> None:
    """execute() must surface stderr/stdout from a failed command instead of an
    empty error string (issue #195 diagnostics)."""
    from src.infra.backend.e2b import E2BBackend

    class _CmdError(Exception):
        def __init__(self, message: str, stderr: str, stdout: str = "") -> None:
            super().__init__(message)
            self.stderr = stderr
            self.stdout = stdout

    class _Commands:
        def run(self, **_kwargs):
            raise _CmdError("Command exited with code 1", stderr="PermissionError: /")

    sandbox = SimpleNamespace(sandbox_id="e2b-test", commands=_Commands())
    backend = E2BBackend(sandbox=sandbox)

    result = backend.execute("echo hi")

    assert result.exit_code == -1
    assert "PermissionError" in result.output


def test_e2b_download_files_classifies_directory_error() -> None:
    """download_files must surface 'is_directory' instead of 'file_not_found'
    when the path is a directory (issue #196), matching upload_files behavior."""
    from src.infra.backend.e2b import E2BBackend

    class _FilesAPI:
        def list(self, path):
            return []

        def read(self, path, format="bytes"):
            raise Exception("path /home/user/project is a directory")

    sandbox = SimpleNamespace(sandbox_id="e2b-test", files=_FilesAPI())
    backend = E2BBackend(sandbox=sandbox)

    responses = backend.download_files(["/home/user/project"])

    assert responses[0].error == "is_directory"
    assert responses[0].content is None


@pytest.mark.asyncio
async def test_probe_download_error_reads_structured_error() -> None:
    """_probe_download_error surfaces the structured download error so
    reveal_file can tell a directory from a missing file (issue #196)."""
    from src.infra.tool.reveal_file_tool import _probe_download_error

    class _Resp:
        def __init__(self, error):
            self.error = error
            self.content = None

    class _Backend:
        def __init__(self, error):
            self._error = error

        async def adownload_files(self, paths):
            return [_Resp(self._error)]

    assert await _probe_download_error(_Backend("is_directory"), "/d") == "is_directory"
    assert await _probe_download_error(_Backend("file_not_found"), "/d") == "file_not_found"
    assert await _probe_download_error(_Backend(None), "/d") is None

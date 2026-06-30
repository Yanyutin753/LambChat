from __future__ import annotations

from types import SimpleNamespace


class _FakeCommandsAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stdout="cube-ok\n", stderr="", exit_code=0)


class _FakeFilesAPI:
    def __init__(self) -> None:
        self.contents: dict[str, str | bytes] = {}

    def write(self, path: str, data: str | bytes) -> None:
        self.contents[path] = data

    def read(self, path: str, format: str = "text"):
        data = self.contents[path]
        if format == "bytes":
            return data.encode("utf-8") if isinstance(data, str) else data
        return data.decode("utf-8") if isinstance(data, bytes) else data

    def list(self, path: str):
        return [
            SimpleNamespace(path=item_path, is_dir=False, size=len(value))
            for item_path, value in self.contents.items()
            if item_path.rsplit("/", 1)[0] == path.rstrip("/")
        ]


class _FakeCubeSandbox:
    def __init__(self) -> None:
        self.sandbox_id = "cube-test"
        self.commands = _FakeCommandsAPI()
        self.files = _FakeFilesAPI()


def test_cubesandbox_backend_executes_commands_in_work_dir() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.execute("pwd")

    assert result.exit_code == 0
    assert result.output == "cube-ok\n"
    assert sandbox.commands.calls[0]["cmd"].startswith(
        "mkdir -p /home/user/session-a && cd /home/user/session-a && pwd"
    )


def test_cubesandbox_backend_reads_and_writes_files() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    write_result = backend.write("note.txt", "hello cube")
    read_result = backend.read("note.txt")

    assert write_result.error is None
    assert read_result.file_data["content"] == "hello cube"


def test_cubesandbox_backend_uses_cube_timeout(monkeypatch) -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    monkeypatch.setattr("src.infra.backend.cubesandbox.settings.CUBE_TIMEOUT", 77)
    monkeypatch.setattr("src.infra.backend.cubesandbox.settings.E2B_TIMEOUT", 999)

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox)

    backend.execute("echo timeout")

    assert sandbox.commands.calls[0]["timeout"] == 77


def test_cubesandbox_backend_caches_parent_dir_creation() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    backend.write("nested/one.txt", "one")
    backend.write("nested/two.txt", "two")

    mkdir_calls = [
        call
        for call in sandbox.commands.calls
        if "mkdir -p /home/user/session-a/nested" in call["cmd"]
    ]
    assert len(mkdir_calls) == 1

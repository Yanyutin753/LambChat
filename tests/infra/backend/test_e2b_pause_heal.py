"""E2BBackend 长任务自愈：超时续期、暂停唤醒重试、重建通知。"""

from __future__ import annotations

from typing import Any

from src.infra.backend.e2b import E2BBackend


def _ok(stdout: str = "ok\n") -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(stdout=stdout, stderr="", exit_code=0)


class _FakeCommands:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.outcomes:
            return _ok()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeFiles:
    def __init__(self) -> None:
        self.read_outcomes: list[Any] = []
        self.read_calls = 0

    def read(self, path: str, format: str = "text") -> Any:
        self.read_calls += 1
        if self.read_outcomes:
            outcome = self.read_outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return "file-content"


class _FakeE2BSandbox:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.sandbox_id = "e2b-heal"
        self.commands = _FakeCommands(outcomes or [])
        self.files = _FakeFiles()
        self.set_timeout_calls: list[int] = []
        self.connect_calls: list[int | None] = []

    def set_timeout(self, timeout: int) -> None:
        self.set_timeout_calls.append(timeout)

    def connect(self, timeout: int | None = None) -> None:
        self.connect_calls.append(timeout)


def test_execute_extends_timeout_on_first_command_then_throttles(
    monkeypatch: Any,
) -> None:
    sandbox = _FakeE2BSandbox([_ok(), _ok()])
    backend = E2BBackend(sandbox=sandbox, timeout=600)
    clock = {"now": 100.0}
    monkeypatch.setattr("src.infra.backend.e2b.time.monotonic", lambda: clock["now"])

    backend.execute("ls")
    assert sandbox.set_timeout_calls == [600]

    backend.execute("ls")
    assert sandbox.set_timeout_calls == [600]  # 未到间隔，不重复续期


def test_execute_extends_again_after_keepalive_interval(monkeypatch: Any) -> None:
    sandbox = _FakeE2BSandbox([_ok(), _ok()])
    backend = E2BBackend(sandbox=sandbox, timeout=600)
    clock = {"now": 100.0}
    monkeypatch.setattr("src.infra.backend.e2b.time.monotonic", lambda: clock["now"])

    backend.execute("ls")
    clock["now"] += 600 / 3 + 1
    backend.execute("ls")

    assert sandbox.set_timeout_calls == [600, 600]


def test_execute_wakes_and_retries_once_on_paused_error() -> None:
    sandbox = _FakeE2BSandbox(
        [RuntimeError("Sandbox is paused, resuming is required"), _ok("healed\n")]
    )
    backend = E2BBackend(sandbox=sandbox, timeout=600)

    result = backend.execute("long-task")

    assert result.exit_code == 0
    assert "healed" in (result.output or "")
    assert len(sandbox.commands.calls) == 2
    assert sandbox.connect_calls  # 唤醒过


def test_execute_does_not_retry_command_timeouts() -> None:
    sandbox = _FakeE2BSandbox([RuntimeError("Command timed out after 30 seconds")])
    backend = E2BBackend(sandbox=sandbox, timeout=600)

    result = backend.execute("sleep 999")

    assert result.exit_code == -1
    assert "timed out" in (result.output or "").lower()
    assert len(sandbox.commands.calls) == 1
    assert sandbox.connect_calls == []


def test_execute_appends_unavailable_guidance_after_repeated_failures() -> None:
    sandbox = _FakeE2BSandbox()
    backend = E2BBackend(sandbox=sandbox, timeout=600)

    outputs: list[str] = []
    for _ in range(3):
        sandbox.commands.outcomes = [
            RuntimeError("Sandbox is paused"),
            RuntimeError("Sandbox is paused"),
        ]
        result = backend.execute("flaky")
        outputs.append(result.output or "")

    assert "unavailable" in outputs[0].lower() or "Command failed" in outputs[0]
    assert "unavailable" in outputs[-1].lower()


async def test_aexecute_prefixes_startup_notice_once() -> None:
    sandbox = _FakeE2BSandbox([_ok("first\n"), _ok("second\n")])
    backend = E2BBackend(sandbox=sandbox, timeout=600)
    backend.sandbox_startup_notice = "[sandbox] rebuilt"

    first = await backend.aexecute("echo hi")
    second = await backend.aexecute("echo hi")

    assert (first.output or "").startswith("[sandbox] rebuilt")
    assert "first" in (first.output or "")
    assert not (second.output or "").startswith("[sandbox] rebuilt")


def test_read_wakes_and_retries_on_connection_error() -> None:
    sandbox = _FakeE2BSandbox()
    sandbox.files.read_outcomes = [ConnectionError("connection refused"), "file-content"]
    backend = E2BBackend(sandbox=sandbox, timeout=600)

    result = backend.read("/home/user/notes.txt")

    assert result.error is None
    assert result.file_data is not None
    assert sandbox.files.read_calls == 2
    assert sandbox.connect_calls

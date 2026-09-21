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


async def test_aexecute_prefixes_startup_notice_once(monkeypatch: Any) -> None:
    fake = _FakeAsyncSandbox([_ok("first\n"), _ok("second\n")])
    _patch_async_client(monkeypatch, fake)
    backend = E2BBackend(sandbox=_FakeE2BSandbox(), timeout=600)
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


def test_per_command_timeout_is_not_capped_by_sandbox_timeout() -> None:
    """单条命令超时与沙箱 timeout 解耦：显式给长超时按原样透传。"""
    sandbox = _FakeE2BSandbox([_ok()])
    backend = E2BBackend(sandbox=sandbox, timeout=300)

    backend.execute("long-build", timeout=1200)

    assert sandbox.commands.calls[0]["timeout"] == 1200


def test_default_command_timeout_keeps_15min_floor() -> None:
    """沙箱 timeout 调小后，单条命令默认上限保持 15 分钟（生产历史行为）。"""
    sandbox = _FakeE2BSandbox([_ok()])
    backend = E2BBackend(sandbox=sandbox, timeout=300)

    backend.execute("pip install")

    assert sandbox.commands.calls[0]["timeout"] == 900


def test_long_command_runs_midflight_keepalive(monkeypatch: Any) -> None:
    """超过沙箱 timeout 的命令执行期间，后台线程持续续期沙箱。"""
    import time as time_mod

    monkeypatch.setattr("src.infra.backend.e2b._KEEPALIVE_MIN_INTERVAL", 0.02)
    sandbox = _FakeE2BSandbox()

    def slow_run(**kwargs: Any):
        sandbox.commands.calls.append(kwargs)
        time_mod.sleep(0.12)  # 跨多个续期间隔
        return _ok("done\n")

    sandbox.commands.run = slow_run  # type: ignore[method-assign]
    # timeout=0.08 → 续期间隔 max(0.02, 0.08/4)=0.02，0.12s 命令内应续期多次
    backend = E2BBackend(sandbox=sandbox, timeout=0.08)

    before = len(sandbox.set_timeout_calls)
    result = backend.execute("long-task", timeout=900)
    during = len(sandbox.set_timeout_calls) - before

    assert result.exit_code == 0
    assert during >= 2  # 命令期间后台续期了多次


def test_short_command_skips_midflight_keepalive() -> None:
    """命令必在沙箱死限内结束时不额外起续期线程。"""
    sandbox = _FakeE2BSandbox([_ok()])
    backend = E2BBackend(sandbox=sandbox, timeout=300)

    backend.execute("echo hi", timeout=60)

    # 只有命令前的常规 keepalive 一次，命令期间没有额外续期
    assert sandbox.set_timeout_calls == [300]


class _FakeAsyncCommands:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict] = []

    async def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.outcomes:
            return _ok()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeAsyncSandbox:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.sandbox_id = "e2b-async"
        self.commands = _FakeAsyncCommands(outcomes)
        self.set_timeout_calls: list[int] = []
        self.connect_calls: list[int | None] = []

    async def connect(self, timeout: int | None = None) -> None:
        self.connect_calls.append(timeout)

    async def set_timeout(self, timeout: int) -> None:
        self.set_timeout_calls.append(timeout)


def _patch_async_client(monkeypatch: Any, fake: _FakeAsyncSandbox) -> None:
    from src.infra.backend import e2b as e2b_mod

    async def fake_client(self):
        return fake

    monkeypatch.setattr(e2b_mod.E2BBackend, "_async_sandbox", fake_client)


async def test_aexecute_runs_native_async_without_thread_pool(monkeypatch: Any) -> None:
    """e2b 命令走原生 async 客户端，不再占用阻塞 IO 线程池。"""
    import asyncio

    from src.infra.backend import e2b as e2b_mod

    async def _pool_must_not_be_used(*_args, **_kwargs):
        raise AssertionError("thread pool used for e2b async command")

    monkeypatch.setattr(e2b_mod, "run_long_blocking_io", _pool_must_not_be_used)
    monkeypatch.setattr(e2b_mod, "run_blocking_io", _pool_must_not_be_used)

    fake = _FakeAsyncSandbox([_ok("native-async\n")])
    _patch_async_client(monkeypatch, fake)
    backend = e2b_mod.E2BBackend(sandbox=_FakeE2BSandbox(), timeout=300)

    result = await asyncio.wait_for(backend.aexecute("echo hi"), timeout=5)

    assert result.exit_code == 0
    assert "native-async" in (result.output or "")


async def test_aexecute_async_wakes_and_retries_on_paused(monkeypatch: Any) -> None:
    import asyncio

    from src.infra.backend import e2b as e2b_mod

    fake = _FakeAsyncSandbox([RuntimeError("Sandbox is paused"), _ok("awake-ok\n")])
    client_fetches = {"n": 0}

    async def counting_client(self):
        client_fetches["n"] += 1
        return fake

    monkeypatch.setattr(e2b_mod.E2BBackend, "_async_sandbox", counting_client)
    backend = e2b_mod.E2BBackend(sandbox=_FakeE2BSandbox(), timeout=300)

    result = await asyncio.wait_for(backend.aexecute("task"), timeout=5)

    assert result.exit_code == 0
    assert len(fake.commands.calls) == 2
    assert client_fetches["n"] >= 2  # wake 重连了 async 客户端


async def test_aexecute_async_midflight_keepalive_task(monkeypatch: Any) -> None:
    import asyncio

    from src.infra.backend import e2b as e2b_mod

    monkeypatch.setattr(e2b_mod, "_KEEPALIVE_MIN_INTERVAL", 0.02)
    fake = _FakeAsyncSandbox()

    async def slow_run(**kwargs: Any) -> Any:
        fake.commands.calls.append(kwargs)
        await asyncio.sleep(0.12)
        return _ok("kept-alive\n")

    fake.commands.run = slow_run  # type: ignore[method-assign]
    _patch_async_client(monkeypatch, fake)
    backend = e2b_mod.E2BBackend(sandbox=_FakeE2BSandbox(), timeout=0.08)

    before = len(fake.set_timeout_calls)
    result = await asyncio.wait_for(backend.aexecute("long", timeout=900), timeout=10)
    during = len(fake.set_timeout_calls) - before

    assert result.exit_code == 0
    assert during >= 2  # asyncio keeper 周期续期


async def test_cube_falls_back_to_thread_lane_when_e2b_client_unavailable(
    monkeypatch: Any,
) -> None:
    """Cube 名下 e2b 兼容客户端建不起来（如本测试的本地假地址）：
    aexecute 自动回落线程慢道，行为不倒退。"""
    import asyncio

    from src.infra.backend import e2b as e2b_mod
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    routed: list[str] = []

    async def fake_long_run(func, *args, timeout=None, **kwargs):
        routed.append("long")
        return func(*args, **kwargs)

    monkeypatch.setattr(e2b_mod, "run_long_blocking_io", fake_long_run)

    from types import SimpleNamespace

    sandbox = SimpleNamespace(
        sandbox_id="cube-lane",
        commands=SimpleNamespace(
            run=lambda **kw: SimpleNamespace(stdout="ok\n", stderr="", exit_code=0)
        ),
        files=SimpleNamespace(),
    )
    sandbox.set_timeout = lambda t: None  # type: ignore[method-assign]
    backend = CubeSandboxBackend(sandbox=sandbox, timeout=300)

    result = await asyncio.wait_for(backend.aexecute("echo hi"), timeout=5)

    assert routed == ["long"]
    assert result.exit_code == 0

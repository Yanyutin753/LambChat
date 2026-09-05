"""daemon 主循环：确认门控 / 执行回传 / 审计 / 退避重连 / 优雅下线。

测试策略：注入 fake client_factory / executor / confirm_fn / 内存 Auditor。
常驻循环的退出手法——连接流结束后 daemon 会重连，用「connect 即抛
TransportAuthError 的终结 client」让 run_daemon 自然上抛退出，顺带锁死
「认证失败不重连、直接上抛」的语义；优雅下线路径用 wait_for 取消驱动。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections import defaultdict
from pathlib import Path

import pytest

from lambchat_sandbox import cli
from lambchat_sandbox.audit import Auditor
from lambchat_sandbox.config import SandboxConfig
from lambchat_sandbox.daemon import DEFAULT_EXEC_TIMEOUT_S, _graceful_shutdown, run_daemon
from lambchat_sandbox.executor import ExecutorError
from lambchat_sandbox.transport import ToolCall, TransportAuthError, TransportError

PAT = "pat-secret-1"


# ---------- fakes ----------


class MemoryAuditor(Auditor):
    """内存审计器：记录 (session_id, event)，可选向共享事件流登记全局顺序。"""

    def __init__(self, events: list[str] | None = None) -> None:
        super().__init__(Path("/dev/null"))
        self.records: dict[str, list[dict]] = defaultdict(list)
        self._events = events

    def log(self, session_id: str, event: dict) -> None:
        self.records[session_id].append(dict(event))
        if self._events is not None:
            self._events.append(f"audit:{session_id}:{event.get('event')}")


class FakeClient:
    """通道客户端替身：脚本化 tool_call 流 / connect 抛错 / 永不产出的挂起流。"""

    def __init__(
        self,
        *,
        calls: list[ToolCall] | None = None,
        connect_error: Exception | None = None,
        hang: bool = False,
        events: list[str] | None = None,
    ) -> None:
        self._calls = list(calls or [])
        self._connect_error = connect_error
        self._hang = hang
        self._events = events
        self.posted: list[tuple[str, dict]] = []
        self.offline_count = 0
        self.close_count = 0

    async def connect(self):
        if self._connect_error is not None:
            raise self._connect_error
        if self._hang:
            return {"sandbox_id": "sbx-hang"}, _never()
        return {"sandbox_id": "sbx-fake"}, _aiter(self._calls)

    async def post_result(self, call_id: str, body: dict) -> None:
        self.posted.append((call_id, dict(body)))
        if self._events is not None:
            self._events.append(f"post:{call_id}:{body.get('stage')}")

    async def post_offline(self) -> None:
        self.offline_count += 1
        if self._events is not None:
            self._events.append("offline")

    async def close(self) -> None:
        self.close_count += 1
        if self._events is not None:
            self._events.append("closed")


class BrokenOfflineClient(FakeClient):
    """post_offline 必炸的替身：验证优雅下线的尽力而为语义。"""

    async def post_offline(self) -> None:
        raise TransportError("offline: HTTP 500")


class FakeFactory:
    """按脚本顺序发放 client 的工厂替身。"""

    def __init__(self, clients: list[FakeClient]) -> None:
        self._clients = list(clients)
        self.created: list[FakeClient] = []

    def __call__(self) -> FakeClient:
        client = self._clients.pop(0)
        self.created.append(client)
        return client


class FakeExecutor:
    """执行器替身：记录参数，返回脚本化结果或抛脚本化异常。"""

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self._result = (
            result
            if result is not None
            else {
                "status": "ok",
                "stdout": "out\n",
                "stderr": "",
                "exit_code": 0,
                "error": None,
            }
        )
        self._error = error
        self.calls: list[tuple[str, str, float]] = []

    def execute(self, command: str, virtual_cwd: str, timeout: float) -> dict:
        self.calls.append((command, virtual_cwd, timeout))
        if self._error is not None:
            raise self._error
        return dict(self._result)


class SleepRecorder:
    """sleep_fn 替身：记录退避秒数、绝不真睡。"""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def _aiter(calls: list[ToolCall]):
    for call in calls:
        yield call


async def _never():
    await asyncio.Event().wait()  # 挂起等待取消：模拟常驻 SSE 无任务
    yield  # pragma: no cover - 永不抵达


# ---------- helpers ----------


def _cfg(policy: str = "none", data_root: Path | None = None) -> SandboxConfig:
    return SandboxConfig(
        server_url="https://lc.example",
        data_root=data_root if data_root is not None else Path("/tmp/sbx-workspaces"),
        confirm_policy=policy,
    )


def _call(
    call_id: str = "c1",
    *,
    op: str = "exec",
    payload: dict | None = None,
    timeout: float = 5.0,
) -> ToolCall:
    if payload is None:
        payload = {"command": "echo hi", "cwd": "/workspace/s1"}
    return ToolCall(call_id=call_id, op=op, payload=payload, timeout=timeout)


def _terminator() -> FakeClient:
    """终结 client：connect 即抛认证错误，让常驻循环自然退出。"""
    return FakeClient(connect_error=TransportAuthError("channel: HTTP 401"))


async def _run(cfg, factory, *, executor, auditor, confirm_fn, sleep=None):
    """跑 run_daemon 直到 TransportAuthError 上抛；返回退避记录器。"""
    sleep_fn = sleep if sleep is not None else SleepRecorder()
    with pytest.raises(TransportAuthError):
        await run_daemon(
            cfg,
            pat=PAT,
            confirm_fn=confirm_fn,
            client_factory=factory,
            executor=executor,
            auditor=auditor,
            sleep_fn=sleep_fn,
        )
    return sleep_fn


def _boom_confirm(command: str) -> bool:
    raise AssertionError(f"不应触发确认: {command}")


# ---------- 放行路径 ----------


async def test_allow_path_posts_ack_then_executes_then_done():
    events: list[str] = []
    client = FakeClient(calls=[_call()], events=events)
    executor = FakeExecutor(
        result={"status": "ok", "stdout": "hi\n", "stderr": "", "exit_code": 0, "error": None}
    )
    auditor = MemoryAuditor()

    await _run(
        _cfg("none"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=_boom_confirm,  # policy=none：确认门根本不应被触碰
    )

    # 顺序与 payload：ack 先于执行结果，done 携带执行器五字段
    assert client.posted == [
        ("c1", {"stage": "ack"}),
        (
            "c1",
            {
                "stage": "done",
                "status": "ok",
                "stdout": "hi\n",
                "stderr": "",
                "exit_code": 0,
                "error": None,
            },
        ),
    ]
    assert events == ["post:c1:ack", "post:c1:done", "closed"]  # 关旧连接后才重连
    # 执行器收到帧内原始 command/cwd/timeout
    assert executor.calls == [("echo hi", "/workspace/s1", 5.0)]
    # 流结束后重连前关闭旧连接
    assert client.close_count == 1


async def test_allow_path_audits_received_allowed_executed_per_session():
    client = FakeClient(
        calls=[
            _call("c1", payload={"command": "echo a", "cwd": "/workspace/s1"}),
            _call("c2", payload={"command": "echo b", "cwd": "/workspace/s2"}),
        ]
    )
    auditor = MemoryAuditor()

    await _run(
        _cfg("none"),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert [e["event"] for e in auditor.records["s1"]] == ["received", "allowed", "executed"]
    assert [e["event"] for e in auditor.records["s2"]] == ["received", "allowed", "executed"]
    assert auditor.records["s1"][0]["command"] == "echo a"


async def test_confirm_true_passes_gate_with_policy_all():
    client = FakeClient(calls=[_call(payload={"command": "rm -rf /tmp/x", "cwd": "/workspace/s3"})])
    confirmed: list[str] = []

    def confirm(command: str) -> bool:
        confirmed.append(command)
        return True

    await _run(
        _cfg("all"),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=MemoryAuditor(),
        confirm_fn=confirm,
    )

    assert confirmed == ["rm -rf /tmp/x"]
    assert [body for _, body in client.posted][0] == {"stage": "ack"}


async def test_ack_is_posted_before_confirm_gate():
    """F3①：ack 先于确认门发出——用户盯着终端确认提示发呆时，dispatch 的 30s
    ack 死线不再被吃掉；确认等待改为计入执行超时窗口（迟到检查见下）。"""
    events: list[str] = []
    client = FakeClient(
        calls=[_call(payload={"command": "rm -rf /tmp/x", "cwd": "/workspace/s5"})], events=events
    )

    def confirm(command: str) -> bool:
        events.append(f"confirm:{command}")
        return True

    await _run(
        _cfg("all"),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=MemoryAuditor(),
        confirm_fn=confirm,
    )

    assert events[:2] == ["post:c1:ack", "confirm:rm -rf /tmp/x"]


async def test_late_call_after_slow_confirm_rejected_as_expired():
    """F3②：确认耗时超过 call.timeout 后即便放行也拒绝执行——dispatch 侧 exec
    死线已到，执行结果注定无人接收，done(expired) 快速失败且 executor 不被调用。"""
    client = FakeClient(
        calls=[_call(payload={"command": "rm -rf /tmp/x", "cwd": "/workspace/s5"}, timeout=0.2)]
    )
    executor = FakeExecutor()
    auditor = MemoryAuditor()

    def slow_confirm(command: str) -> bool:
        time.sleep(0.3)  # 超过 timeout=0.2：确认返回时调用已迟到
        return True

    await _run(
        _cfg("all"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=slow_confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        ("c1", {"stage": "done", "status": "error", "error": "expired"}),
    ]
    assert executor.calls == []  # 迟到即拒绝，不调 executor
    assert [e["event"] for e in auditor.records["s5"]] == ["received", "allowed", "expired"]


# ---------- 拒绝路径 ----------


async def test_decline_posts_ack_then_declined_by_user_without_execute():
    """拒绝路径：ack（收到即发）→ done(declined_by_user)；不执行、审计 declined。"""
    client = FakeClient(calls=[_call(payload={"command": "rm -rf /tmp/x", "cwd": "/workspace/s2"})])
    executor = FakeExecutor()
    auditor = MemoryAuditor()

    def confirm(command: str) -> bool:
        return False

    await _run(
        _cfg("all"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        ("c1", {"stage": "done", "status": "error", "error": "declined_by_user"}),
    ]
    assert executor.calls == []  # 拒绝即不执行
    assert [e["event"] for e in auditor.records["s2"]] == ["received", "declined"]


async def test_confirm_raising_is_treated_as_decline_and_keeps_channel():
    """confirm_fn 崩溃（如 stdin 关闭的 EOFError）按拒绝收敛，绝不拖断通道。"""

    def broken_confirm(command: str) -> bool:
        raise RuntimeError("stdin closed")

    client = FakeClient(calls=[_call()])
    executor = FakeExecutor()

    await _run(  # 走到重连并以认证错误收尾 == 通道未因 confirm 崩溃而中断
        _cfg("all"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=MemoryAuditor(),
        confirm_fn=broken_confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        ("c1", {"stage": "done", "status": "error", "error": "declined_by_user"}),
    ]
    assert executor.calls == []


# ---------- 执行结果透传 ----------


async def test_executor_timeout_result_translates_to_done_error_timeout():
    timeout_result = {
        "status": "error",
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error": "timeout",
    }
    client = FakeClient(
        calls=[_call(payload={"command": "sleep 5", "cwd": "/workspace/s4"}, timeout=0.3)]
    )
    auditor = MemoryAuditor()

    await _run(
        _cfg("none"),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(result=timeout_result),
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        (
            "c1",
            {
                "stage": "done",
                "status": "error",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "error": "timeout",
            },
        ),
    ]
    assert [e["event"] for e in auditor.records["s4"]] == ["received", "allowed", "executed"]


async def test_executor_raising_posts_error_done_and_keeps_channel():
    """非法 cwd 等执行器异常收敛为 done(error=str)，通道继续处理后续任务。"""
    error = ExecutorError("virtual_cwd 必须以 /workspace/ 开头: '/etc'")
    client = FakeClient(calls=[_call(payload={"command": "ls", "cwd": "/etc"})])
    executor = FakeExecutor(error=error)
    auditor = MemoryAuditor()

    await _run(
        _cfg("none"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        (
            "c1",
            {
                "stage": "done",
                "status": "error",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "error": str(error),
            },
        ),
    ]
    # 非法 cwd 的 session_id 回落 unknown，审计仍完整
    assert [e["event"] for e in auditor.records["unknown"]] == ["received", "allowed", "executed"]


async def test_unsupported_op_posts_ack_then_error_done_without_confirm_or_execute():
    call = _call("c9", op="download", payload={"path": "a.txt", "cwd": "/workspace/s9"})
    client = FakeClient(calls=[call])
    executor = FakeExecutor()
    auditor = MemoryAuditor()

    await _run(
        _cfg("all"),  # 即使 all 也不应触发确认：op 不认识直接回错误
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted == [
        ("c9", {"stage": "ack"}),
        ("c9", {"stage": "done", "status": "error", "error": "unsupported op: download"}),
    ]
    assert executor.calls == []
    assert [e["event"] for e in auditor.records["s9"]] == ["received"]


async def test_non_positive_timeout_falls_back_to_default():
    """帧缺失/为 0 的 timeout 回落默认值，避免 communicate(timeout=0) 立即超时。"""
    client = FakeClient(calls=[_call(timeout=0.0)])
    executor = FakeExecutor()

    await _run(
        _cfg("none"),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=MemoryAuditor(),
        confirm_fn=_boom_confirm,
    )

    assert executor.calls[0][2] == DEFAULT_EXEC_TIMEOUT_S


# ---------- 重连循环 ----------


async def test_connection_error_reconnects_with_backoff():
    flaky = FakeClient(connect_error=RuntimeError("connection refused"))
    good = FakeClient(calls=[])  # 连接成功但流立即结束
    auditor = MemoryAuditor()
    sleep = SleepRecorder()

    await _run(
        _cfg("none"),
        FakeFactory([flaky, good, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=_boom_confirm,
        sleep=sleep,
    )

    # 三次建连：失败 → 成功（流结束）→ 认证终结
    assert len(sleep.delays) == 2
    for delay in sleep.delays:
        assert 0.8 <= delay <= 1.2, delay  # backoff_delay(1) 基线 1s ±20% 抖动
    assert flaky.close_count == 1
    assert good.close_count == 1


async def test_backoff_resets_after_successful_connect():
    """连接成功清零退避：第二次退避仍是基线 1s 而非翻倍到 2s。"""
    first = FakeClient(calls=[])
    second = FakeClient(calls=[])
    sleep = SleepRecorder()

    await _run(
        _cfg("none"),
        FakeFactory([first, second, _terminator()]),
        executor=FakeExecutor(),
        auditor=MemoryAuditor(),
        confirm_fn=_boom_confirm,
        sleep=sleep,
    )

    assert len(sleep.delays) == 2
    for delay in sleep.delays:
        assert 0.8 <= delay <= 1.2, delay


# ---------- 优雅下线 ----------


async def test_graceful_shutdown_orders_offline_close_then_audit():
    events: list[str] = []
    client = FakeClient(events=events)
    auditor = MemoryAuditor(events=events)

    await _graceful_shutdown(client, auditor)

    assert events == ["offline", "closed", "audit:daemon:shutdown"]
    assert client.offline_count == 1
    assert client.close_count == 1


async def test_graceful_shutdown_tolerates_offline_failure():
    client = BrokenOfflineClient()
    auditor = MemoryAuditor()

    await _graceful_shutdown(client, auditor)  # offline 失败不得阻断 close/审计

    assert client.close_count == 1
    assert [e["event"] for e in auditor.records["daemon"]] == ["shutdown"]


async def test_cancellation_triggers_graceful_shutdown():
    """取消（SIGTERM/SIGINT 等价物）→ post_offline + close + 审计 shutdown。"""
    events: list[str] = []
    client = FakeClient(hang=True, events=events)
    auditor = MemoryAuditor(events=events)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            run_daemon(
                _cfg("none"),
                pat=PAT,
                confirm_fn=_boom_confirm,
                client_factory=lambda: client,
                executor=FakeExecutor(),
                auditor=auditor,
                sleep_fn=SleepRecorder(),
            ),
            timeout=0.2,
        )

    assert events == ["offline", "closed", "audit:daemon:shutdown"]


# ---------- CLI run / version 子命令 ----------


def _ns() -> argparse.Namespace:
    return argparse.Namespace()


def test_cmd_run_without_pat_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_pat", lambda: None)
    assert cli.cmd_run(_ns()) == 1
    assert "login" in capsys.readouterr().err


def test_cmd_run_auth_error_returns_1_with_relogin_hint(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_pat", lambda: PAT)
    monkeypatch.setattr(cli, "load_config", lambda: SandboxConfig())

    async def fake_daemon(cfg, *, pat):
        raise TransportAuthError("channel: HTTP 401")

    monkeypatch.setattr(cli, "run_daemon", fake_daemon)
    assert cli.cmd_run(_ns()) == 1
    assert "login" in capsys.readouterr().err


@pytest.mark.parametrize("exc", [KeyboardInterrupt, asyncio.CancelledError])
def test_cmd_run_interrupt_flavors_return_0(monkeypatch, capsys, exc):
    """SIGINT→KeyboardInterrupt、SIGTERM→CancelledError：都视为优雅下线。"""
    monkeypatch.setattr(cli, "load_pat", lambda: PAT)
    monkeypatch.setattr(cli, "load_config", lambda: SandboxConfig())

    async def fake_daemon(cfg, *, pat):
        raise exc

    monkeypatch.setattr(cli, "run_daemon", fake_daemon)
    assert cli.cmd_run(_ns()) == 0
    assert "下线" in capsys.readouterr().out


def test_cmd_run_invokes_run_daemon_with_loaded_config_and_pat(monkeypatch):
    monkeypatch.setattr(cli, "load_pat", lambda: PAT)
    cfg = SandboxConfig()
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    seen: dict[str, object] = {}

    async def fake_daemon(rcfg, *, pat):
        seen["cfg"] = rcfg
        seen["pat"] = pat

    monkeypatch.setattr(cli, "run_daemon", fake_daemon)
    assert cli.cmd_run(_ns()) == 0
    assert seen == {"cfg": cfg, "pat": PAT}


def test_cmd_version_prints_package_version(capsys):
    """CLI version 子命令：打印包 __version__（与服务端 daemon_version 同源）。"""
    from lambchat_sandbox import __version__

    assert cli.cmd_version(_ns()) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_main_dispatches_version_subcommand(capsys):
    from lambchat_sandbox import __version__

    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


# ---------- fs op 分发（M4 T3.5：win32 结构化文件操作直达 daemon） ----------


def _fs_call(
    call_id: str = "c1",
    *,
    op: str = "fs_read",
    payload: dict | None = None,
    timeout: float = 5.0,
) -> ToolCall:
    if payload is None:
        payload = {"path": "f.txt", "cwd": "/workspace/s1"}
    return ToolCall(call_id=call_id, op=op, payload=payload, timeout=timeout)


async def test_fs_read_dispatches_to_fsops_and_done_carries_result(tmp_path):
    """fs_read 真文件系统端到端：ack → done(status=ok, result=分页字段)；executor 不被触碰。"""
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1" / "f.txt").write_text("l1\nl2\n", encoding="utf-8")
    client = FakeClient(
        calls=[_fs_call(payload={"path": "f.txt", "cwd": "/workspace/s1", "offset": 0, "limit": 1})]
    )
    executor = FakeExecutor()
    auditor = MemoryAuditor()

    await _run(
        _cfg("none", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        (
            "c1",
            {
                "stage": "done",
                "status": "ok",
                "result": {
                    "encoding": "utf-8",
                    "content": "l1",
                    "total_lines": 2,
                    "start_line": 1,
                    "end_line": 1,
                    "next_offset": 1,
                },
            },
        ),
    ]
    assert executor.calls == []
    events = [e["event"] for e in auditor.records["s1"]]
    assert events == ["received", "allowed", "executed"]
    received = auditor.records["s1"][0]
    assert received["op"] == "fs_read" and received["path"] == "f.txt"


async def test_fs_write_passes_confirm_gate_with_description(tmp_path):
    """写类 fs op 过确认门：描述是 "fs_write sub/a.txt" 形式；放行后真实落盘。"""
    client = FakeClient(
        calls=[
            _fs_call(
                op="fs_write",
                payload={"path": "sub/a.txt", "cwd": "/workspace/s1", "content_b64": "aGVsbG8="},
            )
        ]
    )
    auditor = MemoryAuditor()
    confirmed: list[str] = []

    def confirm(description: str) -> bool:
        confirmed.append(description)
        return True

    await _run(
        _cfg("all", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=confirm,
    )

    assert confirmed == ["fs_write sub/a.txt"]
    assert (tmp_path / "s1" / "sub" / "a.txt").read_text(encoding="utf-8") == "hello"
    assert client.posted[1] == ("c1", {"stage": "done", "status": "ok", "result": {}})


async def test_fs_write_declined_leaves_file_untouched(tmp_path):
    client = FakeClient(
        calls=[
            _fs_call(
                op="fs_write",
                payload={"path": "a.txt", "cwd": "/workspace/s1", "content_b64": "aGVsbG8="},
            )
        ]
    )
    auditor = MemoryAuditor()

    await _run(
        _cfg("all", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=lambda description: False,
    )

    assert client.posted == [
        ("c1", {"stage": "ack"}),
        ("c1", {"stage": "done", "status": "error", "error": "declined_by_user"}),
    ]
    assert not (tmp_path / "s1" / "a.txt").exists()
    assert [e["event"] for e in auditor.records["s1"]] == ["received", "declined"]


async def test_fs_write_confirms_under_commands_policy(tmp_path):
    """commands 策略下写类 fs op 仍确认——它们天然是变更操作。"""
    client = FakeClient(
        calls=[_fs_call(op="fs_delete", payload={"path": "a.txt", "cwd": "/workspace/s1"})]
    )
    confirmed: list[str] = []

    await _run(
        _cfg("commands", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=MemoryAuditor(),
        confirm_fn=lambda d: (confirmed.append(d), True)[1],
    )

    assert confirmed == ["fs_delete a.txt"]


async def test_fs_read_skips_confirm_under_commands_policy(tmp_path):
    """读类 fs op 在 commands 策略下不确认（只读）。"""
    (tmp_path / "s1").mkdir()
    client = FakeClient(calls=[_fs_call()])
    auditor = MemoryAuditor()

    await _run(
        _cfg("commands", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted[1][1]["status"] == "ok"


async def test_fs_op_file_level_error_is_ok_status_with_result_error(tmp_path):
    """路径逃逸等结果级错误：done(status=ok, result.error=…)——模型可改路径重试。"""
    client = FakeClient(
        calls=[_fs_call(op="fs_read", payload={"path": "../../etc/passwd", "cwd": "/workspace/s1"})]
    )
    auditor = MemoryAuditor()

    await _run(
        _cfg("none", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    body = client.posted[1][1]
    assert body["status"] == "ok"
    assert "escape" in body["result"]["error"]
    assert [e["event"] for e in auditor.records["s1"]] == ["received", "allowed", "executed"]


async def test_fs_op_crash_converges_to_error_done_and_keeps_channel(tmp_path, monkeypatch):
    """fsops 内部异常收敛为 done(status=error)，通道继续处理后续任务。"""
    from lambchat_sandbox import daemon as daemon_module

    def boom(op, payload, data_root):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(daemon_module, "handle_fs_op", boom)
    ok_call = _call("c2", payload={"command": "echo ok", "cwd": "/workspace/s2"})
    client = FakeClient(calls=[_fs_call("c1"), ok_call])
    executor = FakeExecutor()
    auditor = MemoryAuditor()

    await _run(
        _cfg("none", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=executor,
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    assert client.posted[1] == (
        "c1",
        {"stage": "done", "status": "error", "error": "disk exploded"},
    )
    assert client.posted[3][1]["status"] == "ok"  # 后续 exec 正常
    assert [e["event"] for e in auditor.records["s1"]] == ["received", "allowed", "executed"]


async def test_fs_op_invalid_cwd_converges_to_error_done(tmp_path):
    """非法 cwd 的 fs op：ExecutorError → done(status=error)，不断连。"""
    client = FakeClient(calls=[_fs_call(payload={"path": "f.txt", "cwd": "/etc"})])
    auditor = MemoryAuditor()

    await _run(
        _cfg("none", data_root=tmp_path),
        FakeFactory([client, _terminator()]),
        executor=FakeExecutor(),
        auditor=auditor,
        confirm_fn=_boom_confirm,
    )

    body = client.posted[1][1]
    assert body["status"] == "error"
    assert "workspace" in body["error"]
    # 非法 cwd 的 session_id 回落 unknown
    assert [e["event"] for e in auditor.records["unknown"]] == ["received", "allowed", "executed"]


# ---------- 内嵌 Python 运行时装配（M4 T4：ensure_runtime + PATH 前置） ----------


async def _run_with_real_executor(cfg, monkeypatch, *, ensure_result, data_root):
    """不注入 executor（走 daemon 自建路径），monkeypatch pbs.ensure_runtime。

    返回 (client, ensure_calls)：client 收到一条 `echo $PATH` 的 exec 调用。
    """
    from lambchat_sandbox import daemon as daemon_module
    from lambchat_sandbox.executor import Executor

    ensure_calls: list[tuple] = []

    def fake_ensure(resources_dir, install_root):
        ensure_calls.append((resources_dir, install_root))
        return ensure_result

    monkeypatch.setattr(daemon_module.pbs, "ensure_runtime", fake_ensure)
    assert daemon_module.Executor is Executor  # 同一对象：monkeypatch ensure 即全链生效

    client = FakeClient(calls=[_call(payload={"command": "echo $PATH", "cwd": "/workspace/s1"})])
    auditor = MemoryAuditor()
    with pytest.raises(TransportAuthError):
        await run_daemon(
            cfg,
            pat=PAT,
            confirm_fn=_boom_confirm,
            client_factory=FakeFactory([client, _terminator()]),
            auditor=auditor,
            sleep_fn=SleepRecorder(),
        )
    return client, ensure_calls


async def test_daemon_prepends_ensure_runtime_bin_dir_to_executor_path(tmp_path, monkeypatch):
    """embedded_python=true（默认）：daemon 启动装配内嵌运行时，executor 子进程
    PATH 首段是 ensure_runtime 返回的 bin 目录。"""
    fake_bin = tmp_path / "embedded-bin"
    cfg = _cfg("none", data_root=tmp_path)
    client, ensure_calls = await _run_with_real_executor(
        cfg, monkeypatch, ensure_result=fake_bin, data_root=tmp_path
    )

    assert ensure_calls == [(None, None)]  # 默认 resources/install 路径交给 pbs 模块
    done = client.posted[1][1]
    assert done["status"] == "ok"
    assert done["stdout"].strip().split(":")[0] == str(fake_bin)


async def test_daemon_skips_ensure_runtime_when_embedded_python_false(tmp_path, monkeypatch):
    """embedded_python=false：不装配、不前置（走系统 PATH）。"""
    from lambchat_sandbox import daemon as daemon_module

    def boom_ensure(resources_dir, install_root):  # pragma: no cover - 调用即失败
        raise AssertionError("embedded_python=false 不应调用 ensure_runtime")

    monkeypatch.setattr(daemon_module.pbs, "ensure_runtime", boom_ensure)
    cfg = SandboxConfig(
        server_url="https://lc.example",
        data_root=tmp_path,
        confirm_policy="none",
        embedded_python=False,
    )
    client = FakeClient(calls=[_call(payload={"command": "echo $PATH", "cwd": "/workspace/s1"})])
    with pytest.raises(TransportAuthError):
        await run_daemon(
            cfg,
            pat=PAT,
            confirm_fn=_boom_confirm,
            client_factory=FakeFactory([client, _terminator()]),
            auditor=MemoryAuditor(),
            sleep_fn=SleepRecorder(),
        )

    done = client.posted[1][1]
    assert done["status"] == "ok"
    # PATH 首段是系统 PATH 首段（未被注入任何目录）
    assert done["stdout"].strip().split(":")[0] == os.environ["PATH"].split(":")[0]


async def test_daemon_falls_back_to_system_path_when_no_tarball(tmp_path, monkeypatch):
    """ensure_runtime 返回 None（无归档回退）：daemon 照常启动执行（仅告警）。"""
    cfg = _cfg("none", data_root=tmp_path)
    client, ensure_calls = await _run_with_real_executor(
        cfg, monkeypatch, ensure_result=None, data_root=tmp_path
    )
    assert ensure_calls  # 装配尝试发生过
    assert client.posted[1][1]["status"] == "ok"
    assert client.posted[1][1]["exit_code"] == 0


async def test_daemon_falls_back_when_ensure_runtime_raises(tmp_path, monkeypatch):
    """ensure_runtime 崩溃不阻断启动：回退系统 PATH 继续执行任务。"""
    from lambchat_sandbox import daemon as daemon_module

    def explode(resources_dir, install_root):
        raise RuntimeError("disk full")

    monkeypatch.setattr(daemon_module.pbs, "ensure_runtime", explode)
    cfg = _cfg("none", data_root=tmp_path)
    client = FakeClient(calls=[_call(payload={"command": "echo ok", "cwd": "/workspace/s1"})])
    with pytest.raises(TransportAuthError):
        await run_daemon(
            cfg,
            pat=PAT,
            confirm_fn=_boom_confirm,
            client_factory=FakeFactory([client, _terminator()]),
            auditor=MemoryAuditor(),
            sleep_fn=SleepRecorder(),
        )

    assert client.posted[1][1] == {
        "stage": "done",
        "status": "ok",
        "stdout": "ok\n",
        "stderr": "",
        "exit_code": 0,
        "error": None,
    }

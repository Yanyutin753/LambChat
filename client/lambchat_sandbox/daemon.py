"""daemon 主循环：把配对、通道、确认、执行、审计、重连组装成常驻进程。

生命周期（:func:`run_daemon`）：

- **外层重连循环**：``ChannelClient.connect`` 成功（收到 hello）即清零退避计数；
  连接失败或流中断按 :func:`backoff_delay` 指数退避重试；
- **单连接处理**（:func:`_handle_channel`）：逐条 ToolCall → 审计 ``received`` →
  ``ack``（**先于确认门**：收到即确认接收，用户盯着确认提示发呆不再吃 dispatch
  的 30s ack 死线，确认等待改计入执行超时窗口）→ 确认门控（拒绝 →
  ``done(status=error, error=declined_by_user)`` + 审计 ``declined``；放行 →
  审计 ``allowed``）→ 迟到检查（确认返回时 ``elapsed >= timeout`` →
  ``done(status=error, error=expired)`` + 审计 ``expired``，不执行）→
  ``executor.execute`` → ``done`` → 审计 ``executed``。执行器超时结果
  （``error="timeout"``）与其他异常都原样透传成 ``done``，绝不拖断通道；
- **退出**（SIGTERM/SIGINT/任务取消）→ :func:`_graceful_shutdown`：尽力
  ``post_offline`` → ``close`` → 审计 ``shutdown``；
- :class:`TransportAuthError`（401/403）直接上抛不重连、不 offline——
  PAT 已失效，offline 也只会再吃一次 401；CLI 捕获后提示重新 login。

信号取舍：SIGTERM 经 ``add_signal_handler`` 取消当前任务（Unix；Windows/
非主线程无此实现则静默跳过）；SIGINT 保持解释器默认——asyncio.Runner 会把
KeyboardInterrupt 转成任务取消走同一条优雅下线路径，且默认行为能在
terminal_confirm 阻塞于 ``input()`` 时立刻打断提示（换成 add_signal_handler
方案，事件循环被同步 ``input()`` 卡住时回调永远没有机会运行）。

注入点：``client_factory`` / ``executor`` / ``auditor`` / ``confirm_fn`` /
``sleep_fn`` 全部可替换，测试不碰网络、不真睡。
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from lambchat_sandbox.audit import Auditor
from lambchat_sandbox.config import SandboxConfig
from lambchat_sandbox.confirm import needs_confirm, terminal_confirm
from lambchat_sandbox.executor import Executor
from lambchat_sandbox.fsops import FS_OPS, WRITE_OPS, handle_fs_op
from lambchat_sandbox.transport import (
    ChannelClient,
    ToolCall,
    TransportAuthError,
    backoff_delay,
)

DEFAULT_AUDIT_ROOT = Path.home() / ".lambchat" / "audit"
DEFAULT_EXEC_TIMEOUT_S = 60.0  # 帧缺失/非正 timeout 的兜底，避免 communicate(timeout=0) 立即超时
DAEMON_AUDIT_SESSION = "daemon"  # shutdown 等进程级事件的审计会话（过 Auditor 白名单）

_DONE_KEYS = ("status", "stdout", "stderr", "exit_code", "error")


async def run_daemon(
    cfg: SandboxConfig,
    *,
    pat: str,
    confirm_fn: Callable[[str], bool] = terminal_confirm,
    client_factory: Callable[[], ChannelClient] | None = None,
    executor: Executor | None = None,
    auditor: Auditor | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """常驻主循环。正常退出只有一条路：任务被取消（SIGTERM/SIGINT）后优雅下线
    并重新抛出 CancelledError；:class:`TransportAuthError` 原样上抛交 CLI 提示。
    """
    factory = (
        client_factory if client_factory is not None else lambda: ChannelClient(cfg.server_url, pat)
    )
    executor_ = executor if executor is not None else Executor(cfg.data_root)
    auditor_ = auditor if auditor is not None else Auditor(DEFAULT_AUDIT_ROOT)
    installed = _install_sigterm_cancel()

    client: ChannelClient | None = None
    attempt = 0
    try:
        while True:
            if client is not None:
                await _silently_close(client)
                client = None
            client = factory()
            try:
                hello, calls = await client.connect()
                attempt = 0  # 连接建立（收到 hello）即清零退避
                print(f"[sandbox] 已连接 {cfg.server_url}（hello={hello}），等待任务…", flush=True)
                await _handle_channel(
                    client,
                    calls,
                    cfg=cfg,
                    confirm_fn=confirm_fn,
                    executor=executor_,
                    auditor=auditor_,
                )
            except TransportAuthError:
                await _silently_close(client)
                client = None
                raise  # PAT 失效：不重连、不 offline，交给 CLI 提示重新 login
            except Exception as exc:  # noqa: BLE001 - 任何单连接失败都退避重连
                print(f"[sandbox] 通道断开: {exc}；退避后重连…", file=sys.stderr, flush=True)
            attempt += 1
            # 保留当前 client（流已关但 httpx 连接池可用）跨退避窗口：取消时仍能 post_offline
            await sleep_fn(backoff_delay(attempt))
    finally:
        _remove_signal_handlers(installed)
        if client is not None:
            await _graceful_shutdown(client, auditor_)


async def _handle_channel(
    client: ChannelClient,
    calls: AsyncIterator[ToolCall],
    *,
    cfg: SandboxConfig,
    confirm_fn: Callable[[str], bool],
    executor: Executor,
    auditor: Auditor,
) -> None:
    """单次连接内逐条处理 ToolCall；流结束/异常交回外层重连循环。"""
    async for call in calls:
        await _process_call(
            client, call, cfg=cfg, confirm_fn=confirm_fn, executor=executor, auditor=auditor
        )


async def _process_call(
    client: ChannelClient,
    call: ToolCall,
    *,
    cfg: SandboxConfig,
    confirm_fn: Callable[[str], bool],
    executor: Executor,
    auditor: Auditor,
) -> None:
    """单条 ToolCall 的完整决策链：审计 received → ack → op 分发 → 确认门控 → 迟到检查 → 执行 → done。

    ack 先于确认门（收到即发）：确认等待计入执行超时窗口而非 dispatch 的 30s
    ack 死线——否则用户在终端确认提示前犹豫超过 30s，dispatch 侧就误报
    ``sandbox_timeout`` 而本地命令根本没跑。作为代价，确认放行后要检查迟到：
    ``elapsed >= timeout`` 说明 dispatch 的 exec 死线已到（或将近），执行结果
    注定无人接收，直接 ``done(error=expired)`` 快速失败，不浪费本机资源。

    op 分发（M4 T3.5）：``exec`` 走 executor（shell 命令）；``fs_*`` 走
    :func:`lambchat_sandbox.fsops.handle_fs_op`（win32 结构化文件操作——
    deepagents 的 POSIX 脚本命令 cmd.exe 跑不了，服务端改发结构化 op）；
    其余 op 回 ``unsupported`` 错误。
    """
    command = str(call.payload.get("command", ""))
    virtual_cwd = str(call.payload.get("cwd", ""))
    path = str(call.payload.get("path", ""))
    session_id = _session_id_from_cwd(virtual_cwd)
    started = time.monotonic()
    auditor.log(
        session_id,
        {
            "event": "received",
            "call_id": call.call_id,
            "op": call.op,
            "command": command,
            "path": path,
        },
    )
    await client.post_result(call.call_id, {"stage": "ack"})

    if call.op == "exec":
        await _process_exec_call(
            client,
            call,
            session_id=session_id,
            command=command,
            virtual_cwd=virtual_cwd,
            started=started,
            cfg=cfg,
            confirm_fn=confirm_fn,
            executor=executor,
            auditor=auditor,
        )
        return
    if call.op in FS_OPS:
        await _process_fs_call(
            client,
            call,
            session_id=session_id,
            path=path,
            started=started,
            cfg=cfg,
            confirm_fn=confirm_fn,
            auditor=auditor,
        )
        return

    await client.post_result(
        call.call_id,
        {"stage": "done", "status": "error", "error": f"unsupported op: {call.op}"},
    )


async def _process_exec_call(
    client: ChannelClient,
    call: ToolCall,
    *,
    session_id: str,
    command: str,
    virtual_cwd: str,
    started: float,
    cfg: SandboxConfig,
    confirm_fn: Callable[[str], bool],
    executor: Executor,
    auditor: Auditor,
) -> None:
    """op=exec 的执行链：确认门 → 迟到检查 → executor → done → 审计。"""
    if needs_confirm(command, cfg.confirm_policy) and not _confirm(command, confirm_fn):
        await client.post_result(
            call.call_id, {"stage": "done", "status": "error", "error": "declined_by_user"}
        )
        auditor.log(
            session_id,
            {"event": "declined", "call_id": call.call_id, "op": "exec", "command": command},
        )
        return

    auditor.log(
        session_id, {"event": "allowed", "call_id": call.call_id, "op": "exec", "command": command}
    )
    effective = call.timeout if call.timeout > 0 else DEFAULT_EXEC_TIMEOUT_S
    if time.monotonic() - started >= effective:
        await client.post_result(
            call.call_id, {"stage": "done", "status": "error", "error": "expired"}
        )
        auditor.log(
            session_id,
            {"event": "expired", "call_id": call.call_id, "op": "exec", "command": command},
        )
        return

    result = _execute(executor, command, virtual_cwd, effective)
    await client.post_result(
        call.call_id, {"stage": "done", **{k: result.get(k) for k in _DONE_KEYS}}
    )
    auditor.log(
        session_id,
        {
            "event": "executed",
            "call_id": call.call_id,
            "op": "exec",
            "command": command,
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
        },
    )


async def _process_fs_call(
    client: ChannelClient,
    call: ToolCall,
    *,
    session_id: str,
    path: str,
    started: float,
    cfg: SandboxConfig,
    confirm_fn: Callable[[str], bool],
    auditor: Auditor,
) -> None:
    """op=fs_* 的执行链：结果走同一 ack/done 协议，结果体放 ``result`` 字段。

    - **确认门**：写类 fs op（write/edit/delete）同样过 needs_confirm——用户
      看到的描述是 ``fs_write sub/a.txt`` 形式。``commands`` 策略按词匹配
      命令，``fs_write`` 不在变更清单里，但写类 fs op 天然变更状态，故以
      ``rm`` 前缀哨兵送判（命中清单即确认）；读类只读，不确认；
    - **错误两级**：文件级错误（不存在/逃逸/坏载荷）在 ``result`` 里（done
      的 status 仍是 ok——模型可改路径重试）；fsops 内部异常（含非法 cwd 的
      ExecutorError）收敛为 ``status=error``，与 exec 的对应路径对齐。
    """
    description = f"{call.op} {path}".rstrip()
    gate_command = description if call.op not in WRITE_OPS else f"rm {description}"
    if needs_confirm(gate_command, cfg.confirm_policy) and not _confirm(description, confirm_fn):
        await client.post_result(
            call.call_id, {"stage": "done", "status": "error", "error": "declined_by_user"}
        )
        auditor.log(
            session_id,
            {"event": "declined", "call_id": call.call_id, "op": call.op, "path": path},
        )
        return

    auditor.log(
        session_id, {"event": "allowed", "call_id": call.call_id, "op": call.op, "path": path}
    )
    effective = call.timeout if call.timeout > 0 else DEFAULT_EXEC_TIMEOUT_S
    if time.monotonic() - started >= effective:
        await client.post_result(
            call.call_id, {"stage": "done", "status": "error", "error": "expired"}
        )
        auditor.log(
            session_id, {"event": "expired", "call_id": call.call_id, "op": call.op, "path": path}
        )
        return

    try:
        result = handle_fs_op(call.op, call.payload, cfg.data_root)
    except Exception as exc:  # noqa: BLE001 - 单条 fs op 崩溃不拖垮通道
        await client.post_result(
            call.call_id, {"stage": "done", "status": "error", "error": str(exc)}
        )
        auditor.log(
            session_id,
            {
                "event": "executed",
                "call_id": call.call_id,
                "op": call.op,
                "path": path,
                "status": "error",
            },
        )
        return

    await client.post_result(call.call_id, {"stage": "done", "status": "ok", "result": result})
    auditor.log(
        session_id,
        {"event": "executed", "call_id": call.call_id, "op": call.op, "path": path, "status": "ok"},
    )


def _session_id_from_cwd(virtual_cwd: str) -> str:
    """``/workspace/{sid}`` → sid；不合法（含 ``..``、缺前缀等）回落 ``unknown``。"""
    prefix = "/workspace/"
    sid = virtual_cwd[len(prefix) :] if virtual_cwd.startswith(prefix) else ""
    if sid and "/" not in sid and sid not in (".", ".."):
        return sid
    return "unknown"


def _confirm(command: str, confirm_fn: Callable[[str], bool]) -> bool:
    """确认门：confirm_fn 抛异常（如 stdin 关闭的 EOFError）按拒绝收敛——
    fail-closed，绝不牵连通道。"""
    try:
        return bool(confirm_fn(command))
    except Exception:  # noqa: BLE001 - 确认端崩溃收敛为拒绝而非断连
        return False


def _execute(executor: Executor, command: str, virtual_cwd: str, timeout: float) -> dict:
    """执行并保证返回 done 契约 dict：executor 异常（如非法 cwd 的 ExecutorError）
    收敛为 ``status=error`` 的结果而非断连。"""
    effective = timeout if timeout > 0 else DEFAULT_EXEC_TIMEOUT_S
    try:
        return executor.execute(command, virtual_cwd, effective)
    except Exception as exc:  # noqa: BLE001 - 单条命令失败不拖垮通道
        return {"status": "error", "stdout": "", "stderr": "", "exit_code": None, "error": str(exc)}


async def _graceful_shutdown(client: ChannelClient, auditor: Auditor) -> None:
    """优雅下线语义：post_offline（尽力而为）→ close → 审计 shutdown。"""
    with contextlib.suppress(Exception):
        await client.post_offline()
    with contextlib.suppress(Exception):
        await client.close()
    auditor.log(DAEMON_AUDIT_SESSION, {"event": "shutdown"})


async def _silently_close(client: ChannelClient) -> None:
    with contextlib.suppress(Exception):
        await client.close()


def _install_sigterm_cancel() -> list[signal.Signals]:
    """注册 SIGTERM→取消当前任务；返回已注册信号（供退出时移除）。"""
    task = asyncio.current_task()
    if task is None:  # 协程内必有任务；防御性兜底
        return []
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
    except (NotImplementedError, RuntimeError, ValueError):
        return []  # Windows Proactor / 非主线程：跳过，依赖 SIGINT/外部取消
    return [signal.SIGTERM]


def _remove_signal_handlers(installed: list[signal.Signals]) -> None:
    if not installed:
        return
    loop = asyncio.get_running_loop()
    for sig in installed:
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.remove_signal_handler(sig)

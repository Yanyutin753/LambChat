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
  PAT 已失效，offline 也只会再吃一次 401；CLI 捕获后提示重新 login；
- :class:`UpdateRequiredError`（426 版本门）同样上抛不重连、不 offline——
  版本过低时重连毫无意义，CLI 捕获后以退出码 1 停机（daemon 侧已打印
  ``lambchat_sandbox update`` 升级指引）。

信号取舍：SIGTERM 经 ``add_signal_handler`` 取消当前任务（Unix；Windows/
非主线程无此实现则静默跳过）；SIGINT 保持解释器默认——asyncio.Runner 会把
KeyboardInterrupt 转成任务取消走同一条优雅下线路径。

注入点：``client_factory`` / ``executor`` / ``auditor`` / ``sleep_fn`` 全部
可替换，测试不碰网络、不真睡。
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from lambchat_sandbox import pbs
from lambchat_sandbox.audit import Auditor
from lambchat_sandbox.config import SandboxConfig
from lambchat_sandbox.executor import Executor
from lambchat_sandbox.fsops import FS_OPS, handle_fs_op
from lambchat_sandbox.transport import (
    ChannelClient,
    ToolCall,
    TransportAuthError,
    UpdateRequiredError,
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
    client_factory: Callable[[], ChannelClient] | None = None,
    executor: Executor | None = None,
    auditor: Auditor | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """常驻主循环。正常退出只有一条路：任务被取消（SIGTERM/SIGINT）后优雅下线
    并重新抛出 CancelledError；:class:`TransportAuthError` 原样上抛交 CLI 提示。
    """
    factory = (
        client_factory
        if client_factory is not None
        else lambda: ChannelClient(cfg.server_url, pat, confirm_policy=cfg.confirm_policy)
    )
    # 启动即装配内嵌 Python 运行时（embedded_python=true 且归档在位时）：
    # shim bin 目录前置进 executor 子进程 PATH，python3 命中内嵌解释器。
    # 注入 executor（测试替身）不经此路径——PATH 注入在 Executor 构造期完成。
    executor_ = (
        executor
        if executor is not None
        else Executor(cfg.data_root, extra_path=_ensure_runtime_bin(cfg))
    )
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
                    executor=executor_,
                    auditor=auditor_,
                )
            except TransportAuthError:
                await _silently_close(client)
                client = None
                raise  # PAT 失效：不重连、不 offline，交给 CLI 提示重新 login
            except UpdateRequiredError as exc:
                # 版本门拒连（426）：打印升级指引后停机退出——退避重连没有
                # 意义（版本不会自己变新）；本 daemon 从未 register，不
                # post_offline（offline 会误踢同账号在线的新版本 daemon）。
                await _silently_close(client)
                client = None
                print(
                    f"[sandbox] 客户端版本过低，服务端拒绝连接（{exc}）；"
                    "请运行 lambchat_sandbox update 升级后重启",
                    file=sys.stderr,
                    flush=True,
                )
                raise
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
    executor: Executor,
    auditor: Auditor,
) -> None:
    """单次连接内逐条处理 ToolCall；流结束/异常交回外层重连循环。"""
    async for call in calls:
        await _process_call(client, call, cfg=cfg, executor=executor, auditor=auditor)


async def _process_call(
    client: ChannelClient,
    call: ToolCall,
    *,
    cfg: SandboxConfig,
    executor: Executor,
    auditor: Auditor,
) -> None:
    """单条 ToolCall 的完整决策链：审计 received → ack → op 分发 → 迟到检查 → 执行 → done。

    确认门控不在本层（spec §3.5 服务端实现）：服务端统一确认门在 dispatch
    前以 ask_human interrupt 完成，daemon 只收到已确认的执行请求，到达即执行。
    ``confirm_policy`` 仍随连接上报（connect URL 第四段）供服务端门读取。

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
    executor: Executor,
    auditor: Auditor,
) -> None:
    """op=exec 的执行链：迟到检查 → executor → done → 审计（确认在服务端）。

    ``payload["env"]``（服务端用户 env 变量，对齐云端 envs= 语义）净化后
    透传 executor 合并进子进程环境——非 dict 载荷或非 str 条目静默丢弃，
    坏 env 不让命令失败。
    """
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

    result = _execute(executor, command, virtual_cwd, effective, _sanitize_env(call.payload))
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
    auditor: Auditor,
) -> None:
    """op=fs_* 的执行链：结果走同一 ack/done 协议，结果体放 ``result`` 字段。

    - **确认在服务端**：到达即已确认（写类同样——服务端在 override 入口过
      统一确认门后才发 fs op），daemon 不再做本地门控；
    - **错误两级**：文件级错误（不存在/逃逸/坏载荷）在 ``result`` 里（done
      的 status 仍是 ok——模型可改路径重试）；fsops 内部异常（含非法 cwd 的
      ExecutorError）收敛为 ``status=error``，与 exec 的对应路径对齐。
    """
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


def _ensure_runtime_bin(cfg: SandboxConfig) -> Path | None:
    """daemon 启动时装配内嵌 PBS 运行时，返回 shim bin 目录（None = 系统 PATH）。

    任何装配失败（归档损坏/磁盘异常）都只告警回退，绝不阻断启动——沙箱的
    存在价值首先是不掉线。回退语义详见 :mod:`lambchat_sandbox.pbs`。
    """
    if not cfg.embedded_python:
        return None
    try:
        return pbs.ensure_runtime(None, None)
    except Exception as exc:  # noqa: BLE001 - 装配异常回退系统 PATH，不阻断启动
        print(f"[sandbox] 内嵌 Python 装配异常，回退系统 PATH: {exc}", file=sys.stderr, flush=True)
        return None


def _session_id_from_cwd(virtual_cwd: str) -> str:
    """``/workspace/{sid}`` → sid；不合法（含 ``..``、缺前缀等）回落 ``unknown``。"""
    prefix = "/workspace/"
    sid = virtual_cwd[len(prefix) :] if virtual_cwd.startswith(prefix) else ""
    if sid and "/" not in sid and sid not in (".", ".."):
        return sid
    return "unknown"


def _sanitize_env(payload: dict) -> dict[str, str] | None:
    """载荷 env 净化：仅保留 str→str 条目；空/非法返回 None（继承语义）。"""
    raw = payload.get("env")
    if not isinstance(raw, dict) or not raw:
        return None
    return {str(k): v for k, v in raw.items() if isinstance(v, str)}


def _execute(
    executor: Executor,
    command: str,
    virtual_cwd: str,
    timeout: float,
    env_extra: dict[str, str] | None = None,
) -> dict:
    """执行并保证返回 done 契约 dict：executor 异常（如非法 cwd 的 ExecutorError）
    收敛为 ``status=error`` 的结果而非断连。"""
    effective = timeout if timeout > 0 else DEFAULT_EXEC_TIMEOUT_S
    try:
        return executor.execute(command, virtual_cwd, effective, env_extra)
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

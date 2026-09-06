"""LocalSandboxBackend 测试：execute 往返、离线透传、id、upload/download 经中继执行。

ExecuteResponse 真实字段为 output/exit_code/truncated（protocol.py:810），
无 stdout/stderr 字段——stdout/stderr 在 aexecute 内合并进 output。

M4 T3 追加：文件命令生成的平台分支——posix 命令串逐字节锁定（Linux 零
回归）、win32 上报后无 POSIX 语法（无 mkdir -p、cmd 双引号引用、单行脚本）、
服务端 _cmd_quote 与 client platform.shell_quote 同组 torture 用例互锁。
"""

import base64
import shlex
import subprocess
from pathlib import Path

import pytest

from src.infra.backend import _local_transfer as transfer_module
from src.infra.backend import local as local_module
from src.infra.backend.local import LocalSandboxBackend
from src.kernel.errors import AppError, ErrorCode


@pytest.fixture(autouse=True)
def _default_daemon_platform(monkeypatch):
    """既有用例默认「无平台信息」（空串 → posix 现状），平台查询不触真实 redis。

    返回 state dict，win32 用例把它翻成 "win32" 即可让同一次 upload/download
    全链按 Windows 分支生成命令。
    """
    state = {"platform": ""}

    async def fake_lookup(user_id, machine_id=None):
        return state["platform"]

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", fake_lookup)
    return state


@pytest.fixture(autouse=True)
def _bridge_transfer_module(monkeypatch):
    """把 _local_transfer 模块（fs 传输通道）的 dispatch/上限代理到 local 模块当前绑定。

    通道拆分到 _local_transfer 后，测试沿用「patch local_module.dispatch_local_call」
    的既有写法即可同时接管 exec 与 fs 两条链路；_download_max_bytes 同理。
    """
    from src.infra.backend import _local_transfer as transfer_module

    async def _bridged_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return await local_module.dispatch_local_call(
            user_id, op, payload, timeout=timeout, machine_id=machine_id
        )

    def _bridged_max_bytes():
        return local_module._download_max_bytes()

    monkeypatch.setattr(transfer_module, "dispatch_local_call", _bridged_dispatch)
    monkeypatch.setattr(transfer_module, "_download_max_bytes", _bridged_max_bytes)
    return transfer_module


def _ok_response(stdout: str = "", stderr: str = "", exit_code: int = 0) -> dict:
    return {"status": "ok", "stdout": stdout, "stderr": stderr, "exit_code": exit_code}


def _real_exec_dispatch(cwd: Path):
    """fake dispatch：像真 daemon 一样在映射后的工作区目录（cwd）真实执行命令。

    返回 dict 带 stdout/stderr/exit_code 独立字段——与 daemon executor 契约一致。
    """

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        proc = subprocess.run(payload["command"], shell=True, cwd=cwd, capture_output=True)
        return {
            "status": "ok",
            "stdout": proc.stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
        }

    return fake_dispatch


def _daemon_dispatch(tmp_path: Path):
    """daemon 全仿真 dispatch：exec 落真实 shell（cwd=工作区），fs_* 走真实 fsops。

    工作区 = data_root/s1（与 daemon 的 map_workspace 一致），exec 的 cwd 取
    同一目录——两类 op 看到同一份文件树，可混用互证（F3 传输通道端到端用）。
    """
    from lambchat_sandbox import fsops

    ws = tmp_path / "s1"
    ws.mkdir(exist_ok=True)
    real_exec = _real_exec_dispatch(ws)

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        if op in ("fs_upload", "fs_download"):
            result = fsops.handle_fs_op(op, payload, tmp_path)
            return {"stage": "done", "status": "ok", "result": result}
        return await real_exec(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    return fake_dispatch


async def test_aexecute_maps_result(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        assert (user_id, op) == ("u1", "exec")
        assert payload["command"] == "echo hi"
        return _ok_response(stdout="hi", exit_code=0)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("echo hi")
    assert resp.output == "hi"
    assert resp.exit_code == 0
    assert resp.truncated is False


async def test_aexecute_appends_stderr_to_output(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        if payload["command"] == "both":
            return _ok_response(stdout="out", stderr="err")
        return _ok_response(stderr="only-err")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert (await backend.aexecute("both")).output == "out\nerr"
    assert (await backend.aexecute("fail-only")).output == "only-err"


async def test_aexecute_passes_cwd_and_timeout(monkeypatch):
    captured = {}

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.update(op=op, payload=payload, timeout=timeout)
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1", exec_timeout=7)
    await backend.aexecute("ls")
    assert captured["op"] == "exec"
    assert captured["payload"] == {"command": "ls", "cwd": "/workspace/s1"}
    assert captured["timeout"] == 7.0


async def test_offline_propagates(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    with pytest.raises(AppError) as exc:
        await backend.aexecute("ls")
    assert exc.value.error_code == ErrorCode.DAEMON_OFFLINE


def test_id_contains_session():
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert backend.id == "local-s1"


def test_execute_bridges_sync(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return _ok_response(stdout="sync-hi")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = backend.execute("echo sync-hi")
    assert resp.output == "sync-hi"
    assert resp.exit_code == 0


def test_download_files_decodes_base64(monkeypatch, tmp_path):
    content = b"file-body"
    (tmp_path / "a.txt").write_bytes(content)

    monkeypatch.setattr(local_module, "dispatch_local_call", _truncating_exec_dispatch(tmp_path))
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files([str(tmp_path / "a.txt")])
    assert len(responses) == 1
    assert responses[0].error is None
    assert responses[0].content == content


def test_download_files_stderr_does_not_pollute_base64(monkeypatch, tmp_path):
    """download 解码只取 stdout 字段：stderr 非空（如 shell 告警）不得混进 base64。

    旧实现经 aexecute 把 stdout+stderr 合并进 output 再解码，stderr 文本里
    的字母会被 base64 解码器吞掉，产出损坏字节。
    """
    content = b"file-body-1"
    (tmp_path / "a.txt").write_bytes(content)
    noisy = "grep: warning: something noisy on stderr"

    real_dispatch = _truncating_exec_dispatch(tmp_path)

    async def noisy_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        result = await real_dispatch(user_id, op, payload, timeout=timeout, machine_id=machine_id)
        result["stderr"] = noisy
        return result

    monkeypatch.setattr(local_module, "dispatch_local_call", noisy_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files([str(tmp_path / "a.txt")])
    assert responses[0].error is None
    assert responses[0].content == content


async def test_adownload_files_stderr_does_not_pollute_base64(monkeypatch, tmp_path):
    # 内容长度取 3 的倍数：b64 无 padding，旧实现的合并解码无法借 padding 截断蒙混过关
    content = b"async-body-1"
    (tmp_path / "a.bin").write_bytes(content)
    noisy = "[PID 123] some daemon chatter"

    real_dispatch = _truncating_exec_dispatch(tmp_path)

    async def noisy_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        result = await real_dispatch(user_id, op, payload, timeout=timeout, machine_id=machine_id)
        result["stderr"] = noisy
        return result

    monkeypatch.setattr(local_module, "dispatch_local_call", noisy_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files([str(tmp_path / "a.bin")])
    assert responses[0].error is None
    assert responses[0].content == content


def test_download_files_maps_missing_to_error(monkeypatch, tmp_path):
    """缺文件：stat 探测即失败，python 的 ENOENT 走原分类。"""
    missing = tmp_path / "missing.txt"

    monkeypatch.setattr(local_module, "dispatch_local_call", _truncating_exec_dispatch(tmp_path))
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files([str(missing)])
    # ENOENT 文本含 "directory" 子串，不能被误分类为 is_directory
    assert responses[0].error == "file_not_found"
    assert responses[0].content is None


def test_download_files_maps_is_directory_error(monkeypatch, tmp_path):
    """目录：Linux 上 stat(getsize) 对目录成功，分片 open 才抛 EISDIR。"""
    monkeypatch.setattr(local_module, "dispatch_local_call", _truncating_exec_dispatch(tmp_path))
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files([str(tmp_path)])
    assert responses[0].error == "is_directory"


def test_classify_file_error_real_daemon_strings():
    classify = local_module._classify_file_error
    assert classify("[Errno 2] No such file or directory: '/workspace/x'") == "file_not_found"
    assert classify("/bin/sh: cat: /workspace/x: No such file or directory") == "file_not_found"
    assert classify("[Errno 21] Is a directory: '/workspace/x'") == "is_directory"
    assert classify("[Errno 13] Permission denied: '/root/x'") == "permission_denied"
    assert classify("mkdir: cannot create directory '/x': Permission denied") == "permission_denied"


def test_classify_file_error_unknown_text_is_io_error_not_file_not_found():
    """识别不了的错误文本不得兜底成 file_not_found——那是 2026-09-06 生产事故的
    误导链（win32 命令超长失败被标"文件不存在"，agent/用户全被带偏）。"""
    classify = local_module._classify_file_error
    assert classify("some unexpected failure") == "io_error"
    assert classify("The filename or extension is too long") == "io_error"
    assert classify("") == "io_error"


async def test_aexecute_returns_failed_command_output(monkeypatch):
    """非零退出码的命令结果必须回到模型（output 含 stderr、exit_code 透传）——
    不能在中继层被劫持成 AppError（Windows 实测：模型看不到 'free' is not
    recognized，无从换成正确命令）。"""

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return {
            "status": "error",
            "stdout": "",
            "stderr": "'free' is not recognized as an internal or external command",
            "exit_code": 1,
            "error": None,
        }

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("free -h")
    assert resp.exit_code == 1
    assert "not recognized" in resp.output


async def test_aexecute_appends_executor_error_marker(monkeypatch):
    """executor 超时结果（error="timeout"，exit_code=None）：error 字段并入
    output 作显式标记，模型能区分「命令超时」与「命令失败」。"""

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return {
            "status": "error",
            "stdout": "partial",
            "stderr": "",
            "exit_code": None,
            "error": "timeout",
        }

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("sleep 999")
    assert resp.exit_code is None
    assert "partial" in resp.output
    assert "timeout" in resp.output


async def test_aexecute_missing_exit_code_is_undetermined(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return {"status": "ok", "stdout": "partial"}

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("cmd")
    # 缺失 exit_code 透传 None（协议：None = 未确定），不得伪装成 0 成功
    assert resp.output == "partial"
    assert resp.exit_code is None


def test_upload_files_writes_via_exec(monkeypatch):
    captured = {}

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.update(op=op, payload=payload)
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.upload_files([("/workspace/s1/note.txt", b"hello")])
    assert len(responses) == 1
    assert responses[0].error is None
    assert captured["op"] == "exec"
    command = captured["payload"]["command"]
    # 内容以 base64 编码进单条命令，路径带引号防注入
    assert base64.b64encode(b"hello").decode() in command
    assert "/workspace/s1/note.txt" in command


async def test_upload_files_offline_propagates(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        raise AppError(ErrorCode.SANDBOX_TIMEOUT)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    with pytest.raises(AppError) as exc:
        await backend.aupload_files([("/workspace/s1/a.txt", b"x")])
    assert exc.value.error_code == ErrorCode.SANDBOX_TIMEOUT


# =========================================================================
# F1: 虚拟别名路径剥离（/workspace/{sid}/x → 相对路径 x，经已映射 cwd 落位）
# =========================================================================


async def test_alias_aread_via_virtual_path(monkeypatch, tmp_path):
    """端到端验收：daemon 侧工作目录已有 note.txt → aread('/workspace/s1/note.txt') 读回内容。"""
    (tmp_path / "note.txt").write_text("alias-read-body", encoding="utf-8")
    monkeypatch.setattr(local_module, "dispatch_local_call", _real_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aread("/workspace/s1/note.txt")
    assert result.error is None
    assert "alias-read-body" in str(result.file_data["content"])


async def test_alias_als_lists_entries_with_prefixed_paths(monkeypatch, tmp_path):
    """端到端验收：als('/workspace/s1') 列出条目，路径补回虚拟别名前缀。"""
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    monkeypatch.setattr(local_module, "dispatch_local_call", _real_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.als("/workspace/s1")
    assert result.error is None
    paths = {entry["path"] for entry in (result.entries or [])}
    assert paths == {"/workspace/s1/note.txt", "/workspace/s1/subdir"}


async def test_alias_awrite_via_virtual_path_lands_in_workspace(monkeypatch, tmp_path):
    """awrite 经 upload_files（BaseSandbox 委托）走 fs_upload 落到会话工作区。

    deepagents 的 write/edit 都委托 upload_files 传输内容——新结构化通道
    自动让 write/edit 也摆脱 exec 命令行限制（daemon 仿真 dispatch 验证
    exec 与 fs 两类 op 落同一份文件树）。
    """
    monkeypatch.setattr(local_module, "dispatch_local_call", _daemon_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite("/workspace/s1/new.txt", "written-via-alias")
    assert result.error is None
    assert result.path == "/workspace/s1/new.txt"
    assert (tmp_path / "s1" / "new.txt").read_text(encoding="utf-8") == "written-via-alias"


async def test_alias_execute_rewrites_command_alias_with_boundary(monkeypatch):
    """shell 命令串里的 /workspace/s1 → .（cd /workspace/s1 && … 可用），且不误伤 s12。"""
    captured: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    await backend.aexecute("cat /workspace/s1/note.txt")
    await backend.aexecute("cd /workspace/s1 && ls")
    await backend.aexecute("cat /workspace/s12/other.txt")
    assert captured[0] == "cat ./note.txt"
    assert captured[1] == "cd . && ls"
    assert captured[2] == "cat /workspace/s12/other.txt"  # 边界：更长 sid 不改写


async def test_alias_execute_rewrites_shared_alias_with_boundary(monkeypatch):
    """命令串里的 /workspace/.shared → ../.shared（相对已映射 cwd 可达），不误伤 .shared-x。"""
    captured: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    await backend.aexecute("python3 /workspace/.shared/skills/demo/run.py")
    await backend.aexecute("cat /workspace/.shared-x/other.txt")
    assert captured[0] == "python3 ../.shared/skills/demo/run.py"
    assert captured[1] == "cat /workspace/.shared-x/other.txt"


async def test_alias_aread_passthrough_for_outside_absolute_path(monkeypatch, tmp_path):
    """别名之外的绝对路径（如 /etc/hostname）不改写——冒烟用例 4 的既有语义。"""
    captured: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(payload["cwd"])
        return _ok_response(stdout="{}")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    await backend.aread("/etc/hostname")
    assert captured == ["/workspace/s1"]  # cwd 契约不变，仍是虚拟别名


# =========================================================================
# F2: 传输上限与误报（分块上传 / 下载 size 预检 / 错误分类）
# =========================================================================


async def test_aupload_files_large_content_chunked_end_to_end(monkeypatch, tmp_path):
    """端到端验收（legacy exec 链路）：>128KB 内容上传成功——分块多条命令写入，落盘内容逐字节一致。

    旧实现把整个 base64 塞单个 argv，超过内核 MAX_ARG_STRLEN（单参数 128KB，
    扣除引号/命令开销 ~96KB 即断）触发 E2BIG，且被误分类为 file_not_found。
    新结构化通道（F3）分流常规上传后，本用例钉住 exec 兜底路径的分块行为。
    """
    content = bytes(range(256)) * 1024  # 256KB 确定性内容
    commands: list[str] = []
    real = _real_exec_dispatch(tmp_path)

    async def tracking_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return await real(user_id, op, payload, timeout=timeout)

    monkeypatch.setattr(local_module, "dispatch_local_call", tracking_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    backend._fs_transfer_supported = False  # 钉住 legacy exec 分块（新通道另测）
    responses = await backend.aupload_files([("/workspace/s1/big.bin", content)])

    assert responses[0].error is None
    assert (tmp_path / "big.bin").read_bytes() == content
    assert len(commands) > 1  # 分块：多条命令而非单个巨型 argv
    assert all(len(cmd) < 100_000 for cmd in commands)  # 单命令远离 MAX_ARG_STRLEN


def test_upload_chunk_commands_split_bounds():
    """分块边界：超 48KB 起分片——首块 wb 截断创建（含 mkdir），后续块 ab 追加。"""
    content = b"x" * (48 * 1024 + 1)
    cmds = LocalSandboxBackend._upload_chunk_commands("sub/dir/f.bin", content)
    assert len(cmds) == 2
    assert "mkdir -p" in cmds[0] and "'wb'" in cmds[0]
    assert "mkdir -p" not in cmds[1] and "'ab'" in cmds[1]
    assert all(len(c) < 100_000 for c in cmds)


def test_upload_chunk_commands_single_command_at_or_below_threshold():
    """≤48KB 保持单命令直写（不额外拆分）。"""
    assert len(LocalSandboxBackend._upload_chunk_commands("f", b"x" * (48 * 1024))) == 1
    assert len(LocalSandboxBackend._upload_chunk_commands("f", b"tiny")) == 1


def test_upload_chunk_commands_win32_sized_for_cmd_exe_limit():
    """win32 旧链路兜底分块：单条命令全文 < 8191（cmd.exe 命令行上限）。

    48KB 分块只防 Linux MAX_ARG_STRLEN（128KB）；win32 上 >~6KB 文件的 b64
    单命令即超 cmd.exe 上限必败（2026-09-06 生产事故根因——新结构化通道
    分流常规上传后，本用例钉住 exec 降级路径的 win32 安全分块）。
    """
    content = b"x" * (6 * 1024 + 100)  # ~6.1KB：旧 win32 单命令必超限的量级
    cmds = LocalSandboxBackend._upload_chunk_commands("dir/f.bin", content, platform="win32")
    assert len(cmds) > 1
    assert all(len(cmd) < 8191 for cmd in cmds)
    # posix 不受影响：同内容单命令
    assert len(LocalSandboxBackend._upload_chunk_commands("dir/f.bin", content)) == 1


async def test_adownload_files_oversized_explicit_error(monkeypatch, tmp_path):
    """端到端验收：超过统一上限的文件得显式 file_too_large（带字节数与
    S3_INTERNAL_UPLOAD_MAX_SIZE 来源），而非 base64 半途炸或误报。"""
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1/big.bin").write_bytes(b"0" * 200)
    monkeypatch.setattr(local_module, "_download_max_bytes", lambda: 100)
    monkeypatch.setattr(local_module, "dispatch_local_call", _daemon_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/big.bin"])
    assert responses[0].error is not None
    assert responses[0].error.startswith("file_too_large: 200 bytes exceeds 100 limit")
    assert responses[0].content is None


async def test_adownload_files_within_limit_roundtrips(monkeypatch, tmp_path):
    """限内文件正常回读：内容逐字节一致（含二进制字节）。"""
    payload = b"roundtrip-body-\x00\x01" * 64
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1/ok.bin").write_bytes(payload)
    monkeypatch.setattr(local_module, "dispatch_local_call", _daemon_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/ok.bin"])
    assert responses[0].error is None
    assert responses[0].content == payload


def test_classify_maps_too_large_and_e2big():
    """Errno 7（E2BIG）与显式超限文本 → file_too_large，不得回落 file_not_found。"""
    classify = local_module._classify_file_error
    assert classify("[Errno 7] Argument list too long") == "file_too_large"
    assert classify("file_too_large: 3145728 bytes exceeds 2097152 limit") == "file_too_large"
    assert classify("OSError: [Errno 27] File too large") == "file_too_large"


async def test_adownload_decode_failure_carries_original_output(monkeypatch):
    """b64decode 异常不得标成 file_not_found：错误带原始 stdout 片段供排查。"""
    garbage = "not!!valid!!b64!!"

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return _ok_response(stdout=garbage)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/a.txt"])
    assert responses[0].error != "file_not_found"
    assert garbage in str(responses[0].error)
    assert responses[0].content is None


# =========================================================================
# F3: 结构化传输通道（fs_upload/fs_download，老 daemon 自动降级 exec）
# =========================================================================


async def test_aupload_via_fs_upload_skips_exec_commands(monkeypatch, tmp_path):
    """端到端：常规大小文件上传走 fs_upload 结构化 op，不再生成 exec 命令。

    旧链路把整个文件 base64 成单条命令——win32 cmd.exe 命令行 8191 字符上限
    下 >~6KB 文件必败（2026-09-06 生产事故：SKILL.md/interact.py 报
    file_not_found，实际是上传命令超长失败被误分类）。
    """
    content = ("技能文件内容中文示意\n" * 300).encode("utf-8")  # ~6.4KB，事故同量级
    ops: list[tuple[str, dict]] = []
    daemon = _daemon_dispatch(tmp_path)

    async def tracking(user_id, op, payload, *, timeout=None, machine_id=None):
        ops.append((op, dict(payload)))
        return await daemon(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    monkeypatch.setattr(local_module, "dispatch_local_call", tracking)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.aupload_files([("/workspace/s1/browser/SKILL.md", content)])

    assert responses[0].error is None
    assert responses[0].path == "/workspace/s1/browser/SKILL.md"
    assert [op for op, _ in ops] == ["fs_upload"]  # 单 op，零 exec 命令
    payload = ops[0][1]
    assert payload["path"] == "browser/SKILL.md"
    assert payload["truncate"] is True
    assert payload["offset"] == 0
    assert base64.b64decode(payload["content_b64"]) == content
    assert (tmp_path / "s1/browser/SKILL.md").read_bytes() == content


async def test_aupload_via_fs_upload_chunks_by_offset(monkeypatch, tmp_path):
    """大文件分块：按 offset 定位多 op 传输，首块 truncate 创建，后续块定位写。"""
    monkeypatch.setattr(transfer_module, "FS_TRANSFER_CHUNK_BYTES", 1024)
    content = bytes(range(256)) * 10  # 2560B → 3 块（1KiB+1KiB+512B）
    calls: list[dict] = []
    daemon = _daemon_dispatch(tmp_path)

    async def tracking(user_id, op, payload, *, timeout=None, machine_id=None):
        calls.append(dict(payload))
        return await daemon(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    monkeypatch.setattr(local_module, "dispatch_local_call", tracking)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.aupload_files([("/workspace/s1/big.bin", content)])

    assert responses[0].error is None
    assert [(c["offset"], c["truncate"]) for c in calls] == [
        (0, True),
        (1024, False),
        (2048, False),
    ]
    assert (tmp_path / "s1/big.bin").read_bytes() == content


async def test_aupload_falls_back_to_exec_on_unsupported_op(monkeypatch, tmp_path):
    """老 daemon（不认识 fs_upload）→ 降级 exec 旧链路成功，且能力位粘滞不再探测。"""
    daemon = _daemon_dispatch(tmp_path)
    fs_attempts: list[str] = []

    async def dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        if op == "fs_upload":
            fs_attempts.append(op)
            raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": f"unsupported op: {op}"})
        return await daemon(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    first = await backend.aupload_files([("/workspace/s1/legacy.txt", b"via-exec")])
    assert first[0].error is None
    assert (tmp_path / "s1/legacy.txt").read_bytes() == b"via-exec"

    second = await backend.aupload_files([("/workspace/s1/legacy2.txt", b"again")])
    assert second[0].error is None
    assert fs_attempts == ["fs_upload"]  # 第二批直接 exec，不再逐批探测


async def test_aupload_absolute_path_outside_workspace_uses_exec(monkeypatch):
    """别名外绝对路径（fs op 锁死工作区）仍走 exec 旧链路，保住既有语义。"""
    seen: list[str] = []

    async def dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        seen.append(op)
        assert op == "exec", "绝对路径不应走 fs op"
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.aupload_files([("/etc/abs-check.txt", b"x")])
    assert responses[0].error is None
    assert seen == ["exec"]


async def test_aupload_shared_dir_rebases_to_shared_cwd(monkeypatch):
    """.shared 别名：fs op 的 cwd 重定位到 /workspace/.shared，路径剥成纯相对。"""
    captured: list[tuple[str, str, str]] = []

    async def dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append((op, str(payload.get("cwd")), str(payload.get("path"))))
        return {"stage": "done", "status": "ok", "result": {"written": 9}}

    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.aupload_files(
        [("/workspace/.shared/skills/demo/run.py", b"print(1)\n")]
    )
    assert responses[0].error is None
    assert captured == [("fs_upload", local_module.PUBLIC_SHARED_DIR, "skills/demo/run.py")]


async def test_aupload_file_level_error_passthrough(monkeypatch):
    """daemon 结果级错误原样透传（不降级 exec——权限/路径问题 exec 同样会失败）。"""

    async def dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        return {"stage": "done", "status": "ok", "result": {"error": "permission_denied"}}

    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.aupload_files([("/workspace/s1/locked.txt", b"x")])
    assert responses[0].error == "permission_denied"


async def test_adownload_via_fs_download_until_eof(monkeypatch, tmp_path):
    """下载走 fs_download 分片循环到 eof：内容逐字节一致，路径回填别名。"""
    monkeypatch.setattr(transfer_module, "FS_TRANSFER_CHUNK_BYTES", 1024)
    content = bytes(range(256)) * 10
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1/blob.bin").write_bytes(content)
    daemon = _daemon_dispatch(tmp_path)
    calls: list[dict] = []

    async def tracking(user_id, op, payload, *, timeout=None, machine_id=None):
        if op == "fs_download":
            calls.append(dict(payload))
        return await daemon(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    monkeypatch.setattr(local_module, "dispatch_local_call", tracking)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/blob.bin"])
    assert responses[0].error is None
    assert responses[0].content == content
    assert responses[0].path == "/workspace/s1/blob.bin"
    assert [c["offset"] for c in calls] == [0, 1024, 2048]


async def test_adownload_falls_back_to_exec_on_unsupported_op(monkeypatch, tmp_path):
    """老 daemon：fs_download 不支持 → exec 旧链路回读成功。"""
    content = b"legacy-download"
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1/f.txt").write_bytes(content)
    daemon = _daemon_dispatch(tmp_path)

    async def dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        if op == "fs_download":
            raise AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": f"unsupported op: {op}"})
        return await daemon(user_id, op, payload, timeout=timeout, machine_id=machine_id)

    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/f.txt"])
    assert responses[0].error is None
    assert responses[0].content == content


# =========================================================================
# M4 T3: 文件命令生成平台分支
# - posix（含无平台信息）：命令串逐字节锁定——Linux daemon 全链零变化
# - win32：无 mkdir -p（makedirs 并进脚本）、cmd 双引号引用、单行无 %
# - 服务端 _cmd_quote 与 client platform.shell_quote 同组 torture 互锁
# =========================================================================


def test_upload_command_posix_bytes_locked():
    """Linux daemon 零回归锁：posix 命令串逐字节快照（mkdir -p + shlex + python3）。"""
    assert LocalSandboxBackend._upload_command("sub/dir/f.bin", b"hello") == (
        'mkdir -p sub/dir && python3 -c "import base64, sys; '
        "open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))\" "
        "sub/dir/f.bin aGVsbG8="
    )
    # 含空格路径：shlex 单引号包裹（posix 引用形态）；b64 含 = 属 shlex 安全字符，不引用
    assert LocalSandboxBackend._upload_command("my dir/a b.txt", b"x") == (
        "mkdir -p 'my dir' && python3 -c \"import base64, sys; "
        "open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))\" "
        "'my dir/a b.txt' eA=="
    )


def test_upload_command_posix_append_bytes_locked():
    """追加块：无 mkdir 前缀（父目录必已存在），模式 'ab'。"""
    assert LocalSandboxBackend._upload_command("sub/dir/f.bin", b"x", append=True) == (
        'python3 -c "import base64, sys; '
        "open(sys.argv[1], 'ab').write(base64.b64decode(sys.argv[2]))\" "
        "sub/dir/f.bin eA=="
    )


def test_download_size_command_posix_bytes_locked():
    """Linux daemon 零回归锁：posix stat 探测命令逐字节快照（单行脚本）。"""
    assert LocalSandboxBackend._download_size_command("a b.txt") == (
        'python3 -c "import os, sys; '
        'sys.stdout.write(str(os.path.getsize(sys.argv[1])))" '
        "'a b.txt'"
    )


def test_download_slice_command_posix_bytes_locked():
    """posix 分片命令逐字节快照：seek 偏移与读取长度为字面数字插值。"""
    assert LocalSandboxBackend._download_slice_command("a b.txt", offset=147456, length=147456) == (
        'python3 -c "import sys, base64; '
        "f = open(sys.argv[1], 'rb'); f.seek(147456); "
        'sys.stdout.buffer.write(base64.b64encode(f.read(147456)))" '
        "'a b.txt'"
    )


def test_platform_ctx_only_win32_branches_windows():
    """平台归一：win32/windows 之外（含空=未上报、linux/darwin、未知串）一律 posix。"""
    assert local_module._platform_ctx("win32").is_windows is True
    assert local_module._platform_ctx("windows").is_windows is True
    for plat in ("", "linux", "darwin", "unknown-xyz"):
        assert local_module._platform_ctx(plat).is_windows is False


def test_platform_ctx_posix_quote_matches_shlex():
    ctx = local_module._platform_ctx("linux")
    for s in ["a b", 'he said "hi"', "trailing\\", "$HOME", "a;b", ""]:
        assert ctx.quote(s) == shlex.quote(s)


def test_upload_command_windows_omits_mkdir_and_cmd_quotes():
    """win32 首块：无 mkdir -p 前缀（makedirs 并进脚本）、参数为 cmd 双引号引用。"""
    cmd = LocalSandboxBackend._upload_command("sub/dir/f.bin", b"hello", platform="win32")
    assert cmd == (
        'python3 -c "import base64, os, sys; '
        "d = os.path.dirname(sys.argv[1]); "
        "os.makedirs(d, exist_ok=True) if d else None; "
        "open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))\" "
        '"sub/dir/f.bin" "aGVsbG8="'
    )
    assert "mkdir -p" not in cmd
    assert "\n" not in cmd  # cmd.exe 逐行解析：脚本必须单行


def test_upload_command_windows_append_skips_makedirs():
    """win32 追加块：与 posix 对仗——父目录必已存在，脚本不含 makedirs 子句。"""
    cmd = LocalSandboxBackend._upload_command("f.bin", b"x", append=True, platform="win32")
    assert cmd == (
        'python3 -c "import base64, sys; '
        "open(sys.argv[1], 'ab').write(base64.b64decode(sys.argv[2]))\" "
        '"f.bin" "eA=="'
    )


def test_download_commands_windows_single_line_no_percent():
    """win32 下载探测/分片：单行脚本、无 % （cmd 双引号内 %VAR% 会被展开）。"""
    size_cmd = LocalSandboxBackend._download_size_command("a b.txt", platform="win32")
    slice_cmd = LocalSandboxBackend._download_slice_command(
        "a b.txt", offset=147456, length=147456, platform="win32"
    )
    assert size_cmd == (
        'python3 -c "import os, sys; sys.stdout.write(str(os.path.getsize(sys.argv[1])))" "a b.txt"'
    )
    assert slice_cmd == (
        'python3 -c "import sys, base64; '
        "f = open(sys.argv[1], 'rb'); f.seek(147456); "
        'sys.stdout.buffer.write(base64.b64encode(f.read(147456)))" '
        '"a b.txt"'
    )
    for cmd in (size_cmd, slice_cmd):
        assert "\n" not in cmd
        assert "%" not in cmd
        assert "/dev/null" not in cmd


def test_upload_files_windows_via_registry_platform(monkeypatch, _default_daemon_platform):
    """fake 注册表平台=win32 → 全链生成 Windows 命令：无 mkdir -p、cmd 引用。"""
    _default_daemon_platform["platform"] = "win32"
    commands: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.upload_files([("/workspace/s1/dir/note.txt", b"hello")])
    assert responses[0].error is None
    assert len(commands) == 1
    assert "mkdir -p" not in commands[0]
    assert "os.makedirs" in commands[0]
    assert '"/workspace/s1/dir/note.txt"' in commands[0]  # cmd 双引号引用（完整路径）


async def test_aupload_files_windows_chunked_commands(monkeypatch, _default_daemon_platform):
    """win32 分块上传（legacy exec 链路）：首块带 makedirs、后续块无（对仗 posix 分块语义）。

    win32 阈值 3KB（cmd.exe 命令行上限），见 _UPLOAD_CHUNK_WIN32_RAW_BYTES。
    """
    _default_daemon_platform["platform"] = "win32"
    commands: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    content = b"x" * (local_module._UPLOAD_CHUNK_WIN32_RAW_BYTES + 1)
    responses = await backend.aupload_files([("/workspace/s1/big.bin", content)])
    assert responses[0].error is None
    assert len(commands) == 2
    assert "os.makedirs" in commands[0] and "'wb'" in commands[0]
    assert "os.makedirs" not in commands[1] and "'ab'" in commands[1]
    assert all(len(c) < 8191 for c in commands)


async def test_adownload_files_windows_command_shape(monkeypatch, _default_daemon_platform):
    """win32 下载全链：stat 探测与分片命令都是单行 cmd 形态、路径 cmd 引用。"""
    _default_daemon_platform["platform"] = "win32"
    captured: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(payload["command"])
        if "getsize" in payload["command"]:
            return _ok_response(stdout="4")
        return _ok_response(stdout=base64.b64encode(b"body").decode())

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/a b.txt"])
    assert responses[0].error is None
    assert len(captured) == 2  # stat + 单片
    for command in captured:
        assert command.endswith('"/workspace/s1/a b.txt"')  # cmd 引用含空格路径
        assert "\n" not in command


def test_platform_hint_overrides_registry(monkeypatch):
    """显式 platform_hint 优先于注册表查询（构造期已知平台的 wiring/测试用）。"""
    commands: list[str] = []

    async def failing_lookup(user_id):
        raise AssertionError("hint 在场时不应查注册表")

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", failing_lookup)
    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1", platform_hint="win32")
    backend.upload_files([("/workspace/s1/a.txt", b"x")])
    assert "mkdir -p" not in commands[0]


async def test_lookup_daemon_platform_defaults_posix_on_error(monkeypatch):
    """注册表查询失败（redis 不可达等）容错回落空串 → posix（现状零变化）。"""

    class _BrokenRegistry:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("redis down")

    monkeypatch.setattr(local_module, "SandboxClientRegistry", _BrokenRegistry)
    assert await local_module._lookup_daemon_platform("u1") == ""


def test_upload_files_default_platform_keeps_posix_commands(monkeypatch):
    """无平台信息（旧格式 value/查询失败）→ 命令串与现状逐字节一致。"""
    commands: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    backend.upload_files([("/workspace/s1/dir/note.txt", b"hello")])
    assert commands[0] == (
        'mkdir -p /workspace/s1/dir && python3 -c "import base64, sys; '
        "open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))\" "
        "/workspace/s1/dir/note.txt aGVsbG8="
    )


# ---------- % 拒绝策略：cmd.exe 双引号内 %VAR% 展开无法可靠转义 ----------


def test_cmd_quote_rejects_percent_arguments():
    """含 % 的参数拒绝（ValueError）——命令行上下文（非 batch）没有可靠的
    % 转义（%% 仅 batch 生效），引用静默放行等于任由 cmd 展开改写路径。"""
    with pytest.raises(ValueError, match="%"):
        local_module._cmd_quote("a%PATH%b")
    with pytest.raises(ValueError, match="%"):
        local_module._cmd_quote("50%off.txt")


def test_upload_windows_percent_path_maps_to_error(monkeypatch):
    """win32 上传含 % 路径：ValueError 落进 _upload_one 既有兜底 → invalid_path，
    不崩链路也不下发会被 cmd 改写的命令。"""
    commands: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1", platform_hint="win32")
    responses = backend.upload_files([("dir/50%off.txt", b"x")])
    assert responses[0].error == "invalid_path"
    assert commands == []  # 拒绝发生在命令生成期，未下发任何命令


# ---------- 双侧引用互锁：服务端 _cmd_quote vs client platform.shell_quote ----------

# 与 tests/client/test_platform.py 的 _WIN_TORTURE 同一组 torture 用例（不含 %，
# % 拒绝是服务端侧的有意差异，见 test_cmd_quote_rejects_percent_arguments）。
_INTERLOCK_TORTURE = [
    "a b",
    'he said "hi"',
    "trailing\\",
    'a\\"b\\\\',
    "",
    "plain",
    "a\\b",
    "\\",
    "\\\\",
    '"',
    '""',
    '\\"',
    "space at end ",
    "\ttab",
    'mix \\" tail\\\\',
    "C:\\Program Files\\LambChat\\daemon.exe",
]


def test_cmd_quote_interlocks_with_client_windows_quote():
    """同一组输入同输出：服务端生成命令的引用与 client 平台层逐字节一致。"""
    from lambchat_sandbox.platform import shell_quote as client_quote

    for s in _INTERLOCK_TORTURE:
        assert local_module._cmd_quote(s) == client_quote(s, platform="windows"), (
            f"server/client 引用规则漂移: {s!r}"
        )


def test_platform_ctx_posix_interlocks_with_client_posix_quote():
    from lambchat_sandbox.platform import shell_quote as client_quote

    for s in _INTERLOCK_TORTURE:
        assert local_module._platform_ctx("linux").quote(s) == client_quote(s, platform="posix")


# ---------- 继承的 read/ls 命令平台中立性（验收项：无 mkdir -p / 无 shell 引用参数） ----------


def test_inherited_read_commands_are_platform_neutral():
    """deepagents 继承的 read/ls 把路径 base64 进脚本、无 mkdir 前缀、无 shell
    引用参数位——命令形态与 daemon 平台无关（引用之争不存在于这两族命令）。"""
    from deepagents.backends.sandbox import _build_ls_cmd, _build_read_cmd

    for cmd in (_build_read_cmd('weird "path" b.txt', 0, 10), _build_ls_cmd("a b/c.txt")):
        assert "mkdir -p" not in cmd
    # 路径以 base64 进脚本，不作为 shell 参数出现（无 shlex/cmd 引用形态）
    assert base64.b64encode(b"a b/c.txt").decode() in _build_ls_cmd("a b/c.txt")


# =========================================================================
# M4 T3.5: win32 结构化文件操作（daemon 平台 win32 时 fs op 直达，posix 零变化）
# =========================================================================


def _fs_dispatch(result: dict):
    """fake dispatch：记录 (op, payload) 序列并回放 fs 结果体。"""

    calls: list[tuple[str, dict]] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        assert (user_id, op) == ("u1", op)
        calls.append((op, dict(payload)))
        return {"status": "ok", "result": result}

    fake_dispatch.calls = calls
    return fake_dispatch


async def test_win32_aread_dispatches_structured_fs_read(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch(
        {
            "encoding": "utf-8",
            "content": "l1\nl2",
            "total_lines": 2,
            "start_line": 1,
            "end_line": 2,
            "next_offset": 2,
        }
    )
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aread("/workspace/s1/note.txt", offset=0, limit=2)

    assert dispatch.calls == [
        ("fs_read", {"path": "note.txt", "offset": 0, "limit": 2, "cwd": "/workspace/s1"})
    ]
    assert result.error is None
    assert result.file_data is not None
    assert result.file_data["content"] == "l1\nl2"
    assert result.file_data["encoding"] == "utf-8"
    assert (result.total_lines, result.start_line, result.end_line, result.next_offset) == (
        2,
        1,
        2,
        2,
    )


async def test_win32_aread_error_message_matches_posix_format(
    monkeypatch, _default_daemon_platform
):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"error": "file_not_found"})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aread("/workspace/s1/ghost.txt")
    assert result.error == "File 'ghost.txt': file_not_found"  # 与 _parse_read_output 同构


def test_win32_sync_read_uses_fs_op(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"encoding": "utf-8", "content": "body", "no_lines_requested": False})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = backend.read("/workspace/s1/f.txt")
    assert result.error is None
    assert result.file_data is not None and result.file_data["content"] == "body"
    assert dispatch.calls[0][0] == "fs_read"


async def test_posix_read_still_exec_pos_commands(monkeypatch, _default_daemon_platform):
    """posix（无平台信息）走 super() 的 exec 命令路径——现状零变化。"""
    captured: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(op)
        captured.append(payload["command"])
        return _ok_response(stdout='{"encoding": "utf-8", "content": "posix"}')

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aread("/workspace/s1/note.txt")
    assert captured[0] == "exec"
    assert "python3" in captured[1]
    assert result.file_data is not None and result.file_data["content"] == "posix"


async def test_win32_als_restores_alias_prefix_on_entries(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch(
        {"entries": [{"path": "./note.txt", "is_dir": False}, {"path": "./subdir", "is_dir": True}]}
    )
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.als("/workspace/s1")
    assert dispatch.calls == [("fs_ls", {"path": ".", "cwd": "/workspace/s1"})]
    assert result.error is None
    assert {(e["path"], e["is_dir"]) for e in (result.entries or [])} == {
        ("/workspace/s1/note.txt", False),
        ("/workspace/s1/subdir", True),
    }


async def test_win32_als_error_uses_ls_error_format(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"error": "path_not_found"})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.als("/workspace/s1/ghost")
    assert result.entries is None
    assert result.error == "Path 'ghost': path_not_found"


async def test_win32_awrite_sends_b64_and_restores_path(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite("/workspace/s1/sub/new.txt", "内容 ✓")
    assert dispatch.calls == [
        (
            "fs_write",
            {
                "path": "sub/new.txt",
                "content_b64": base64.b64encode("内容 ✓".encode()).decode(),
                "cwd": "/workspace/s1",
            },
        )
    ]
    assert result.error is None
    assert result.path == "/workspace/s1/sub/new.txt"  # 成功回填原别名路径


async def test_win32_awrite_over_cap_rejects_before_dispatch(monkeypatch, _default_daemon_platform):
    """>2MB 内容单次 fs_write 拒绝（file_too_large，与 posix 侧 2MB 量级对齐）。"""
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite(
        "/workspace/s1/big.bin", "x" * (local_module._FS_WRITE_MAX_BYTES + 1)
    )
    assert dispatch.calls == []  # 未下发
    assert result.path is None
    assert "file_too_large" in (result.error or "")


async def test_win32_awrite_error_wrapped(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"error": "permission_denied"})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite("/workspace/s1/f.txt", "x")
    assert result.path is None
    assert result.error == "Failed to write file 'f.txt': permission_denied"


async def test_win32_aedit_sends_b64_and_maps_errors(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"count": 2})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aedit("/workspace/s1/f.txt", "old", "new", replace_all=True)
    assert dispatch.calls == [
        (
            "fs_edit",
            {
                "path": "f.txt",
                "old_str_b64": base64.b64encode(b"old").decode(),
                "new_str_b64": base64.b64encode(b"new").decode(),
                "replace_all": True,
                "cwd": "/workspace/s1",
            },
        )
    ]
    assert result.error is None
    assert result.path == "/workspace/s1/f.txt"
    assert result.occurrences == 2


async def test_win32_aedit_string_not_found_message_posix_parity(
    monkeypatch, _default_daemon_platform
):
    """错误码经 deepagents _map_edit_error——与 posix 路径同一条消息。"""
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"error": "string_not_found"})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aedit("/workspace/s1/f.txt", "needle", "x")
    assert result.error == "Error: String not found in file: 'needle'"
    assert result.path is None


async def test_win32_adelete_dispatch_and_not_found(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.adelete("/workspace/s1/f.txt")
    assert dispatch.calls == [("fs_delete", {"path": "f.txt", "cwd": "/workspace/s1"})]
    assert result.path == "/workspace/s1/f.txt"

    missing = _fs_dispatch({"error": "file_not_found"})
    monkeypatch.setattr(local_module, "dispatch_local_call", missing)
    result = await backend.adelete("/workspace/s1/ghost")
    assert result.error == "Error: 'ghost' not found"


async def test_win32_aglob_root_normalizes_and_restores(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch(
        {
            "matches": [{"path": "deep/a.py", "is_dir": False}],
            "truncated": False,
            "truncation_reason": None,
        }
    )
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aglob("*.py")  # path=None → 根搜索（fs 语义 = 工作区根）
    assert dispatch.calls == [("fs_glob", {"pattern": "*.py", "path": ".", "cwd": "/workspace/s1"})]
    assert result.error is None
    assert [m["path"] for m in (result.matches or [])] == ["/workspace/s1/deep/a.py"]


async def test_win32_aglob_subroot_joins_virtual_root(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"matches": [{"path": "a.txt", "is_dir": False}]})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aglob("*.txt", path="/workspace/s1/src")
    assert dispatch.calls[0][1]["path"] == "src"
    assert [m["path"] for m in (result.matches or [])] == ["/workspace/s1/src/a.txt"]


async def test_win32_agrep_payload_and_restore(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch(
        {"matches": [{"path": "./a.txt", "line": 2, "text": "beta"}], "truncated": False}
    )
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.agrep("beta", path="/workspace/s1", glob="*.txt", max_count=5)
    assert dispatch.calls == [
        (
            "fs_grep",
            {
                "pattern": "beta",
                "path": ".",
                "glob": "*.txt",
                "max_count": 5,
                "is_regex": False,
                "cwd": "/workspace/s1",
            },
        )
    ]
    assert result.error is None
    assert result.matches is not None and len(result.matches) == 1
    assert result.matches[0] == {"path": "/workspace/s1/a.txt", "line": 2, "text": "beta"}
    assert result.truncated is False


async def test_win32_agrep_truncated_and_error(monkeypatch, _default_daemon_platform):
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"matches": [], "truncated": True})
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.agrep("x", path=None)
    assert dispatch.calls[0][1]["path"] == "."
    assert result.truncated is True

    failing = _fs_dispatch({"error": "invalid_pattern"})
    monkeypatch.setattr(local_module, "dispatch_local_call", failing)
    result = await backend.agrep("", path=None)
    assert result.error == "Path '.': invalid_pattern"
    assert result.matches is None


async def test_platform_hint_win32_triggers_fs_without_registry(monkeypatch):
    """构造期显式 platform_hint=win32：不查注册表即走 fs 分支（wiring/测试通道）。"""
    dispatch = _fs_dispatch({"entries": []})

    async def boom_lookup(user_id):
        raise AssertionError("platform hint 不应触注册表")

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", boom_lookup)
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(
        user_id="u1", session_id="s1", platform_hint="win32"
    )

    result = await backend.als("/workspace/s1")
    assert dispatch.calls == [("fs_ls", {"path": ".", "cwd": "/workspace/s1"})]
    assert result.entries == []


async def test_platform_hint_posix_keeps_exec_commands(monkeypatch):
    dispatch = _fs_dispatch({})

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        dispatch.calls.append((op, dict(payload)))
        return _ok_response(stdout="{}")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(
        user_id="u1", session_id="s1", platform_hint="linux"
    )

    await backend.aread("/workspace/s1/f.txt")
    assert dispatch.calls[0][0] == "exec"


async def test_win32_fs_result_malformed_degrades_to_error(monkeypatch, _default_daemon_platform):
    """坏结果体（缺 content / 分页字段组合非法）降级为错误而非裸异常。"""
    _default_daemon_platform["platform"] = "win32"
    dispatch = _fs_dispatch({"total_lines": 5})  # 无 content 且分页字段缺窗
    monkeypatch.setattr(local_module, "dispatch_local_call", dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.aread("/workspace/s1/f.txt")
    assert result.error is not None
    assert "unexpected server response" in result.error


# ============================================================================
# env 变量注入（对齐云端沙箱：backend.env_vars → exec 载荷 env 字段）
# ============================================================================


async def test_aexecute_payload_carries_env_vars(monkeypatch):
    payloads = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        payloads.append(payload)
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(
        user_id="u1", session_id="s1", env_vars={"OPENAI_API_KEY": "sk-x"}
    )
    await backend.aexecute("echo hi")
    assert payloads[0]["env"] == {"OPENAI_API_KEY": "sk-x"}


async def test_aexecute_payload_omits_env_when_empty(monkeypatch):
    payloads = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        payloads.append(payload)
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    await backend.aexecute("echo hi")
    assert "env" not in payloads[0]


async def test_sync_sandbox_env_vars_writes_local_backend(monkeypatch):
    """env_var 工具运行中改动经 sync_sandbox_env_vars 实时写入 local backend。"""
    from unittest.mock import AsyncMock

    from src.infra.envvar.sync import sync_sandbox_env_vars

    storage = AsyncMock()
    storage.get_decrypted_vars = AsyncMock(return_value={"FOO": "bar"})
    import src.infra.envvar.sync as envvar_sync

    monkeypatch.setattr(envvar_sync, "EnvVarStorage", lambda: storage)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    await sync_sandbox_env_vars(backend, "u1")
    assert backend.env_vars == {"FOO": "bar"}


async def test_resolve_platform_sticky_after_transient_lookup_failure(monkeypatch):
    """平台查询瞬断（redis 异常）不回退 posix：复用最近一次成功解析值。

    生产事故（2026-09-06）：一次查询失败把 win32 会话翻回 posix 分支，
    daemon 收到多行 POSIX python3 脚本产出垃圾输出（ls 全空、read 报
    unexpected server response）。粘滞缓存保证一次成功解析后不再漂移。
    """
    state = {"fail": False}

    async def fake_lookup(user_id, machine_id=None):
        if state["fail"]:
            return ""  # 真实 _lookup_daemon_platform 故障时回落空串（不抛异常）
        return "win32"

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", fake_lookup)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert await backend._resolve_platform() == "win32"

    state["fail"] = True
    assert await backend._resolve_platform() == "win32"


async def test_resolve_platform_posix_when_never_resolved(monkeypatch):
    """从未成功解析过平台的会话，查询失败仍按空串（posix 现状）处理。"""

    async def fake_lookup(user_id, machine_id=None):
        return ""  # 持续故障：真实契约回落空串

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", fake_lookup)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert await backend._resolve_platform() == ""


async def test_resolve_platform_prefers_hint_over_sticky_cache(monkeypatch):
    """显式 platform_hint 优先级最高，粘滞缓存不影响既有构造期提示语义。"""

    async def fake_lookup(user_id, machine_id=None):
        return "win32"

    monkeypatch.setattr(local_module, "_lookup_daemon_platform", fake_lookup)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1", platform_hint="linux")
    assert await backend._resolve_platform() == "linux"


# ---------------------------------------------------------------------------
# 分块下载（2026-09-06 生产事故）：daemon executor 的 stdout 只保留尾部
# 256KB（MAX_OUTPUT_BYTES）并加 "...[truncated]" 前缀——单命令整读的
# base64 流超线即被毁，>192KB 文件 reveal/下载全部 invalid_download_output，
# 上层误报 file_not_found_or_empty（1.2MB 截图案例）。
# ---------------------------------------------------------------------------

_DAEMON_MAX_OUTPUT_BYTES = 256 * 1024
_DAEMON_TRUNC_MARK = "...[truncated]"


def _truncating_exec_dispatch(cwd: Path):
    """fake dispatch：真实执行命令，并复刻 daemon 的 stdout 截断语义。"""

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        proc = subprocess.run(payload["command"], shell=True, cwd=cwd, capture_output=True)
        stdout = proc.stdout
        if len(stdout) > _DAEMON_MAX_OUTPUT_BYTES:
            stdout = _DAEMON_TRUNC_MARK.encode() + stdout[-_DAEMON_MAX_OUTPUT_BYTES:]
        return {
            "status": "ok",
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
        }

    return fake_dispatch


async def test_download_files_large_file_survives_daemon_output_truncation(monkeypatch, tmp_path):
    """>分块线的文件必须分片回传：在复刻 daemon 截断的链路上 2.65MB 全量还原。

    体量刻意压过已删除的旧 2MB 下载上限——上限统一走
    S3_INTERNAL_UPLOAD_MAX_SIZE（默认 1GB），本地下载不再有自己的小额度。
    """
    import os

    data = os.urandom(144 * 1024 * 18 + 1234)  # ~2.65MB，跨 19 个分块
    target = tmp_path / "big.bin"
    target.write_bytes(data)

    monkeypatch.setattr(local_module, "dispatch_local_call", _truncating_exec_dispatch(tmp_path))
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files([str(target)])

    assert responses[0].error is None, responses[0].error
    assert responses[0].content == data


async def test_download_files_small_file_roundtrip(monkeypatch, tmp_path):
    """≤分块线的文件同样经 stat+单片往返，内容必须逐字节还原。"""
    data = b"tiny-body"
    target = tmp_path / "small.txt"
    target.write_bytes(data)

    monkeypatch.setattr(local_module, "dispatch_local_call", _truncating_exec_dispatch(tmp_path))
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files([str(target)])

    assert responses[0].error is None
    assert responses[0].content == data


async def test_download_files_oversize_reports_too_large_without_slicing(monkeypatch, tmp_path):
    """超过统一上限（环境变量 S3_INTERNAL_UPLOAD_MAX_SIZE）直接 file_too_large，
    报错信息带字节数与上限来源，且不下发任何分片命令。"""
    data = b"x" * 200
    target = tmp_path / "huge.bin"
    target.write_bytes(data)

    monkeypatch.setattr(local_module, "_download_max_bytes", lambda: 100)
    commands = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        if "getsize" in payload["command"]:
            return _ok_response(stdout=str(len(data)))
        raise AssertionError(f"unexpected command after size probe: {payload['command']}")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files([str(target)])

    assert responses[0].content is None
    assert responses[0].error is not None
    assert responses[0].error.startswith("file_too_large: 200 bytes exceeds 100 limit")
    assert "S3_INTERNAL_UPLOAD_MAX_SIZE" in responses[0].error
    assert len(commands) == 1  # 只有 stat 探测，零分片下发


def test_download_size_and_slice_commands_are_windows_safe(_default_daemon_platform):
    """win32 分片/探测命令：单行脚本、无 % 格式化（cmd 会吞双引号内的 % 对）。"""
    _default_daemon_platform["platform"] = "win32"
    size_cmd = LocalSandboxBackend._download_size_command("/workspace/s1/big.bin", platform="win32")
    slice_cmd = LocalSandboxBackend._download_slice_command(
        "/workspace/s1/big.bin", offset=144 * 1024, length=144 * 1024, platform="win32"
    )
    for cmd in (size_cmd, slice_cmd):
        assert "\n" not in cmd  # cmd.exe 逐行解析
        assert cmd.count('"') % 2 == 0
        assert "python3 -c " in cmd
        assert "%d" not in cmd and "%s" not in cmd
    assert "f.seek(147456)" in slice_cmd
    assert "f.read(147456)" in slice_cmd


# =========================================================================
# 持久共享目录别名（/workspace/.shared → data_root/.shared，跨会话复用）
# =========================================================================


def _shared_layout_exec_dispatch(base: Path):
    """fake dispatch：按 daemon 契约把虚拟 cwd 映射到 base 下真实目录后执行。

    `/workspace/s1` → base/s1，`/workspace/.shared` → base/.shared——与真 daemon
    的 map_workspace 对 ".shared" 这个 sid 的映射一致；fs_upload/fs_download
    走真实 fsops（同一映射规则），exec 与 fs 两类 op 看到同一份文件树。
    """
    from lambchat_sandbox import fsops

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        if op in ("fs_upload", "fs_download"):
            result = fsops.handle_fs_op(op, payload, base)
            return {"stage": "done", "status": "ok", "result": result}
        virtual_cwd = str(payload.get("cwd", "/workspace/s1"))
        target = base / virtual_cwd.removeprefix("/workspace/")
        target.mkdir(parents=True, exist_ok=True)  # 对齐真 daemon：exec 前 mkdir 工作区
        proc = subprocess.run(payload["command"], shell=True, cwd=target, capture_output=True)
        return {
            "status": "ok",
            "stdout": proc.stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
        }

    return fake_dispatch


async def test_alias_awrite_via_shared_dir_alias_lands_in_shared_root(monkeypatch, tmp_path):
    """posix 写经 /workspace/.shared/x 落到 data_root/.shared/x（不在会话目录内）。"""
    monkeypatch.setattr(local_module, "dispatch_local_call", _shared_layout_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")

    result = await backend.awrite("/workspace/.shared/skills/demo.md", "shared-body")

    assert result.error is None
    assert result.path == "/workspace/.shared/skills/demo.md"
    assert (tmp_path / ".shared" / "skills" / "demo.md").read_text(
        encoding="utf-8"
    ) == "shared-body"
    assert not (tmp_path / "s1" / "skills").exists()


async def test_alias_aread_via_shared_dir_alias(monkeypatch, tmp_path):
    shared_root = tmp_path / ".shared"
    (shared_root / "skills").mkdir(parents=True)
    (shared_root / "skills" / "note.txt").write_text("shared-note", encoding="utf-8")
    monkeypatch.setattr(local_module, "dispatch_local_call", _shared_layout_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s2")

    result = await backend.aread("/workspace/.shared/skills/note.txt")

    assert result.error is None
    assert "shared-note" in str(result.file_data["content"])


async def test_alias_als_shared_dir_lists_public_prefixed_paths(monkeypatch, tmp_path):
    shared_root = tmp_path / ".shared"
    (shared_root / "tool").mkdir(parents=True)
    (shared_root / "tool" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(local_module, "dispatch_local_call", _shared_layout_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")

    result = await backend.als("/workspace/.shared/tool")

    assert result.error is None
    paths = {entry["path"] for entry in (result.entries or [])}
    assert paths == {"/workspace/.shared/tool/run.sh"}


async def test_alias_upload_download_via_shared_dir_alias(monkeypatch, tmp_path):
    monkeypatch.setattr(local_module, "dispatch_local_call", _shared_layout_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")

    upload = await backend.aupload_files([("/workspace/.shared/up/demo.txt", b"payload")])
    assert len(upload) == 1
    assert upload[0].path == "/workspace/.shared/up/demo.txt"
    assert upload[0].error is None
    assert (tmp_path / ".shared" / "up" / "demo.txt").read_bytes() == b"payload"

    download = await backend.adownload_files(["/workspace/.shared/up/demo.txt"])
    assert download[0].path == "/workspace/.shared/up/demo.txt"
    assert download[0].content == b"payload"


async def test_win32_fs_call_rebases_shared_path_to_shared_cwd(monkeypatch, tmp_path):
    """win32 结构化 fs op：../.shared/x 重定位为 cwd=/workspace/.shared + 相对路径。"""
    captured: list[tuple[str, dict]] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append((op, dict(payload)))
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(
        user_id="u1", session_id="s1", platform_hint="win32"
    )

    result = await backend.awrite("/workspace/.shared/skills/demo.md", "win-shared")

    assert result.error is None
    assert result.path == "/workspace/.shared/skills/demo.md"
    op, payload = captured[-1]
    assert op == "fs_write"
    assert payload["cwd"] == "/workspace/.shared"
    assert payload["path"] == "skills/demo.md"


async def test_alias_paths_outside_shared_alias_keep_segment_boundary(monkeypatch):
    """/workspace/.shared-x 不是共享别名，按别名外绝对路径原样透传。"""
    captured: list[dict] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        captured.append(dict(payload))
        return _ok_response(stdout="{}")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")

    await backend.aread("/workspace/.shared-x/note.txt")

    assert captured[-1]["cwd"] == "/workspace/s1"

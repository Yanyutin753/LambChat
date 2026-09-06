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
    monkeypatch.setattr(local_module, "dispatch_local_call", _real_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    result = await backend.awrite("/workspace/s1/new.txt", "written-via-alias")
    assert result.error is None
    assert result.path == "/workspace/s1/new.txt"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "written-via-alias"


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
    """端到端验收：>128KB 内容上传成功——分块多条命令写入，落盘内容逐字节一致。

    旧实现把整个 base64 塞单个 argv，超过内核 MAX_ARG_STRLEN（单参数 128KB，
    扣除引号/命令开销 ~96KB 即断）触发 E2BIG，且被误分类为 file_not_found。
    """
    content = bytes(range(256)) * 1024  # 256KB 确定性内容
    commands: list[str] = []
    real = _real_exec_dispatch(tmp_path)

    async def tracking_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return await real(user_id, op, payload, timeout=timeout)

    monkeypatch.setattr(local_module, "dispatch_local_call", tracking_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
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


async def test_adownload_files_oversized_explicit_error(monkeypatch, tmp_path):
    """端到端验收：超过统一上限的文件得显式 file_too_large（带字节数与
    S3_INTERNAL_UPLOAD_MAX_SIZE 来源），而非 base64 半途炸或误报。"""
    (tmp_path / "big.bin").write_bytes(b"0" * 200)
    monkeypatch.setattr(local_module, "_download_max_bytes", lambda: 100)
    monkeypatch.setattr(local_module, "dispatch_local_call", _real_exec_dispatch(tmp_path))
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/big.bin"])
    assert responses[0].error is not None
    assert responses[0].error.startswith("file_too_large: 200 bytes exceeds 100 limit")
    assert responses[0].content is None


async def test_adownload_files_within_limit_roundtrips(monkeypatch, tmp_path):
    """限内文件走 stat 预检路径正常回读：内容逐字节一致。"""
    payload = b"roundtrip-body-\x00\x01" * 64
    (tmp_path / "ok.bin").write_bytes(payload)
    monkeypatch.setattr(local_module, "dispatch_local_call", _real_exec_dispatch(tmp_path))
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
    """win32 分块上传：首块带 makedirs、后续块无（对仗 posix 分块语义）。"""
    _default_daemon_platform["platform"] = "win32"
    commands: list[str] = []

    async def fake_dispatch(user_id, op, payload, *, timeout=None, machine_id=None):
        commands.append(payload["command"])
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    content = b"x" * (local_module._UPLOAD_CHUNK_RAW_BYTES + 1)
    responses = await backend.aupload_files([("/workspace/s1/big.bin", content)])
    assert responses[0].error is None
    assert len(commands) == 2
    assert "os.makedirs" in commands[0] and "'wb'" in commands[0]
    assert "os.makedirs" not in commands[1] and "'ab'" in commands[1]
    assert all("mkdir -p" not in c for c in commands)


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

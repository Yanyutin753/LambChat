"""LocalSandboxBackend 测试：execute 往返、离线透传、id、upload/download 经中继执行。

ExecuteResponse 真实字段为 output/exit_code/truncated（protocol.py:810），
无 stdout/stderr 字段——stdout/stderr 在 aexecute 内合并进 output。
"""

import base64
import subprocess
from pathlib import Path

import pytest

from src.infra.backend import local as local_module
from src.infra.backend.local import LocalSandboxBackend
from src.kernel.errors import AppError, ErrorCode


def _ok_response(stdout: str = "", stderr: str = "", exit_code: int = 0) -> dict:
    return {"status": "ok", "stdout": stdout, "stderr": stderr, "exit_code": exit_code}


def _real_exec_dispatch(cwd: Path):
    """fake dispatch：像真 daemon 一样在映射后的工作区目录（cwd）真实执行命令。

    返回 dict 带 stdout/stderr/exit_code 独立字段——与 daemon executor 契约一致。
    """

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        proc = subprocess.run(
            payload["command"], shell=True, cwd=cwd, capture_output=True
        )
        return {
            "status": "ok",
            "stdout": proc.stdout.decode("utf-8", errors="replace"),
            "stderr": proc.stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
        }

    return fake_dispatch


async def test_aexecute_maps_result(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
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
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        if payload["command"] == "both":
            return _ok_response(stdout="out", stderr="err")
        return _ok_response(stderr="only-err")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    assert (await backend.aexecute("both")).output == "out\nerr"
    assert (await backend.aexecute("fail-only")).output == "only-err"


async def test_aexecute_passes_cwd_and_timeout(monkeypatch):
    captured = {}

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        captured.update(op=op, payload=payload, timeout=timeout)
        return _ok_response()

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1", exec_timeout=7)
    await backend.aexecute("ls")
    assert captured["op"] == "exec"
    assert captured["payload"] == {"command": "ls", "cwd": "/workspace/s1"}
    assert captured["timeout"] == 7.0


async def test_offline_propagates(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
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
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        return _ok_response(stdout="sync-hi")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = backend.execute("echo sync-hi")
    assert resp.output == "sync-hi"
    assert resp.exit_code == 0


def test_download_files_decodes_base64(monkeypatch):
    content = "file-body"

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        b64 = base64.b64encode(content.encode()).decode()
        return _ok_response(stdout=b64)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files(["/workspace/s1/a.txt"])
    assert len(responses) == 1
    assert responses[0].error is None
    assert responses[0].content == content.encode()


def test_download_files_stderr_does_not_pollute_base64(monkeypatch):
    """download 解码只取 stdout 字段：stderr 非空（如 shell 告警）不得混进 base64。

    旧实现经 aexecute 把 stdout+stderr 合并进 output 再解码，stderr 文本里
    的字母会被 base64 解码器吞掉，产出损坏字节。
    """
    content = b"file-body"
    noisy = "grep: warning: something noisy on stderr"

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        assert payload["cwd"] == "/workspace/s1"  # 与 aexecute 同 cwd 契约
        b64 = base64.b64encode(content).decode()
        return _ok_response(stdout=b64, stderr=noisy)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files(["/workspace/s1/a.txt"])
    assert responses[0].error is None
    assert responses[0].content == content


async def test_adownload_files_stderr_does_not_pollute_base64(monkeypatch):
    # 内容长度取 3 的倍数：b64 无 padding，旧实现的合并解码无法借 padding 截断蒙混过关
    content = b"async-body-1"
    noisy = "[PID 123] some daemon chatter"

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        b64 = base64.b64encode(content).decode()
        return _ok_response(stdout=b64, stderr=noisy)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = await backend.adownload_files(["/workspace/s1/a.bin"])
    assert responses[0].error is None
    assert responses[0].content == content


def test_download_files_maps_missing_to_error(monkeypatch):
    # 真实 daemon 的 ENOENT 输出（python3 open() 抛出后经 stderr 回传）
    enoent = "[Errno 2] No such file or directory: '/workspace/s1/missing.txt'"

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        return _ok_response(stdout=enoent, exit_code=1)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files(["/workspace/s1/missing.txt"])
    # ENOENT 文本含 "directory" 子串，不能被误分类为 is_directory
    assert responses[0].error == "file_not_found"
    assert responses[0].content is None


def test_download_files_maps_is_directory_error(monkeypatch):
    eisdir = "[Errno 21] Is a directory: '/workspace/s1'"

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        return _ok_response(stdout=eisdir, exit_code=1)

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    responses = backend.download_files(["/workspace/s1"])
    assert responses[0].error == "is_directory"


def test_classify_file_error_real_daemon_strings():
    classify = local_module._classify_file_error
    assert classify("[Errno 2] No such file or directory: '/workspace/x'") == "file_not_found"
    assert classify("/bin/sh: cat: /workspace/x: No such file or directory") == "file_not_found"
    assert classify("[Errno 21] Is a directory: '/workspace/x'") == "is_directory"
    assert classify("[Errno 13] Permission denied: '/root/x'") == "permission_denied"
    assert classify("mkdir: cannot create directory '/x': Permission denied") == "permission_denied"


async def test_aexecute_missing_exit_code_is_undetermined(monkeypatch):
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        return {"status": "ok", "stdout": "partial"}

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = LocalSandboxBackend(user_id="u1", session_id="s1")
    resp = await backend.aexecute("cmd")
    # 缺失 exit_code 透传 None（协议：None = 未确定），不得伪装成 0 成功
    assert resp.output == "partial"
    assert resp.exit_code is None


def test_upload_files_writes_via_exec(monkeypatch):
    captured = {}

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
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
    async def fake_dispatch(user_id, op, payload, *, timeout=None):
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

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
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

    async def fake_dispatch(user_id, op, payload, *, timeout=None):
        captured.append(payload["cwd"])
        return _ok_response(stdout="{}")

    monkeypatch.setattr(local_module, "dispatch_local_call", fake_dispatch)
    backend = local_module.WorkspaceAliasBackend(user_id="u1", session_id="s1")
    await backend.aread("/etc/hostname")
    assert captured == ["/workspace/s1"]  # cwd 契约不变，仍是虚拟别名


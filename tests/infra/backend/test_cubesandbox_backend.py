from __future__ import annotations

import base64
import re
from types import SimpleNamespace


class _FakeCommandsAPI:
    """模拟 Cube commands.run：识别 stat/base64/dd/mkdir 片段，其余回固定输出。

    stdout 事件按 SDK 语义 utf-8 replace 解码——base64 是纯 ASCII，字节安全。
    """

    def __init__(self, files_api: "_FakeFilesAPI") -> None:
        self.calls: list[dict] = []
        self._files = files_api

    def run(self, **kwargs):
        self.calls.append(kwargs)
        stdout = self._interpret(kwargs.get("cmd", ""))
        return SimpleNamespace(stdout=stdout, stderr="", exit_code=0)

    def _interpret(self, cmd: str) -> str:
        # _with_work_dir 会拼 mkdir/cd 前缀；逐段解释
        for segment in cmd.split(" && "):
            segment = segment.strip()
            if not segment or segment.startswith(("mkdir ", "cd ")):
                continue
            m = re.fullmatch(r"stat -c %s (\S+)(?: 2>/dev/null)?", segment)
            if m:
                data = self._files.contents.get(m.group(1))
                return "" if data is None else str(len(data))
            m = re.fullmatch(r"base64 -w0 (\S+)", segment)
            if m:
                data = self._files.contents.get(m.group(1))
                if data is None:
                    raise IOError(f"No such file: {m.group(1)}")
                return base64.b64encode(data).decode()
            m = re.fullmatch(
                r"dd if=(\S+) bs=(\d+) skip=(\d+) count=(\d+) 2>/dev/null \| base64 -w0",
                segment,
            )
            if m:
                path, bs, skip, count = (
                    m.group(1),
                    int(m.group(2)),
                    int(m.group(3)),
                    int(m.group(4)),
                )
                data = self._files.contents.get(path)
                if data is None:
                    raise IOError(f"No such file: {path}")
                return base64.b64encode(data[skip * bs : (skip + count) * bs]).decode()
        return "cube-ok\n"


class _FakeFilesAPI:
    """模拟 Cube SDK files API：read 恒返回 lossy 解码 str（真实 SDK resp.text 语义）。"""

    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}

    def write(self, path: str, data: str | bytes) -> None:
        self.contents[path] = data.encode("utf-8") if isinstance(data, str) else data

    def read(self, path: str, format: str = "text"):  # noqa: A002 - 与 SDK 签名对齐
        data = self.contents[path]
        # 真实 Cube SDK 无 format 参数，恒 resp.text（utf-8 replace）
        del format
        return data.decode("utf-8", "replace")

    def list(self, path: str):
        return [
            SimpleNamespace(path=item_path, is_dir=False, size=len(value))
            for item_path, value in self.contents.items()
            if item_path.rsplit("/", 1)[0] == path.rstrip("/")
        ]


class _FakeHttpClient:
    """模拟 sandbox._client：envd /files 原始字节直读的主通道。"""

    def __init__(self, files_api: "_FakeFilesAPI", status_code: int = 200) -> None:
        self._files = files_api
        self.status_code = status_code
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None):
        self.calls.append(
            {"url": url, "params": dict(params or {}), "headers": dict(headers or {})}
        )
        data = self._files.contents.get((params or {}).get("path"))
        if data is None or self.status_code != 200:
            return SimpleNamespace(status_code=self.status_code, content=b"", text="err")
        return SimpleNamespace(status_code=200, content=data, text="")


class _FakeCubeSandbox:
    def __init__(self) -> None:
        self.sandbox_id = "cube-test"
        self._client = None
        self.files = _FakeFilesAPI()
        self.commands = _FakeCommandsAPI(self.files)

    def get_host(self, port: int) -> str:
        return f"{port}-cube-test.cube.app"


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


def test_cubesandbox_backend_read_returns_v07_pagination_metadata() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    sandbox.files.contents["/home/user/session-a/note.txt"] = b"alpha\nbeta\ngamma\n"
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.read("note.txt", offset=1, limit=1)

    assert result.file_data["content"] == "beta\n"
    assert result.start_line == 2
    assert result.end_line == 2
    assert result.next_offset == 2
    assert result.total_lines == 3


def test_cubesandbox_default_command_timeout_not_clamped_by_platform_timeout(
    monkeypatch,
) -> None:
    """单条命令默认超时保持 15 分钟下限，不被（较小的）平台空闲超时钳住。"""
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    monkeypatch.setattr("src.infra.backend.cubesandbox.settings.CUBE_TIMEOUT", 77)
    monkeypatch.setattr("src.infra.backend.cubesandbox.settings.E2B_TIMEOUT", 999)

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox)

    backend.execute("echo timeout")

    assert sandbox.commands.calls[0]["timeout"] == 900


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


class _WakeRecordingSandbox(_FakeCubeSandbox):
    def __init__(self) -> None:
        super().__init__()
        self.resume_calls: list[int | None] = []

    def resume(self, timeout: int | None = None) -> None:
        self.resume_calls.append(timeout)


def test_cubesandbox_execute_wakes_via_resume_and_retries_paused_error() -> None:
    from types import SimpleNamespace

    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _WakeRecordingSandbox()

    def first_paused_then_ok(**kwargs):
        sandbox.commands.calls.append(kwargs)
        if len(sandbox.commands.calls) == 1:
            raise RuntimeError("sandbox is paused")
        return SimpleNamespace(stdout="resumed-ok\n", stderr="", exit_code=0)

    sandbox.commands.run = first_paused_then_ok  # type: ignore[method-assign]
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.execute("task")

    assert result.exit_code == 0
    assert "resumed-ok" in (result.output or "")
    assert sandbox.resume_calls  # 唤醒走的是 Cube 的 resume()


def test_cubesandbox_execute_does_not_retry_timeouts() -> None:

    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _WakeRecordingSandbox()
    calls: list[dict] = []

    def always_timeout(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("command timed out")

    sandbox.commands.run = always_timeout  # type: ignore[method-assign]
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.execute("sleep 999")

    assert result.exit_code == -1
    assert len(calls) == 1
    assert sandbox.resume_calls == []


# ── 二进制文件字节安全（2026-10-14 生产事故：Word/PDF 经 download 损坏）──


def _binary_payload(size: int = 8192) -> bytes:
    """docx/zip 风格：PK 头 + 不可 UTF-8 解码的高熵字节 + 压缩尾。"""
    body = bytes(range(256)) * (size // 256 + 1)
    return b"PK\x03\x04" + body[: size - 10] + b"\xff\xfePK\x05\x06\x00"


def test_cubesandbox_download_files_returns_exact_binary_bytes() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    payload = _binary_payload()
    sandbox.files.contents["/home/user/session-a/blob.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["blob.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload


def test_cubesandbox_read_binary_returns_base64_file_data() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    payload = b"\x89PNG\r\n\x1a\n" + _binary_payload(4096)
    sandbox.files.contents["/home/user/session-a/img.png"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.read("img.png")

    assert result.error is None
    assert result.file_data["encoding"] == "base64"
    assert base64.b64decode(result.file_data["content"]) == payload


def test_cubesandbox_download_empty_binary_file() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    sandbox.files.contents["/home/user/session-a/empty.bin"] = b""
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["empty.bin"])

    assert responses[0].error is None
    assert responses[0].content == b""


def test_cubesandbox_download_large_binary_chunks(monkeypatch) -> None:
    """超过单块上限的文件走 dd 分块通道，字节仍精确。"""
    from src.infra.backend import cubesandbox as mod
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    monkeypatch.setattr(mod, "_B64_CHUNK_BYTES", 256 * 1024)
    monkeypatch.setattr(mod, "_B64_CHUNK_BS", 64 * 1024)
    sandbox = _FakeCubeSandbox()
    payload = _binary_payload(700 * 1024)  # → 3 块
    sandbox.files.contents["/home/user/session-a/big.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["big.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload
    dd_calls = [c for c in sandbox.commands.calls if "dd if=" in c["cmd"]]
    assert len(dd_calls) == 3


def test_cubesandbox_download_reports_size_mismatch(monkeypatch) -> None:
    """分块解码长度与 stat 不符（传输截断）必须报错，绝不交付损坏字节。"""
    from src.infra.backend import cubesandbox as mod
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    monkeypatch.setattr(mod, "_B64_CHUNK_BYTES", 256 * 1024)
    monkeypatch.setattr(mod, "_B64_CHUNK_BS", 64 * 1024)

    class _TruncatingCommands(_FakeCommandsAPI):
        def run(self, **kwargs):
            out = super().run(**kwargs)
            if "dd if=" in kwargs.get("cmd", ""):
                # 模拟传输截断：丢一半
                return SimpleNamespace(
                    stdout=out.stdout[: len(out.stdout) // 2], stderr="", exit_code=0
                )
            return out

    sandbox = _FakeCubeSandbox()
    sandbox.commands = _TruncatingCommands(sandbox.files)
    payload = _binary_payload(700 * 1024)
    sandbox.files.contents["/home/user/session-a/trunc.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["trunc.bin"])

    assert responses[0].error == "file_not_found"
    assert responses[0].content is None


def test_cubesandbox_read_text_still_plain() -> None:
    """文本文件不进 base64 通道，保持分页语义。"""
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    sandbox.files.contents["/home/user/session-a/note.txt"] = "纯文本内容\n第二行\n".encode()
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    result = backend.read("note.txt")

    assert result.error is None
    assert result.file_data["content"] == "纯文本内容\n第二行\n"


async def test_cubesandbox_adownload_files_returns_exact_binary_bytes() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    payload = _binary_payload()
    sandbox.files.contents["/home/user/session-a/blob.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")
    backend._async_disabled = True  # 测试环境不连真实 async 客户端，走线程回落

    responses = await backend.adownload_files(["blob.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload


async def test_cubesandbox_aread_binary_returns_base64_file_data() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    payload = _binary_payload(4096)
    sandbox.files.contents["/home/user/session-a/img.png"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")
    backend._async_disabled = True

    result = await backend.aread("img.png")

    assert result.error is None
    assert result.file_data["encoding"] == "base64"
    assert base64.b64decode(result.file_data["content"]) == payload


def test_cubesandbox_download_uses_envd_http_primary_channel() -> None:
    """主通道＝envd HTTP 原始字节（大文件快、无 base64 膨胀），不回落命令通道。"""
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    client = _FakeHttpClient(sandbox.files)
    sandbox._client = client
    payload = _binary_payload()
    sandbox.files.contents["/home/user/session-a/blob.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["blob.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload
    assert client.calls, "主通道应走 envd HTTP"
    from cubesandbox._commands import DEFAULT_ENVD_USER as SDK_DEFAULT_USER

    assert client.calls[0]["params"].get("username") == SDK_DEFAULT_USER
    assert not any("dd if=" in c["cmd"] for c in sandbox.commands.calls), "不应回落命令通道"


def test_cubesandbox_download_falls_back_when_envd_http_fails() -> None:
    """envd HTTP 失败（如 5xx/内部结构漂移）时回落 base64 命令通道，字节仍精确。"""
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    sandbox._client = _FakeHttpClient(sandbox.files, status_code=500)
    payload = _binary_payload()
    sandbox.files.contents["/home/user/session-a/blob.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    responses = backend.download_files(["blob.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload
    assert any("base64" in c["cmd"] for c in sandbox.commands.calls), "应回落命令通道"


async def test_cubesandbox_adownload_uses_envd_http_primary_channel() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    client = _FakeHttpClient(sandbox.files)
    sandbox._client = client
    payload = _binary_payload()
    sandbox.files.contents["/home/user/session-a/blob.bin"] = payload
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")
    backend._async_disabled = True

    responses = await backend.adownload_files(["blob.bin"])

    assert responses[0].error is None
    assert responses[0].content == payload
    assert client.calls


def test_cubesandbox_unimplemented_async_handshake_fails_fast_quietly(caplog) -> None:
    """控制面未实现 e2b connect 握手（JSONDecodeError）：一次禁用、不刷 WARNING。"""
    import logging

    from src.infra.backend.cubesandbox import CubeSandboxBackend

    sandbox = _FakeCubeSandbox()
    backend = CubeSandboxBackend(sandbox=sandbox, work_dir="/home/user/session-a")

    with caplog.at_level(logging.WARNING, logger="src.infra.backend.cubesandbox"):
        backend._register_async_init_failure(
            ValueError("Expecting value: line 1 column 1 (char 0)")
        )

    assert backend._async_disabled is True
    assert backend._async_init_failures == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    # 其他错误仍走基类语义（不禁用、计一次失败）
    backend2 = CubeSandboxBackend(sandbox=_FakeCubeSandbox(), work_dir="/w")
    backend2._register_async_init_failure(RuntimeError("connection refused"))
    assert backend2._async_disabled is False
    assert backend2._async_init_failures == 1

"""沙箱上传失败的错误码映射：未知失败不得兜底成 file_not_found。

2026-09-06 生产事故：win32 本地沙箱上传命令超长（cmd.exe 8191 字符命令行
上限）失败，被三个沙箱后端的兜底分支统一标成 file_not_found——agent 与用户
都被「文件不存在」的假象带偏（实际源文件一直可读，transfer 报失败、read_file
却正常）。真 ENOENT 仍归 file_not_found；识别不了的失败如实报
upload_failed / io_error。
"""

from __future__ import annotations

from src.infra.backend.daytona import DaytonaBackend
from src.infra.backend.e2b import E2BBackend
from src.infra.backend.protocol_compat import classify_upload_error

# ---------- 共享映射 helper ----------


def test_classify_upload_error_known_families():
    assert classify_upload_error("No such file or directory: '/x'") == "file_not_found"
    assert classify_upload_error("[Errno 2] No such file or directory") == "file_not_found"
    assert classify_upload_error("Permission denied") == "permission_denied"
    assert classify_upload_error("Is a directory: '/x'") == "is_directory"
    assert classify_upload_error("EISDIR") == "is_directory"


def test_classify_upload_error_unknown_defaults_to_upload_failed():
    assert classify_upload_error("connection reset by peer") == "upload_failed"
    assert classify_upload_error("") == "upload_failed"
    assert classify_upload_error("The filename or extension is too long") == "upload_failed"


# ---------- Daytona：fs.upload_files 异常经 helper 映射 ----------


class _FailingDaytonaFs:
    def upload_files(self, requests):
        raise RuntimeError("connection reset by peer")


class _DaytonaStub:
    def __init__(self):
        self.id = "stub"
        self.fs = _FailingDaytonaFs()


def test_daytona_upload_unknown_failure_reports_upload_failed(monkeypatch):
    backend = DaytonaBackend(_DaytonaStub())  # type: ignore[arg-type]
    monkeypatch.setattr(backend, "_ensure_parent_dir", lambda path: None)
    responses = backend.upload_files([("/home/user/a.txt", b"x")])
    assert len(responses) == 1
    assert responses[0].error == "upload_failed"


def test_daytona_upload_permission_failure_reports_permission_denied(monkeypatch):
    class _PermissionFs:
        def upload_files(self, requests):
            raise PermissionError("[Errno 13] Permission denied")

    stub = _DaytonaStub()
    stub.fs = _PermissionFs()
    backend = DaytonaBackend(stub)  # type: ignore[arg-type]
    monkeypatch.setattr(backend, "_ensure_parent_dir", lambda path: None)
    responses = backend.upload_files([("/home/user/a.txt", b"x")])
    assert responses[0].error == "permission_denied"


# ---------- E2B：files.write 异常经 helper 映射 ----------


class _FailingE2BFiles:
    def write(self, *, path, data):
        raise RuntimeError("connection reset by peer")


class _E2BStub:
    def __init__(self):
        self.files = _FailingE2BFiles()


def test_e2b_upload_unknown_failure_reports_upload_failed(monkeypatch):
    backend = E2BBackend(_E2BStub())  # type: ignore[arg-type]
    monkeypatch.setattr(backend, "_resolve_path", lambda path: path)
    monkeypatch.setattr(backend, "_ensure_parent_dir", lambda path: None)
    responses = backend.upload_files([("/home/user/a.txt", b"x")])
    assert len(responses) == 1
    assert responses[0].error == "upload_failed"

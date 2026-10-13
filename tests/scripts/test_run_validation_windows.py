"""Portable Windows gate behavior; the real kernel proof runs separately in CI."""

import ctypes
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "scripts/run_validation.py"


class FileHandle:
    def __init__(self, disk, mode):
        self.disk = disk
        self.binary = "b" in mode
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else len(self.disk.data) + offset
        return self.position

    def tell(self):
        return self.position

    def read(self, size=-1):
        if self.disk.held and self.disk.protect_byte_zero and self.position == 0:
            raise PermissionError("another process holds byte zero")
        end = len(self.disk.data) if size < 0 else self.position + size
        value = self.disk.data[self.position : end]
        self.position += len(value)
        return bytes(value) if self.binary else bytes(value).decode()

    def write(self, value):
        value = value.encode() if isinstance(value, str) else value
        end = self.position + len(value)
        self.disk.data[self.position : end] = value
        self.position = end
        return len(value)

    def truncate(self, size=None):
        del self.disk.data[self.position if size is None else size :]

    def flush(self):
        pass

    def fileno(self):
        return 17


class LockPath:
    def __init__(self, data, held, protect_byte_zero):
        self.data = bytearray(data)
        self.held = held
        self.protect_byte_zero = protect_byte_zero
        self.parent = self

    def __truediv__(self, _):
        return self

    def mkdir(self, **_):
        pass

    def read_text(self, **_):
        return self.open("r").read()

    def open(self, mode="r", **_):
        return FileHandle(self, mode)


class NativeFunction:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


@pytest.fixture
def windows_gate(monkeypatch):
    def make(*, held=True, protect_byte_zero=True, alive=True, owner="parent"):
        spec = importlib.util.spec_from_file_location("windows_validation_under_test", RUNNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        disk = LockPath(b' {"owner":"parent","pid":4312}', held, protect_byte_zero)
        calls = []
        process = {"alive": alive}

        def kill(pid, signal):
            calls.append(("kill", pid, signal))
            process["alive"] = False  # Windows os.kill(pid, 0) terminates the target.

        def open_process(access, inherit, pid):
            calls.append(("open", access, inherit, pid))
            assert access & 1 == 0, "PROCESS_TERMINATE must never be requested"
            return 91 if process["alive"] else 0

        kernel = SimpleNamespace(
            OpenProcess=NativeFunction(open_process),
            WaitForSingleObject=NativeFunction(lambda *_: 258 if process["alive"] else 0),
            CloseHandle=NativeFunction(lambda handle: calls.append(("close", handle)) or 1),
        )
        monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_k: kernel, raising=False)
        monkeypatch.setattr(module, "Path", SimpleNamespace(home=lambda: disk))
        monkeypatch.setattr(
            module,
            "os",
            SimpleNamespace(
                name="nt",
                environ={"LAMBCHAT_VALIDATION_OWNER": owner},
                kill=kill,
                getpid=lambda: 9001,
            ),
        )

        def locking(fd, mode, count):
            assert (fd, mode, count) == (17, 2, 1)
            if disk.held:
                raise OSError("lock busy")
            disk.held = True

        monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(LK_NBLCK=2, locking=locking))
        return module, disk, process, calls

    return make


def test_windows_nested_reads_metadata_beyond_locked_byte(windows_gate):
    module, _, process, _ = windows_gate()
    with module.validation_slot() as acquired:
        assert acquired is None
    assert process["alive"]


def test_windows_owner_writes_metadata_after_reserved_lock_byte(windows_gate):
    module, disk, _, _ = windows_gate(held=False, owner="")
    with module.validation_slot() as acquired:
        assert acquired is not None
        metadata = json.loads(bytes(disk.data[1:]))
        assert metadata == {"owner": module.os.environ["LAMBCHAT_VALIDATION_OWNER"], "pid": 9001}
        assert disk.data[0] in (0, 32)


def test_windows_parent_probe_is_read_only_and_closes_handle(windows_gate):
    module, _, process, calls = windows_gate(protect_byte_zero=False)
    with module.validation_slot() as acquired:
        assert acquired is None
    assert process["alive"], "nested admission must not terminate its lock owner"
    assert not any(call[0] == "kill" for call in calls)
    assert ("close", 91) in calls
    assert any(call[0] == "open" and call[3] == 4312 for call in calls)


def test_windows_dead_parent_cannot_authorize_nested_entry(windows_gate):
    module, _, _, _ = windows_gate(protect_byte_zero=False, alive=False)
    with pytest.raises(SystemExit) as caught:
        with module.validation_slot():
            pytest.fail("dead owner admitted a competing command")
    assert caught.value.code == 75


def test_windows_unrelated_owner_cannot_reuse_slot_or_probe_parent(windows_gate):
    module, _, process, calls = windows_gate(owner="stale-token")
    with pytest.raises(SystemExit) as caught:
        with module.validation_slot():
            pytest.fail("unrelated owner admitted")
    assert caught.value.code == 75
    assert process["alive"]
    assert not calls

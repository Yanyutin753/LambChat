"""Serialize local validation across worktrees using one per-user OS lock."""

import json
import os
import re
import secrets
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path


def _process_is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name != "nt":
        os.kill(pid, 0)
        return True

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, never TERMINATE
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT: still alive
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def validation_slot():
    path = Path.home() / ".cache/lambchat/validation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = os.environ.get("LAMBCHAT_VALIDATION_OWNER", "")
    nested = False
    try:
        if os.name == "nt":
            # Windows locks deny reads of byte zero, including buffered read-ahead.
            with path.open("rb", buffering=0) as metadata_file:
                metadata_file.seek(1)
                metadata = json.loads(metadata_file.read())
        else:
            metadata = json.loads(path.read_text())
        if owner and metadata.get("owner") == owner:
            nested = _process_is_alive(metadata["pid"])
    except (OSError, ValueError, KeyError):
        pass

    # Never unlink: replacing the inode would let another process bypass the lock.
    with path.open("a+b" if os.name == "nt" else "a+") as lock:
        if os.name == "nt":
            import msvcrt

            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            acquire()
        except OSError:
            if nested:
                yield None
                return
            print(
                "LambChat validation slot is busy; retry after all edits and the active task finish.",
                file=sys.stderr,
            )
            raise SystemExit(75)
        token = secrets.token_hex(16)
        metadata = {"owner": token, "pid": os.getpid()}
        if os.name == "nt":
            # Preserve the locked byte and put all readable metadata beyond it.
            lock.seek(1)
            lock.truncate()
            lock.write(json.dumps(metadata).encode("utf-8"))
        else:
            lock.seek(0)
            lock.truncate()
            json.dump(metadata, lock)
        lock.flush()
        os.environ["LAMBCHAT_VALIDATION_OWNER"] = token
        try:
            yield lock
        finally:
            if owner:
                os.environ["LAMBCHAT_VALIDATION_OWNER"] = owner
            else:
                os.environ.pop("LAMBCHAT_VALIDATION_OWNER", None)


def main():
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("Usage: python scripts/run_validation.py <command> [args…]", file=sys.stderr)
        return 2
    for index, argument in enumerate(command):
        match = re.fullmatch(
            r"(--(?:maxWorkers|maxConcurrency|concurrency|jobs)|-j)(?:=?(.+))?", argument
        )
        if argument == "--fileParallelism" or (
            match and (match[2] or (command[index + 1] if index + 1 < len(command) else "")) != "1"
        ):
            print("LambChat validation requires a single worker/job", file=sys.stderr)
            return 2
    with validation_slot() as lock:
        env = {
            **os.environ,
            "VITEST_MAX_WORKERS": "1",
            "CARGO_BUILD_JOBS": "1",
            "RAYON_NUM_THREADS": "1",
            "MAKEFLAGS": "-j1",
            "GOMAXPROCS": "1",
        }
        try:
            child = subprocess.Popen(
                command,
                env=env,
                start_new_session=lock is not None and os.name != "nt",
                **({"pass_fds": (lock.fileno(),)} if lock is not None and os.name != "nt" else {}),
            )
        except OSError as error:
            print(error, file=sys.stderr)
            return 127

        def forward(signum, _frame):
            if child.poll() is None:
                if lock is not None and os.name != "nt":
                    os.killpg(child.pid, signum)
                else:
                    child.send_signal(signum)

        previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = child.wait()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        return result if result >= 0 else 128 - result


if __name__ == "__main__":
    sys.exit(main())

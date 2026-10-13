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


@contextmanager
def validation_slot():
    path = Path.home() / ".cache/lambchat/validation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = os.environ.get("LAMBCHAT_VALIDATION_OWNER", "")
    nested = False
    try:
        metadata = json.loads(path.read_text())
        if owner and metadata.get("owner") == owner:
            os.kill(metadata["pid"], 0)
            nested = True
    except (OSError, ValueError, KeyError):
        pass

    # Never unlink: replacing the inode would let another process bypass the lock.
    with path.open("a+") as lock:
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
        lock.seek(0)
        lock.truncate()
        json.dump({"owner": token, "pid": os.getpid()}, lock)
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

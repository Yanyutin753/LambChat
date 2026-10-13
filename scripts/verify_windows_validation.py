"""Real Windows nested validation smoke, invoked inside run_validation.py.

Uses the real per-user lock without changing HOME, deleting it, or opening a
second validation slot. Competing probes must fail immediately with exit 75.
"""

import argparse
import ctypes
import json
import os
import secrets
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_validation.py"
BRIDGE = ROOT / "scripts/run-validation.mjs"
SELF = Path(__file__).resolve()


def process_alive(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
    finally:
        kernel.CloseHandle(handle)


def owner_metadata():
    # Unbuffered I/O must not touch the byte locked by the parent process.
    with (Path.home() / ".cache/lambchat/validation.lock").open("rb", buffering=0) as stream:
        stream.seek(1)
        return json.loads(stream.read())


def child(expected_owner_pid, exit_code):
    metadata = owner_metadata()
    assert metadata["pid"] == expected_owner_pid
    assert metadata["owner"] == os.environ["LAMBCHAT_VALIDATION_OWNER"]
    assert process_alive(expected_owner_pid), "validation owner was terminated"
    return exit_code


def invoke(command, env, expected, timeout=10):
    started = time.monotonic()
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode != expected:
        raise RuntimeError(
            f"Expected exit {expected}, got {result.returncode}: "
            f"{result.stdout[-1500:]} {result.stderr[-1500:]}"
        )
    return time.monotonic() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child-owner", type=int)
    parser.add_argument("--exit-code", type=int, default=0)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This smoke requires the actual Windows kernel")
    if not os.environ.get("LAMBCHAT_VALIDATION_OWNER"):
        parser.error("Invoke through python scripts/run_validation.py")
    if args.child_owner is not None:
        return child(args.child_owner, args.exit_code)

    metadata = owner_metadata()
    owner_pid = metadata["pid"]
    assert owner_pid != os.getpid()
    assert metadata["owner"] == os.environ["LAMBCHAT_VALIDATION_OWNER"]
    assert process_alive(owner_pid)
    env = dict(os.environ)
    inner = [sys.executable, str(SELF), "--child-owner", str(owner_pid)]
    # Held Python wrapper -> Node bridge -> another Python wrapper -> proof.
    for code in (0, 23):
        invoke(["node", str(BRIDGE), *inner, "--exit-code", str(code)], env, code)
        assert process_alive(owner_pid), "nested command killed its lock owner"

    for token in (None, secrets.token_hex(32)):
        contender_env = dict(env)
        if token is None:
            contender_env.pop("LAMBCHAT_VALIDATION_OWNER", None)
        else:
            contender_env["LAMBCHAT_VALIDATION_OWNER"] = token
        elapsed = invoke([sys.executable, str(RUNNER), *inner], contender_env, 75, timeout=5)
        assert elapsed < 5, "competing validation waited for the held slot"
        assert process_alive(owner_pid), "contender killed its lock owner"

    # Refusals must leave the original lease reusable and owner identity intact.
    invoke(["node", str(BRIDGE), *inner], env, 0)
    assert owner_metadata() == metadata
    assert process_alive(owner_pid)
    print("Windows validation smoke PASS: nested bridge, live parent, busy/stale owner, exit 23")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

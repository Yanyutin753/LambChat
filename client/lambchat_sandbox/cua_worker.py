"""Isolate native desktop APIs so a hung call cannot outlive its deadline."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

import psutil

_MAX_FRAME = 2 * 1024 * 1024


def _worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cua-worker"]
    return [sys.executable, "-m", "lambchat_sandbox", "--cua-worker"]


class CuaWorker:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._state: tempfile.TemporaryDirectory | None = None
        self._job: int | None = None

    async def call(self, op: str, payload: dict, *, timeout: float) -> dict:
        async with self._lock:
            try:
                async with asyncio.timeout(timeout):
                    if self._process is None:
                        self._state = tempfile.TemporaryDirectory(prefix="lambchat-cua-")
                        self._process = await asyncio.create_subprocess_exec(
                            *_worker_command(),
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.DEVNULL,
                            limit=_MAX_FRAME,
                            start_new_session=os.name != "nt",
                            creationflags=0x00000004 if os.name == "nt" else 0,  # CREATE_SUSPENDED
                            env={
                                **os.environ,
                                # The driver protects Windows ACLs only for directories it creates.
                                "AGENT_DESKTOP_HOME": str(Path(self._state.name) / "driver"),
                                "PYTHONPATH": str(Path(__file__).resolve().parents[1])
                                + os.pathsep
                                + os.environ.get("PYTHONPATH", ""),
                            },
                        )
                        if os.name == "nt":
                            # A launcher must join the Job before it can spawn the real worker.
                            self._attach_job(self._process.pid)
                            psutil.Process(self._process.pid).resume()
                    proc = self._process
                    assert proc.stdin is not None and proc.stdout is not None
                    request = json.dumps({"op": op, "payload": payload}).encode() + b"\n"
                    if len(request) > _MAX_FRAME:
                        return {"error": "invalid_arguments", "detail": "CUA request too large"}
                    proc.stdin.write(request)
                    await proc.stdin.drain()
                    result = json.loads(await proc.stdout.readline())
                    if not isinstance(result, dict):
                        raise ValueError("CUA worker returned a non-object")
                    return result
            except asyncio.CancelledError:
                await self.close()
                raise
            except TimeoutError:
                await self.close()
                return {
                    "error": "timeout",
                    "retry": "observe_first",
                    "detail": "Desktop worker stopped; observe before retrying input",
                }
            except (OSError, ValueError, psutil.Error):
                await self.close()
                return {
                    "error": "worker_failed",
                    "retry": "observe_first",
                    "detail": "Desktop worker lost; observe before retrying input",
                }

    def _attach_job(self, pid: int) -> None:
        from lambchat_sandbox import executor

        api = executor._winapi
        assert api is not None
        job = api.create_job_object()
        try:
            info = executor.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = executor.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            api.set_information_job_object(job, executor.JOBOBJECT_INFO_CLASS_EXTENDED_LIMIT, info)
            handle = api.open_process(executor.PROCESS_SET_QUOTA | executor.PROCESS_TERMINATE, pid)
            try:
                api.assign_process_to_job_object(job, handle)
            finally:
                api.close_handle(handle)
        except BaseException:
            api.close_handle(job)
            raise
        self._job = job

    async def close(self) -> None:
        proc, self._process = self._process, None
        job_closed = self._job is not None
        if self._job is not None:
            from lambchat_sandbox import executor

            assert executor._winapi is not None
            executor._winapi.close_handle(self._job)
            self._job = None
        if proc is None:
            if self._state is not None:
                self._state.cleanup()
                self._state = None
            return
        # Closing the Windows Job already terminates its entire process tree.
        if not job_closed:
            with contextlib.suppress(psutil.NoSuchProcess):
                parent = psutil.Process(proc.pid)
                parent.suspend()
                for child in reversed(parent.children(recursive=True)):
                    with contextlib.suppress(psutil.NoSuchProcess):
                        child.kill()
            if os.name != "nt":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            else:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
        await asyncio.wait_for(proc.wait(), timeout=5)
        if self._state is not None:
            self._state.cleanup()
            self._state = None


def worker_main() -> int:
    from lambchat_sandbox.cua_ops import handle_cua_op

    for line in sys.stdin.buffer:
        if len(line) > _MAX_FRAME:
            return 1
        request = json.loads(line)
        result = handle_cua_op(request["op"], request["payload"])
        encoded = json.dumps(result, ensure_ascii=False)
        if len(encoded.encode()) >= _MAX_FRAME:
            encoded = '{"error":"result_too_large"}'
        print(encoded, flush=True)
    return 0

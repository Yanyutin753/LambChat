"""Cloud file writes use the same execution-host commit primitive as the daemon."""

from __future__ import annotations

import base64
import json
import shlex
import uuid
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

from deepagents.backends.sandbox import BaseSandbox

from src.infra.backend._local_compat import _run_coro_sync
from src.infra.backend.protocol_compat import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileUploadResponse,
    ReadResult,
    WriteResult,
)


@lru_cache(maxsize=1)
def _commit_source() -> str:
    return (
        Path(__file__).resolve().parents[3] / "client/lambchat_sandbox/file_commit.py"
    ).read_text()


_DISPATCH = """
import base64
import tempfile
request = json.loads(base64.b64decode(PAYLOAD))
try:
    path = Path(request["path"]).resolve()
    if request["op"] == "version":
        answer = {"version": file_version(path), "path": str(path)}
    elif request["op"] == "stage":
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".lambchat-cloud-", delete=False) as stream:
            answer = {"stage": stream.name}
    elif request["op"] == "discard":
        stage = Path(request["stage"])
        if stage.parent != path.parent or not stage.name.startswith(".lambchat-cloud-"):
            raise FileCommitError("invalid staging path")
        stage.unlink(missing_ok=True)
        answer = {}
    elif request["op"] == "commit":
        commit_file(Path(request["stage"]) if request["stage"] else None, path, request["expected"], Path(request["history"]), actor=request["actor"])
        answer = {"version": file_version(path)}
    else:
        raise FileCommitError("unsupported file operation")
    print(RESULT_MARKER + json.dumps(answer))
except (FileCommitError, OSError, ValueError) as error:
    print(RESULT_MARKER + json.dumps({"error": str(error)}))
"""


class GuardedSandboxBackend(BaseSandbox):
    def __init__(self, backend, *, user_id: str, session_id: str):
        self._backend = backend
        self._user_id = user_id
        self._session_id = session_id
        self._versions: dict[str, str] = {}
        self.work_dir = backend.work_dir
        self._pending_notices: list[str] = []

    @property
    def id(self):
        return self._backend.id

    def __getattr__(self, name):
        return getattr(self._backend, name)

    @property
    def env_vars(self):
        return self._backend.env_vars

    @env_vars.setter
    def env_vars(self, value):
        self._backend.env_vars = value

    def _path(self, path: str) -> str:
        return str(Path(self.work_dir) / path) if not path.startswith("/") else path

    async def _remote(self, op: str, path: str, **kwargs) -> dict:
        request = {"op": op, "path": self._path(path), **kwargs}
        payload = base64.b64encode(json.dumps(request).encode()).decode()
        marker = "LAMBCHAT_FILE_RESULT_" + uuid.uuid4().hex + ":"
        script = (
            _commit_source()
            + "\n"
            + _DISPATCH.replace("PAYLOAD", repr(payload)).replace("RESULT_MARKER", repr(marker))
        )
        result = await self._backend.aexecute("python3 -c " + shlex.quote(script), timeout=120)
        if result.exit_code != 0:
            raise RuntimeError(result.output or "file operation failed")
        prefix, separator, encoded = result.output.rpartition(marker)
        if not separator:
            raise RuntimeError("Missing file operation result")
        if prefix.strip():
            self._pending_notices.append(prefix.strip())
        response = json.loads(encoded)
        if not isinstance(response, dict) or response.get("error"):
            raise RuntimeError(
                response.get("error") if isinstance(response, dict) else "invalid file response"
            )
        return response

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000):
        path = self._path(file_path)
        try:
            before = await self._remote("version", path)
            result = await self._backend.aread(path, offset, limit)
            after = await self._remote("version", path)
            if before != after:
                return ReadResult(
                    error="file_conflict: file changed while reading; reread required"
                )
            if not result.error:
                self._versions[path] = after["version"]
            return result
        except Exception as error:
            self._versions.pop(path, None)
            return ReadResult(error=str(error))

    async def _commit_content(self, file_path: str, content: bytes | None):
        path = self._path(file_path)
        stage = None
        try:
            expected = self._versions.get(path, "missing")
            current = await self._remote("version", path)
            if current["version"] != expected:
                raise RuntimeError("file_conflict: reread the current file before writing")
            if content is not None:
                stage = (await self._remote("stage", path))["stage"]
                uploads = await self._backend.aupload_files([(stage, content)])
                if len(uploads) != 1 or uploads[0].error:
                    raise RuntimeError("failed to stage file content")
            committed = await self._remote(
                "commit",
                path,
                stage=stage,
                expected=expected,
                history=str(Path(self.work_dir).parent / ".lambchat-file-history"),
                actor={"user_id": self._user_id, "session_id": self._session_id},
            )
            stage = None
            self._versions[path] = committed["version"]
            return WriteResult(path=file_path)
        except Exception as error:
            self._versions.pop(path, None)
            return WriteResult(error=str(error))
        finally:
            if stage is not None:
                with suppress(Exception):
                    await self._remote("discard", path, stage=stage)

    async def awrite(self, file_path: str, content: str):
        return await self._commit_content(file_path, content.encode("utf-8"))

    def write(self, file_path: str, content: str):
        return _run_coro_sync(self.awrite(file_path, content))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return _run_coro_sync(self.aread(file_path, offset, limit))

    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ):
        try:
            if not old_string:
                return EditResult(error="empty search string")
            files = await self._backend.adownload_files([self._path(file_path)])
            if len(files) != 1 or files[0].error or files[0].content is None:
                return EditResult(error="cannot read file for edit")
            text = files[0].content.decode("utf-8")
            old_lf = old_string.replace("\r\n", "\n")
            new_lf = new_string.replace("\r\n", "\n")
            candidates = (
                (old_string, new_string),
                (old_lf.replace("\n", "\r\n"), new_lf.replace("\n", "\r\n")),
                (old_lf, new_lf),
            )
            for old, new in candidates:
                count = text.count(old)
                if count:
                    break
            if not count:
                return EditResult(error="string_not_found")
            if count > 1 and not replace_all:
                return EditResult(error="multiple_occurrences")
            content = text.replace(old, new, -1 if replace_all else 1).encode("utf-8")
            result = await self._commit_content(file_path, content)
            return EditResult(
                error=result.error,
                path=result.path,
                occurrences=count if not result.error else None,
            )
        except Exception as error:
            return EditResult(error=str(error))

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        return _run_coro_sync(self.aedit(file_path, old_string, new_string, replace_all))

    async def adelete(self, file_path: str):
        result = await self._commit_content(file_path, None)
        return DeleteResult(error=result.error, path=result.path)

    def delete(self, file_path: str):
        return _run_coro_sync(self.adelete(file_path))

    async def aupload_files(self, files):
        results = []
        for path, content in files:
            result = await self._commit_content(path, content)
            results.append(FileUploadResponse(path=path, error=result.error))
        return results

    def upload_files(self, files):
        return _run_coro_sync(self.aupload_files(files))

    def download_files(self, paths):
        return self._backend.download_files(paths)

    async def adownload_files(self, paths):
        return await self._backend.adownload_files(paths)

    async def aexecute(self, command: str, *, timeout: int | None = None):
        self._versions.clear()
        return self._with_notices(await self._backend.aexecute(command, timeout=timeout))

    def execute(self, command: str, *, timeout: int | None = None):
        self._versions.clear()
        return self._with_notices(self._backend.execute(command, timeout=timeout))

    def _with_notices(self, result):
        if not self._pending_notices:
            return result
        output = "\n".join([*self._pending_notices, result.output or ""])
        self._pending_notices.clear()
        return ExecuteResponse(
            output=output, exit_code=result.exit_code, truncated=result.truncated
        )

    def ls(self, path):
        return self._backend.ls(path)

    async def als(self, path):
        return await self._backend.als(path)

    def glob(self, pattern, path=None):
        return self._backend.glob(pattern, path)

    async def aglob(self, pattern, path=None):
        return await self._backend.aglob(pattern, path)

    def grep(self, pattern, path=None, glob=None, *, max_count=None):
        return self._backend.grep(pattern, path, glob, max_count=max_count)

    async def agrep(self, pattern, path=None, glob=None, *, max_count=None):
        return await self._backend.agrep(pattern, path, glob, max_count=max_count)


def guard_cloud_backend(backend, *, user_id: str, session_id: str):
    from src.infra.backend.daytona import DaytonaBackend
    from src.infra.backend.e2b import E2BBackend

    if isinstance(backend, (E2BBackend, DaytonaBackend)):
        return GuardedSandboxBackend(backend, user_id=user_id, session_id=session_id)
    return backend

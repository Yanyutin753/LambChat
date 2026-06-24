"""deepagents backend backed by a user's connected desktop client."""

from __future__ import annotations

import asyncio
import base64
import json
import shlex
from typing import Any

from deepagents.backends.sandbox import BaseSandbox

from src.infra.backend.protocol_compat import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    ReadResult,
    WriteResult,
    file_download_response,
    file_upload_response,
)
from src.infra.client_sandbox.router import (
    ClientSandboxRouter,
    ClientSandboxRouterError,
    get_client_sandbox_router,
)
from src.infra.client_sandbox.storage import ClientSandboxStorage
from src.kernel.config import settings


class ClientSandboxBackend(BaseSandbox):
    """Route sandbox operations to a session-bound desktop client."""

    def __init__(
        self,
        *,
        user_id: str,
        session_id: str,
        storage: ClientSandboxStorage | Any | None = None,
        router: ClientSandboxRouter | Any | None = None,
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self._storage = storage or ClientSandboxStorage()
        self._router = router or get_client_sandbox_router()
        self._binding = None
        self.is_client_sandbox = True

    @property
    def id(self) -> str:
        if self._binding is not None:
            return f"client:{self._binding.device_id}"
        return "client:unbound"

    @property
    def work_dir(self) -> str:
        return "/workspace"

    async def _get_binding(self):
        if self._binding is None:
            self._binding = await self._storage.get_active_binding(self.user_id, self.session_id)
        if self._binding is None:
            raise ClientSandboxRouterError(
                "binding_missing",
                "No active desktop sandbox binding for this session",
            )
        return self._binding

    async def _call(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        binding = await self._get_binding()
        response = await self._router.call(
            user_id=self.user_id,
            device_id=binding.device_id,
            session_id=self.session_id,
            operation=operation,
            payload=payload,
            timeout_seconds=timeout or getattr(settings, "CLIENT_SANDBOX_RPC_TIMEOUT", 60),
        )
        if not response.ok:
            error = response.error
            message = error.message if error else "Desktop sandbox request failed"
            code = error.code if error else "client_error"
            raise ClientSandboxRouterError(code, message)
        return response.result or {}

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aexecute(command, timeout=timeout))
        if loop.is_running():
            return ExecuteResponse(
                output="Client sandbox execute() cannot be used from a running event loop; use aexecute().",
                exit_code=-1,
                truncated=False,
            )
        return loop.run_until_complete(self.aexecute(command, timeout=timeout))

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        try:
            await self._get_binding()
            result = await self._call(
                "execute",
                {"command": command, "cwd": "/workspace"},
                timeout=timeout,
            )
            return ExecuteResponse(
                output=str(result.get("output", "")),
                exit_code=int(result.get("exit_code", -1)),
                truncated=bool(result.get("truncated", False)),
            )
        except ClientSandboxRouterError as e:
            return ExecuteResponse(output=e.message, exit_code=-1, truncated=False)
        except Exception as e:
            return ExecuteResponse(
                output=f"Client sandbox failed: {e}", exit_code=-1, truncated=False
            )

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            result = await self._call(
                "read_file",
                {"path": file_path, "offset": offset, "limit": limit},
            )
            content = str(result.get("content", ""))
            return ReadResult(file_data={"content": content}, rendered_content=content)
        except ClientSandboxRouterError as e:
            return ReadResult(error=e.message)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:  # type: ignore[override]
        return asyncio.run(self.aread(file_path, offset, limit))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        try:
            await self._call("write_file", {"path": file_path, "content": content})
            return WriteResult(path=file_path, files_update=None)
        except ClientSandboxRouterError as e:
            return WriteResult(error=e.message)
        except Exception as e:
            return WriteResult(error=f"Client sandbox failed: {e}")

    def write(self, file_path: str, content: str) -> WriteResult:
        return asyncio.run(self.awrite(file_path, content))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        payload = {
            "path": file_path,
            "old": old_string,
            "new": new_string,
            "replace_all": bool(replace_all),
        }
        payload_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        command = (
            "python3 - <<'PY'\n"
            "import base64, json, pathlib, sys\n"
            f"payload = json.loads(base64.b64decode({payload_b64!r}).decode('utf-8'))\n"
            "path = pathlib.Path(payload['path'])\n"
            "if not path.is_file():\n"
            "    print(f\"Error: File '{payload['path']}' not found\")\n"
            "    sys.exit(3)\n"
            "text = path.read_text(encoding='utf-8')\n"
            "old = payload['old']\n"
            "new = payload['new']\n"
            "count = text.count(old)\n"
            "if count == 0:\n"
            "    print('Error: String not found in file')\n"
            "    sys.exit(1)\n"
            "if count > 1 and not payload.get('replace_all'):\n"
            "    print('Error: String appears multiple times. Use replace_all=True to replace all occurrences.')\n"
            "    sys.exit(2)\n"
            "path.write_text(text.replace(old, new, -1 if payload.get('replace_all') else 1), encoding='utf-8')\n"
            "print(count if payload.get('replace_all') else 1)\n"
            "PY"
        )
        result = await self.aexecute(command)
        output = result.output.strip()
        if result.exit_code != 0:
            return EditResult(error=output or f"Error editing file '{file_path}'")
        try:
            occurrences = int(output.splitlines()[-1])
        except (ValueError, IndexError):
            occurrences = None
        return EditResult(path=file_path, files_update=None, occurrences=occurrences)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return asyncio.run(self.aedit(file_path, old_string, new_string, replace_all))

    async def als_info(self, path: str) -> list[FileInfo]:
        try:
            result = await self._call("list", {"path": path})
            entries = result.get("entries", [])
            if not isinstance(entries, list):
                return []
            infos: list[FileInfo] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_path = entry.get("path")
                if not isinstance(entry_path, str):
                    continue
                info: FileInfo = {"path": entry_path}
                if "is_dir" in entry:
                    info["is_dir"] = bool(entry["is_dir"])
                if isinstance(entry.get("size"), int):
                    info["size"] = int(entry["size"])
                if isinstance(entry.get("modified_at"), str):
                    info["modified_at"] = entry["modified_at"]
                infos.append(info)
            return infos
        except ClientSandboxRouterError as e:
            return [{"path": f"Error: {e.message}", "is_dir": False}]

    def ls_info(self, path: str) -> list[FileInfo]:
        return asyncio.run(self.als_info(path))

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        payload = {"pattern": pattern, "path": path}
        payload_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        command = (
            "python3 - <<'PY'\n"
            "import base64, glob, json, os\n"
            f"payload = json.loads(base64.b64decode({payload_b64!r}).decode('utf-8'))\n"
            "base = payload.get('path') or '/'\n"
            "pattern = payload.get('pattern') or '*'\n"
            "search = pattern if os.path.isabs(pattern) else os.path.join(base, pattern)\n"
            "for match in glob.glob(search, recursive=True):\n"
            "    try:\n"
            "        st = os.stat(match)\n"
            "        print(json.dumps({'path': match, 'is_dir': os.path.isdir(match), 'size': int(st.st_size)}))\n"
            "    except OSError:\n"
            "        pass\n"
            "PY"
        )
        result = await self.aexecute(command)
        if result.exit_code != 0:
            return []
        matches: list[FileInfo] = []
        for line in result.output.splitlines():
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and isinstance(data.get("path"), str):
                matches.append(data)
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return asyncio.run(self.aglob_info(pattern, path))

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        search_path = shlex.quote(path or ".")
        pattern_arg = shlex.quote(pattern)
        glob_arg = f" --include={shlex.quote(glob)}" if glob else ""
        command = f"grep -rHnF{glob_arg} -e {pattern_arg} {search_path} 2>/dev/null || true"
        result = await self.aexecute(command)
        if result.exit_code not in (0, None):
            return result.output
        matches: list[GrepMatch] = []
        for line in result.output.splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue
            try:
                line_number = int(parts[1])
            except ValueError:
                continue
            matches.append({"path": parts[0], "line": line_number, "text": parts[2]})
        return matches

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        return asyncio.run(self.agrep_raw(pattern, path, glob))

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                result = await self._call(
                    "upload_file",
                    {
                        "path": path,
                        "content_base64": base64.b64encode(content).decode("ascii"),
                    },
                )
                error = result.get("error")
                responses.append(file_upload_response(path=path, error=error))
            except ClientSandboxRouterError:
                responses.append(file_upload_response(path=path, error="file_not_found"))
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return asyncio.run(self.aupload_files(files))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                result = await self._call("download_file", {"path": path})
                encoded = result.get("content_base64")
                content = base64.b64decode(encoded) if isinstance(encoded, str) else None
                responses.append(
                    file_download_response(
                        path=path,
                        content=content,
                        error=result.get("error"),
                    )
                )
            except ClientSandboxRouterError:
                responses.append(file_download_response(path=path, error="file_not_found"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return asyncio.run(self.adownload_files(paths))

"""Exercise real composite routing, including implicit fan-out and transfer entrypoints."""

import json
from unittest.mock import AsyncMock

import pytest
from deepagents.backends.protocol import (
    BackendProtocol,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    ReadResult,
    WriteResult,
)

from src.infra.auth import tool_authority
from src.infra.backend.deepagent import create_persistent_backend
from src.kernel.schemas.user import TokenPayload


class _Files(BackendProtocol):
    def __init__(self):
        self.calls = []

    async def awrite(self, file_path, content):
        self.calls.append(("write", file_path))
        return WriteResult(path=file_path)

    async def aread(self, file_path, offset=0, limit=2000):
        self.calls.append(("read", file_path))
        return ReadResult(error="file_not_found")

    async def agrep(self, pattern, path=None, glob=None, *, max_count=None):
        self.calls.append(("grep", path))
        return GrepResult(matches=[])

    async def aglob(self, pattern, path=None):
        self.calls.append(("glob", path))
        return GlobResult(matches=[])

    async def adownload_files(self, paths):
        self.calls.extend(("download", path) for path in paths)
        return [FileDownloadResponse(path=path, content=b"private") for path in paths]

    async def aupload_files(self, files):
        self.calls.extend(("upload", path) for path, _ in files)
        return [FileUploadResponse(path=path) for path, _ in files]


def _backend(monkeypatch, permissions):
    current = AsyncMock(
        return_value=TokenPayload(
            sub="owner", username="owner", roles=["role"], permissions=permissions
        )
    )
    monkeypatch.setattr(tool_authority, "resolve_tool_user", current)
    backend = create_persistent_backend("search", user_id="owner", session_id="session")
    default, skills, memories = _Files(), _Files(), _Files()
    backend.default = default
    backend.routes = {"/skills/": skills, "/memories/": memories}
    backend.sorted_routes = list(backend.routes.items())
    return backend, default, skills, memories, current


async def test_no_sandbox_composite_denies_skill_write_before_storage(monkeypatch):
    backend, default, skills, _, _ = _backend(monkeypatch, ["chat:write", "skill:read"])
    result = await backend.awrite("/skills/private/SKILL.md", "change")
    assert result.error and "permission" in result.error.lower()
    assert not skills.calls and not default.calls


@pytest.mark.parametrize("method,args", [("agrep", ("private",)), ("aglob", ("**/*",))])
async def test_root_search_does_not_read_unauthorized_mounts(monkeypatch, method, args):
    backend, default, skills, memories, _ = _backend(monkeypatch, ["file:read", "sandbox:read"])
    result = await getattr(backend, method)(*args)
    assert result.error and "permission" in result.error.lower()
    assert not skills.calls and not memories.calls and not default.calls


async def test_transfer_does_not_bypass_skill_source_read_permission(monkeypatch):
    from src.infra.tool import transfer_file_tool

    backend, default, skills, _, _ = _backend(monkeypatch, ["file:read", "file:upload:document"])
    monkeypatch.setattr(transfer_file_tool, "get_backend_from_runtime", lambda _: backend)
    result = json.loads(
        await transfer_file_tool.transfer_file.coroutine(
            "/skills/private/SKILL.md", "/workflow/session/copied.md"
        )
    )
    assert not result["success"]
    assert not skills.calls and not default.calls


async def test_download_checks_every_path_before_any_backend_io(monkeypatch):
    backend, default, skills, _, _ = _backend(monkeypatch, ["file:read"])
    result = await backend.adownload_files(
        ["/workflow/session/report.md", "/skills/private/SKILL.md"]
    )
    assert any(item.error for item in result)
    assert not default.calls and not skills.calls


async def test_backend_rechecks_revoked_permission_after_prior_success(monkeypatch):
    backend, _, skills, _, current = _backend(monkeypatch, ["skill:write"])
    assert not (await backend.awrite("/skills/own/a.md", "first")).error
    current.return_value = TokenPayload(sub="owner", username="owner", permissions=[])
    assert (await backend.awrite("/skills/own/b.md", "second")).error
    assert skills.calls == [("write", "/own/a.md")]


async def test_trusted_evidence_write_is_exact_and_does_not_authorize_other_paths(monkeypatch):
    from src.infra.backend.resource_authority import trusted_backend_io

    backend, default, skills, _, _ = _backend(monkeypatch, [])
    evidence = _Files()
    backend.routes["/evidence/"] = evidence
    backend.sorted_routes = list(backend.routes.items())
    path = "/evidence/observation.json"
    assert (await backend.awrite(path, "forged")).error
    with trusted_backend_io(backend, path):
        assert not (await backend.awrite(path, "server observation")).error
        assert (await backend.awrite("/workflow/session/user.md", "no grant")).error
        assert (await backend.awrite("/skills/own/SKILL.md", "no grant")).error
    assert (await backend.awrite(path, "forged later")).error
    assert evidence.calls == [("write", "/observation.json")]
    assert not skills.calls and not default.calls


async def test_server_artifact_sidecar_does_not_grant_model_file_write(monkeypatch):
    from src.infra.backend.resource_authority import server_artifact_backend

    backend, default, skills, _, _ = _backend(monkeypatch, [])
    sidecar = server_artifact_backend(backend)
    path = "/conversation_history/server.md"
    assert not (await sidecar.awrite(path, "history")).error
    assert (await backend.awrite(path, "model overwrite")).error
    with pytest.raises(ValueError):
        await sidecar.awrite("/skills/own/SKILL.md", "not an artifact")
    assert default.calls == [("write", path)]
    assert not skills.calls


@pytest.mark.parametrize("sync", [False, True])
@pytest.mark.parametrize(
    "download_result,allowed",
    [
        ("nonempty", False),
        ("binary", False),
        ("error", False),
        ("exception", False),
        ("no_response", False),
        ("no_content", False),
        ("empty", True),
        ("missing", True),
    ],
)
async def test_server_history_download_only_allows_whole_write_for_known_empty_or_missing_file(
    monkeypatch, sync, download_result, allowed
):
    import asyncio

    from src.infra.backend.resource_authority import server_artifact_backend

    backend, default, *_ = _backend(monkeypatch, [])
    sidecar = server_artifact_backend(backend)
    path = "/conversation_history/server.md"
    result = FileDownloadResponse(
        path=path,
        content={"nonempty": b"existing history", "binary": b"\xff", "empty": b""}.get(
            download_result
        ),
        error={"error": "io_error", "missing": "file_not_found"}.get(download_result),
    )
    default.adownload_files = AsyncMock(
        return_value=[] if download_result == "no_response" else [result],
        side_effect=RuntimeError("download unavailable")
        if download_result == "exception"
        else None,
    )
    try:
        if sync:
            await asyncio.to_thread(sidecar.download_files, [path])
        else:
            await sidecar.adownload_files([path])
    except RuntimeError:
        assert download_result == "exception"

    written = (
        await asyncio.to_thread(sidecar.write, path, "new history")
        if sync
        else await sidecar.awrite(path, "new history")
    )
    assert bool(written.error) is not allowed
    assert (("write", path) in default.calls) is allowed


async def test_internal_eviction_uses_sidecar_without_changing_tool_backend(monkeypatch):
    from src.infra.backend.resource_authority import protect_server_artifact_eviction

    backend, default, _, _, _ = _backend(monkeypatch, [])

    class Eviction:
        async def _aevict_and_truncate_messages(self, path):
            return await self.backend.awrite(path, "history")

    middleware = Eviction()
    middleware.backend = backend
    protect_server_artifact_eviction(middleware)
    assert not (
        await middleware._aevict_and_truncate_messages("/conversation_history/server.md")
    ).error
    assert middleware.backend is backend
    assert (await middleware.backend.awrite("/conversation_history/model.md", "no grant")).error
    assert default.calls == [("write", "/conversation_history/server.md")]


@pytest.mark.parametrize("path", ["/skills/own/SKILL.md", "/memories/private.md"])
def test_server_scope_cannot_trust_personal_resource_mounts(monkeypatch, path):
    from src.infra.backend.resource_authority import trusted_backend_io

    backend, *_ = _backend(monkeypatch, [])
    with pytest.raises(ValueError):
        with trusted_backend_io(backend, path):
            pass


async def test_server_handoff_writer_retains_exact_path_permission(monkeypatch):
    from src.infra.agent.middleware.main_agent_context import write_subagent_handoff_file

    backend, default, _, _, _ = _backend(monkeypatch, [])
    result = await write_subagent_handoff_file(
        backend,
        dirname="main_agent_context",
        filename="handoff.md",
        content="server context",
        log_context="test",
    )
    assert result == "/main_agent_context/handoff.md"
    assert default.calls == [("write", result)]
    assert (await backend.awrite(result, "model overwrite")).error


def test_summary_sidecar_preserves_composite_artifacts_root(monkeypatch):
    from deepagents.backends import CompositeBackend
    from deepagents.middleware.summarization import SummarizationMiddleware
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from src.infra.backend.resource_authority import server_artifact_backend

    backend, *_ = _backend(monkeypatch, [])
    backend.artifacts_root = "/workspace/session"
    sidecar = server_artifact_backend(backend)
    assert isinstance(sidecar, CompositeBackend)
    assert sidecar.artifacts_root == backend.artifacts_root
    summary = SummarizationMiddleware(
        model=FakeListChatModel(responses=["summary"]), backend=sidecar
    )
    assert summary._history_path_prefix == "/workspace/session/conversation_history"


async def test_actual_large_tool_result_eviction_uses_limited_sidecar(monkeypatch):
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain_core.messages import ToolMessage

    from src.infra.backend.resource_authority import protect_server_artifact_eviction

    backend, default, skills, _, _ = _backend(monkeypatch, [])
    backend.artifacts_root = "/workspace/session"
    middleware = protect_server_artifact_eviction(
        FilesystemMiddleware(
            backend=backend,
            tool_token_limit_before_evict=1,
        )
    )
    message = ToolMessage(content="Long result " * 1000, tool_call_id="tool-call")
    processed, evicted = await middleware._aprocess_large_message(message, backend)
    path = "/workspace/session/large_tool_results/tool-call"
    assert evicted
    assert path in str(processed.content)
    assert default.calls == [("write", path)]
    assert middleware.backend is backend
    assert (await backend.awrite(path, "model cannot overwrite")).error
    assert not skills.calls

"""Exercise cloud-style guarded commits against a real temporary filesystem."""

import subprocess
from pathlib import Path

import pytest
from deepagents.backends.utils import create_file_data

from src.infra.backend.protocol_compat import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    ReadResult,
    file_download_response,
    file_upload_response,
)


class FilesystemBackend:
    id = "test-cloud"
    env_vars = {}

    def __init__(self, root):
        self.work_dir = str(root)

    async def aexecute(self, command, **kwargs):
        result = subprocess.run(
            command, shell=True, cwd=self.work_dir, capture_output=True, text=True
        )
        return ExecuteResponse(output=result.stdout + result.stderr, exit_code=result.returncode)

    async def aread(self, path, offset=0, limit=2000):
        content = Path(path).read_text()
        return ReadResult(file_data=create_file_data(content))

    async def aupload_files(self, files):
        results = []
        for path, content in files:
            Path(path).write_bytes(content)
            results.append(file_upload_response(path=path))
        return results

    async def aedit(self, path, old, new, replace_all=False):
        target = Path(path)
        text = target.read_text()
        target.write_text(text.replace(old, new))
        return EditResult(path=path, occurrences=text.count(old))

    async def adelete(self, path):
        Path(path).unlink()
        return DeleteResult(path=path)

    async def adownload_files(self, paths):
        return [file_download_response(path=p, content=Path(p).read_bytes()) for p in paths]


async def test_cloud_guard_preserves_old_bytes_and_rejects_stale_write(tmp_path):
    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    target = tmp_path / "report.txt"
    target.write_text("original report")
    first = GuardedSandboxBackend(FilesystemBackend(tmp_path), user_id="u1", session_id="a")
    second = GuardedSandboxBackend(FilesystemBackend(tmp_path), user_id="u1", session_id="b")
    assert (await first.aread(str(target))).error is None
    assert (await second.aread(str(target))).error is None
    assert (await first.awrite(str(target), "first report")).error is None
    result = await second.awrite(str(target), "second report")
    assert result.error and "file_conflict" in result.error
    assert target.read_text() == "first report"
    assert any(
        p.read_bytes() == b"original report"
        for p in (tmp_path.parent / ".lambchat-file-history").glob("snapshots/*.blob")
    )


@pytest.mark.parametrize("operation", ["edit", "delete", "upload"])
async def test_cloud_all_mutations_refuse_stale_file(tmp_path, operation):
    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    target = tmp_path / "report.txt"
    target.write_text("original report")
    backend = GuardedSandboxBackend(FilesystemBackend(tmp_path), user_id="u1", session_id="a")
    await backend.aread(str(target))
    target.write_text("other report")
    if operation == "edit":
        result = await backend.aedit(str(target), "report", "document")
    elif operation == "delete":
        result = await backend.adelete(str(target))
    else:
        result = (await backend.aupload_files([(str(target), b"replacement")]))[0]
    assert result.error and "file_conflict" in result.error
    assert target.read_text() == "other report"


async def test_cloud_write_does_not_download_old_file_through_server(tmp_path):
    from unittest.mock import AsyncMock

    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    target = tmp_path / "report.txt"
    target.write_text("original")
    raw = FilesystemBackend(tmp_path)
    raw.adownload_files = AsyncMock(side_effect=AssertionError("cross-network backup"))
    backend = GuardedSandboxBackend(raw, user_id="u1", session_id="a")
    await backend.aread(str(target))
    result = await backend.awrite(str(target), "replacement")
    assert result.error is None
    raw.adownload_files.assert_not_awaited()


async def test_cloud_listing_preserves_observed_versions_and_provider_behavior(tmp_path):
    from unittest.mock import AsyncMock

    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    raw = FilesystemBackend(tmp_path)
    raw.als = AsyncMock(return_value="provider-listing")
    backend = GuardedSandboxBackend(raw, user_id="u1", session_id="a")
    backend._versions["file"] = "observed"
    assert await backend.als(".") == "provider-listing"
    assert backend._versions == {"file": "observed"}


async def test_internal_file_rpc_preserves_runtime_recovery_notice(tmp_path):
    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    class RecoveredBackend(FilesystemBackend):
        notice = "Previous workspace recovered from persistent storage."

        async def aexecute(self, command, **kwargs):
            result = await super().aexecute(command, **kwargs)
            if self.notice:
                result.output = self.notice + "\\n" + result.output
                self.notice = ""
            return result

    target = tmp_path / "report.txt"
    target.write_text("original")
    backend = GuardedSandboxBackend(RecoveredBackend(tmp_path), user_id="u1", session_id="a")
    assert (await backend.aread(str(target))).error is None
    result = await backend.aexecute("printf done")
    assert "Previous workspace recovered" in result.output
    assert "done" in result.output


async def test_failed_cloud_upload_removes_only_its_staging_file(tmp_path):
    from src.infra.backend.guarded_sandbox import GuardedSandboxBackend

    class FailedUpload(FilesystemBackend):
        async def aupload_files(self, files):
            await super().aupload_files(files)
            return [file_upload_response(path=path, error="upload_failed") for path, _ in files]

    target = tmp_path / "report.txt"
    target.write_text("original")
    keep = tmp_path / ".lambchat-cloud-user-file"
    keep.write_text("keep")
    backend = GuardedSandboxBackend(FailedUpload(tmp_path), user_id="u1", session_id="a")
    await backend.aread(str(target))
    result = await backend.awrite(str(target), "replacement")
    assert result.error
    assert target.read_text() == "original"
    assert list(tmp_path.glob(".lambchat-cloud-*")) == [keep]

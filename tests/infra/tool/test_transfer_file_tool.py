import json
from types import SimpleNamespace

import pytest
from deepagents.backends.protocol import LsResult

from src.infra.tool import transfer_file_tool


class _Runtime:
    def __init__(self, backend: object) -> None:
        self.config = {"configurable": {"backend": backend}}


@pytest.mark.asyncio
async def test_transfer_path_reports_structured_ls_error_as_failure() -> None:
    class _FailedBackend:
        async def als(self, path: str) -> LsResult:
            return LsResult(error=f"storage unavailable for {path}")

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir="/workspace/project",
            target_prefix="/tmp/",
            runtime=_Runtime(_FailedBackend()),
        )
    )

    assert result["success"] is False
    assert "storage unavailable" in result["error"]


@pytest.mark.asyncio
async def test_transfer_path_stops_listing_after_file_limit() -> None:
    root = "/workspace/huge"
    first_dir = f"{root}/first"
    second_dir = f"{root}/second"
    limit = transfer_file_tool.MAX_BATCH_FILES

    class _FakeBackend:
        def __init__(self) -> None:
            self.listed: list[str] = []

        async def als(self, path: str):
            self.listed.append(path)
            if path == root:
                return SimpleNamespace(
                    entries=[
                        {"path": first_dir, "is_dir": True},
                        {"path": second_dir, "is_dir": True},
                    ]
                )
            if path == first_dir:
                return SimpleNamespace(
                    entries=[
                        {"path": f"{first_dir}/file-{index}.txt", "is_dir": False}
                        for index in range(limit + 1)
                    ]
                )
            if path == second_dir:
                raise AssertionError("listing should stop once the file limit is exceeded")
            return SimpleNamespace(entries=[])

    backend = _FakeBackend()

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/tmp/",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is False
    assert "too many files" in result["error"]
    assert second_dir not in backend.listed


@pytest.mark.asyncio
async def test_transfer_path_limits_returned_file_details() -> None:
    root = "/workspace/project"
    limit = transfer_file_tool.TRANSFER_PATH_RESULT_FILE_LIMIT

    class _FakeBackend:
        async def als(self, path: str):
            assert path == root
            return SimpleNamespace(
                entries=[
                    {"path": f"{root}/file-{index}.txt", "is_dir": False}
                    for index in range(limit + 25)
                ]
            )

        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(content=b"hello", error=None) for _path in paths]

        async def aupload_files(self, files: list[tuple[str, bytes]]):
            return [SimpleNamespace(error=None) for _path, _content in files]

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/tmp/",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == limit + 25
    assert len(result["files"]) == limit
    assert result["files_omitted"] == 25


@pytest.mark.asyncio
async def test_transfer_path_offloads_final_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = "/workspace/project"
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    class _FakeBackend:
        async def als(self, path: str):
            assert path == root
            return SimpleNamespace(entries=[{"path": f"{root}/file.txt", "is_dir": False}])

        async def adownload_files(self, paths: list[str]):
            assert paths == [f"{root}/file.txt"]
            return [SimpleNamespace(content=b"hello", error=None)]

        async def aupload_files(self, files: list[tuple[str, bytes]]):
            assert files == [("/tmp/project/file.txt", b"hello")]
            return [SimpleNamespace(error=None)]

    monkeypatch.setattr(transfer_file_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/tmp/",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result["success"] is True
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_transfer_file_offloads_error_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(transfer_file_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await transfer_file_tool.transfer_file.coroutine(
            source_path="/workspace/file.txt",
            target_path="/tmp/secret.txt",
            runtime=None,
        )
    )

    assert result["success"] is False
    assert "backend not available" in result["error"]
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_transfer_path_offloads_error_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(transfer_file_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir="/skills/MySkill/",
            target_prefix="/skills/",
            runtime=_Runtime(object()),
        )
    )

    assert result["success"] is False
    assert "same backend" in result["error"]
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_transfer_file_rejects_known_oversize_file_before_download() -> None:
    source_path = "/workspace/huge.txt"

    class _FakeBackend:
        def __init__(self) -> None:
            self.download_called = False

        async def aget_file_size(self, path: str) -> int:
            assert path == source_path
            return transfer_file_tool.MAX_FILE_SIZE + 1

        async def adownload_files(self, paths: list[str]):
            self.download_called = True
            raise AssertionError("oversized file should not be downloaded")

    backend = _FakeBackend()

    result = json.loads(
        await transfer_file_tool.transfer_file.coroutine(
            source_path=source_path,
            target_path="/tmp/huge.txt",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is False
    assert "file too large" in result["error"]
    assert backend.download_called is False


@pytest.mark.asyncio
async def test_transfer_path_skips_known_oversize_file_before_download() -> None:
    root = "/workspace/project"
    huge_path = f"{root}/huge.txt"

    class _FakeBackend:
        def __init__(self) -> None:
            self.downloaded: list[str] = []

        async def als(self, path: str):
            assert path == root
            return SimpleNamespace(
                entries=[
                    {
                        "path": huge_path,
                        "is_dir": False,
                        "size": transfer_file_tool.MAX_FILE_SIZE + 1,
                    }
                ]
            )

        async def adownload_files(self, paths: list[str]):
            self.downloaded.extend(paths)
            raise AssertionError("oversized file should not be downloaded")

    backend = _FakeBackend()

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/tmp/",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == 0
    assert result["skipped"] == 1
    assert "file too large" in result["files"][0]["error"]
    assert backend.downloaded == []


@pytest.mark.asyncio
async def test_transfer_path_skips_known_batch_oversize_before_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transfer_file_tool, "MAX_FILE_SIZE", 10)
    monkeypatch.setattr(transfer_file_tool, "MAX_BATCH_SIZE", 15)
    root = "/workspace/project"
    first_path = f"{root}/first.txt"
    second_path = f"{root}/second.txt"

    class _FakeBackend:
        def __init__(self) -> None:
            self.downloaded: list[str] = []

        async def als(self, path: str):
            assert path == root
            return SimpleNamespace(
                entries=[
                    {"path": first_path, "is_dir": False, "size": 10},
                    {"path": second_path, "is_dir": False, "size": 10},
                ]
            )

        async def adownload_files(self, paths: list[str]):
            self.downloaded.extend(paths)
            return [SimpleNamespace(content=b"x" * 10, error=None) for _path in paths]

        async def aupload_files(self, files: list[tuple[str, bytes]]):
            return [SimpleNamespace(error=None) for _path, _content in files]

    backend = _FakeBackend()

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/tmp/",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == 1
    assert result["skipped"] == 1
    assert "batch size limit exceeded" in result["files"][1]["error"]
    assert backend.downloaded == [first_path]

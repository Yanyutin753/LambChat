import asyncio
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


@pytest.mark.asyncio
async def test_transfer_path_moves_501_file_tree_in_one_call() -> None:
    """/skills 全量搬运场景（2026-09-09 生产会话）：501 个文件刚好卡死 500 上限。

    上限抬高后，此类整树搬运应单次调用完成，而不是要求 agent 手工分批。
    """

    root = "/skills/all"
    file_count = 501

    class _FakeBackend:
        async def als(self, path: str) -> LsResult:
            assert path == root
            return LsResult(
                entries=[
                    {"path": f"{root}/file-{index}.txt", "is_dir": False, "size": 3}
                    for index in range(file_count)
                ]
            )

        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(content=b"abc", error=None) for _path in paths]

        async def aupload_files(self, files: list[tuple[str, bytes]]):
            return [SimpleNamespace(error=None) for _path, _content in files]

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/workspace/backup/",
            runtime=_Runtime(_FakeBackend()),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == file_count
    assert result["failed"] == 0


def test_transfer_tools_document_persistent_shared_dir_convention() -> None:
    """工具描述写明持久共享目录约定：可复用文件进 /workspace/.shared，先 ls 复用避免重复转移。"""
    file_doc = transfer_file_tool.get_transfer_file_tool().description or ""
    path_doc = transfer_file_tool.get_transfer_path_tool().description or ""

    for doc in (file_doc, path_doc):
        assert "/workspace/.shared" in doc
        assert "persist" in doc
        assert "`ls`" in doc

    target_hint = transfer_file_tool.get_transfer_path_tool().args["target_prefix"]["description"]
    assert "/workspace/.shared/" in target_hint


@pytest.mark.asyncio
async def test_transfer_file_retries_once_on_transient_upload_failure() -> None:
    """上传瞬时失败（upload_failed/io_error 等非确定性错误）重试一次即成功。

    2026-09-06 生产事故的衍生加固：中继/SDK 抖动导致的单次上传失败不应
    直接判死整个文件转移。
    """

    class _FlakyBackend:
        def __init__(self) -> None:
            self.upload_attempts = 0
            self.downloaded: list[str] = []

        async def aget_file_size(self, path: str):
            return 3

        async def adownload_files(self, paths):
            self.downloaded.extend(paths)
            return [SimpleNamespace(path=paths[0], content=b"abc", error=None)]

        async def aupload_files(self, files):
            self.upload_attempts += 1
            if self.upload_attempts == 1:
                return [SimpleNamespace(path=files[0][0], content=None, error="upload_failed")]
            return [SimpleNamespace(path=files[0][0], content=None, error=None)]

    backend = _FlakyBackend()
    result = json.loads(
        await transfer_file_tool.transfer_file.coroutine(
            source_path="/skills/demo/SKILL.md",
            target_path="/workspace/w1/SKILL.md",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is True
    assert backend.upload_attempts == 2


@pytest.mark.asyncio
async def test_transfer_file_does_not_retry_deterministic_upload_error() -> None:
    """确定性失败（permission_denied 等）不重试——重试只会浪费一轮往返。"""

    class _DeniedBackend:
        def __init__(self) -> None:
            self.upload_attempts = 0

        async def aget_file_size(self, path: str):
            return 3

        async def adownload_files(self, paths):
            return [SimpleNamespace(path=paths[0], content=b"abc", error=None)]

        async def aupload_files(self, files):
            self.upload_attempts += 1
            return [SimpleNamespace(path=files[0][0], content=None, error="permission_denied")]

    backend = _DeniedBackend()
    result = json.loads(
        await transfer_file_tool.transfer_file.coroutine(
            source_path="/skills/demo/SKILL.md",
            target_path="/workspace/w1/SKILL.md",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is False
    assert "permission_denied" in result["error"]
    assert backend.upload_attempts == 1


@pytest.mark.asyncio
async def test_transfer_path_retries_transient_upload_failure_per_file() -> None:
    class _FlakyOnceBackend:
        def __init__(self) -> None:
            self.upload_attempts: dict[str, int] = {}

        async def als(self, path: str) -> LsResult:
            if path == "/skills/demo":
                return LsResult(
                    entries=[{"path": "/skills/demo/a.txt", "is_dir": False, "size": 3}]
                )
            return LsResult(entries=[])

        async def adownload_files(self, paths):
            return [SimpleNamespace(path=paths[0], content=b"abc", error=None)]

        async def aupload_files(self, files):
            target = files[0][0]
            self.upload_attempts[target] = self.upload_attempts.get(target, 0) + 1
            if self.upload_attempts[target] == 1:
                return [SimpleNamespace(path=target, content=None, error="upload_failed")]
            return [SimpleNamespace(path=target, content=None, error=None)]

    backend = _FlakyOnceBackend()
    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir="/skills/demo",
            target_prefix="/workspace/w1/",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_download_from_backend_returns_empty_file_content() -> None:
    """空文件（content=b""）是合法内容，不得误判为缺失后落入同步 fallback。"""

    class _EmptyFileBackend:
        def __init__(self) -> None:
            self.sync_download_called = False

        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(content=b"", error=None)]

        def download_files(self, paths: list[str]):
            self.sync_download_called = True
            raise RuntimeError("sync fallback must not run when async path succeeded")

    backend = _EmptyFileBackend()
    content = await transfer_file_tool._download_from_backend(backend, "/skills/demo/__init__.py")

    assert content == b""
    assert backend.sync_download_called is False


@pytest.mark.asyncio
async def test_transfer_path_transfers_empty_file_instead_of_skipping() -> None:
    class _EmptyFileBackend:
        async def als(self, path: str) -> LsResult:
            if path == "/skills/demo":
                return LsResult(entries=[{"path": "/skills/demo/__init__.py", "is_dir": False}])
            return LsResult(entries=[])

        async def adownload_files(self, paths):
            return [SimpleNamespace(content=b"", error=None)]

        async def aupload_files(self, files):
            return [SimpleNamespace(error=None) for _f in files]

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir="/skills/demo",
            target_prefix="/workspace/w1/",
            runtime=_Runtime(_EmptyFileBackend()),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == 1
    assert result["skipped"] == 0
    assert result["files"][0]["size"] == 0


@pytest.mark.asyncio
async def test_transfer_path_transfers_files_concurrently() -> None:
    """多文件目录并发下载：串行实现会在栅栏处超时失败。"""
    root = "/skills/big"
    need = 4

    class _ConcurrentBackend:
        def __init__(self) -> None:
            self.in_flight = 0
            self.max_in_flight = 0
            self.gate = asyncio.Event()

        async def als(self, path: str) -> LsResult:
            if path == root:
                return LsResult(
                    entries=[
                        {"path": f"{root}/file-{index}.txt", "is_dir": False}
                        for index in range(need)
                    ]
                )
            return LsResult(entries=[])

        async def adownload_files(self, paths):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            if self.in_flight >= need:
                self.gate.set()
            try:
                await asyncio.wait_for(self.gate.wait(), timeout=5)
            finally:
                self.in_flight -= 1
            return [SimpleNamespace(content=b"data", error=None)]

        async def aupload_files(self, files):
            return [SimpleNamespace(error=None) for _f in files]

    backend = _ConcurrentBackend()
    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/workspace/w1/",
            runtime=_Runtime(backend),
        )
    )

    assert result["success"] is True
    assert result["transferred"] == need
    assert result["failed"] == 0
    assert result["skipped"] == 0
    assert backend.max_in_flight >= need


@pytest.mark.asyncio
async def test_transfer_path_preserves_result_order_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = "/skills/ordered"
    count = 6

    class _StaggeredBackend:
        def __init__(self) -> None:
            self.download_delay = {f"{root}/file-{i}.txt": 0.02 * (count - i) for i in range(count)}

        async def als(self, path: str) -> LsResult:
            if path == root:
                return LsResult(
                    entries=[
                        {"path": f"{root}/file-{index}.txt", "is_dir": False}
                        for index in range(count)
                    ]
                )
            return LsResult(entries=[])

        async def adownload_files(self, paths):
            await asyncio.sleep(self.download_delay[paths[0]])
            return [SimpleNamespace(content=b"x", error=None)]

        async def aupload_files(self, files):
            return [SimpleNamespace(error=None) for _f in files]

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/workspace/w1/",
            runtime=_Runtime(_StaggeredBackend()),
        )
    )

    assert [entry["file"] for entry in result["files"]] == [
        f"{root}/file-{index}.txt" for index in range(count)
    ]


@pytest.mark.asyncio
async def test_transfer_path_enforces_batch_budget_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下载完成后才知道大小的文件也要受 MAX_BATCH_SIZE 约束（锁内原子配额）。"""
    monkeypatch.setattr(transfer_file_tool, "MAX_BATCH_SIZE", 10)
    root = "/skills/budget"
    count = 3

    class _UnknownSizeBackend:
        async def als(self, path: str) -> LsResult:
            if path == root:
                return LsResult(
                    entries=[
                        {"path": f"{root}/file-{index}.txt", "is_dir": False}
                        for index in range(count)
                    ]
                )
            return LsResult(entries=[])

        async def adownload_files(self, paths):
            await asyncio.sleep(0.01)
            return [SimpleNamespace(content=b"1234", error=None)]

        async def aupload_files(self, files):
            return [SimpleNamespace(error=None) for _f in files]

    result = json.loads(
        await transfer_file_tool.transfer_path.coroutine(
            source_dir=root,
            target_prefix="/workspace/w1/",
            runtime=_Runtime(_UnknownSizeBackend()),
        )
    )

    assert result["transferred"] == 2
    assert result["skipped"] == 1
    assert result["total_size"] == 8

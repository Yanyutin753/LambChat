from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

from src.api.routes import github
from src.kernel.errors import AppError


class _TrackableChunk(bytearray):
    pass


@pytest.mark.asyncio
async def test_gather_limited_caps_concurrent_work() -> None:
    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def _work(value: int) -> int:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return value

    task = asyncio.create_task(github._gather_limited([lambda i=i: _work(i) for i in range(5)], 2))
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    assert await task == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_fetch_all_files_recursive_rejects_too_many_files_before_fetching_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github, "GITHUB_IMPORT_MAX_FILES", 2)

    async def _fake_dir(owner: str, repo: str, branch: str, path: str = "") -> list[dict]:
        return [
            {"name": "SKILL.md", "type": "file", "path": "skill/SKILL.md"},
            {"name": "a.txt", "type": "file", "path": "skill/a.txt"},
            {"name": "b.txt", "type": "file", "path": "skill/b.txt"},
        ]

    async def _should_not_fetch_file(*args, **kwargs):
        raise AssertionError("file content should not be fetched after file count limit")

    monkeypatch.setattr(github, "fetch_github_dir", _fake_dir)
    monkeypatch.setattr(github, "fetch_github_file", _should_not_fetch_file)

    with pytest.raises(ValueError, match="too many files"):
        await github.fetch_all_files_recursive("owner", "repo", "main", "skill")


@pytest.mark.asyncio
async def test_fetch_all_files_recursive_rejects_known_oversize_before_fetching_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github, "GITHUB_IMPORT_MAX_TOTAL_BYTES", 10)

    async def _fake_dir(owner: str, repo: str, branch: str, path: str = "") -> list[dict]:
        return [
            {
                "name": "huge.txt",
                "type": "file",
                "path": "skill/huge.txt",
                "size": 11,
            }
        ]

    async def _should_not_fetch_file(*args, **kwargs):
        raise AssertionError("known oversized file should not be fetched")

    monkeypatch.setattr(github, "fetch_github_dir", _fake_dir)
    monkeypatch.setattr(github, "fetch_github_file", _should_not_fetch_file)

    with pytest.raises(ValueError, match="content too large"):
        await github.fetch_all_files_recursive("owner", "repo", "main", "skill")


@pytest.mark.asyncio
async def test_fetch_all_files_recursive_rejects_known_total_oversize_before_fetching_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github, "GITHUB_IMPORT_MAX_TOTAL_BYTES", 10)

    async def _fake_dir(owner: str, repo: str, branch: str, path: str = "") -> list[dict]:
        return [
            {"name": "a.txt", "type": "file", "path": "skill/a.txt", "size": 6},
            {"name": "b.txt", "type": "file", "path": "skill/b.txt", "size": 5},
        ]

    async def _should_not_fetch_file(*args, **kwargs):
        raise AssertionError("known total oversized files should not be fetched")

    monkeypatch.setattr(github, "fetch_github_dir", _fake_dir)
    monkeypatch.setattr(github, "fetch_github_file", _should_not_fetch_file)

    with pytest.raises(ValueError, match="content too large"):
        await github.fetch_all_files_recursive("owner", "repo", "main", "skill")


@pytest.mark.asyncio
async def test_fetch_github_file_streams_response_without_materializing_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        status_code = 200

        @property
        def text(self) -> str:
            raise AssertionError("GitHub raw download must stream bytes, not materialize text")

        async def aiter_bytes(self):
            yield "hello ".encode()
            yield "world".encode()

    class _FakeStreamContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, url: str, timeout: float):
            assert method == "GET"
            assert url.endswith("/owner/repo/main/skill/SKILL.md")
            assert timeout == 30.0
            return _FakeStreamContext()

    monkeypatch.setattr(github.httpx, "AsyncClient", lambda: _FakeClient())

    content = await github.fetch_github_file("owner", "repo", "main", "skill/SKILL.md")

    assert content == "hello world"


@pytest.mark.asyncio
async def test_fetch_github_file_releases_download_chunks_between_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_chunk_released_before_second = False
    first_chunk_ref: weakref.ReferenceType[_TrackableChunk]

    class _FakeResponse:
        status_code = 200

        async def aiter_bytes(self):
            nonlocal first_chunk_ref, first_chunk_released_before_second
            first_chunk = _TrackableChunk(b"hello ")
            first_chunk_ref = weakref.ref(first_chunk)
            yield first_chunk
            first_chunk = None
            gc.collect()
            first_chunk_released_before_second = first_chunk_ref() is None
            yield _TrackableChunk(b"world")

    class _FakeStreamContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, url: str, timeout: float):
            return _FakeStreamContext()

    monkeypatch.setattr(github.httpx, "AsyncClient", lambda: _FakeClient())

    content = await github.fetch_github_file("owner", "repo", "main", "skill/SKILL.md")

    assert content == "hello world"
    assert first_chunk_released_before_second is True


@pytest.mark.asyncio
async def test_scan_for_skills_limits_skill_md_preview_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_dir(owner: str, repo: str, branch: str, path: str = "") -> list[dict]:
        assert path == ""
        return [{"name": "skill-a", "type": "dir", "path": "skill-a"}]

    async def _fake_file(
        owner: str,
        repo: str,
        branch: str,
        path: str,
        max_bytes: int | None = None,
    ) -> str:
        assert path == "skill-a/SKILL.md"
        assert max_bytes == github.GITHUB_SKILL_MD_MAX_BYTES
        return "---\nname: skill-a\n---\nSmall enough"

    monkeypatch.setattr(github, "fetch_github_dir", _fake_dir)
    monkeypatch.setattr(github, "fetch_github_file", _fake_file)

    skills = await github.scan_for_skills("owner", "repo", "main")

    assert skills[0]["name"] == "skill-a"


@pytest.mark.asyncio
async def test_scan_for_skills_limits_root_skill_md_preview_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_dir(owner: str, repo: str, branch: str, path: str = "") -> list[dict]:
        assert path == ""
        return [{"name": "SKILL.md", "type": "file", "path": "SKILL.md"}]

    async def _fake_file(
        owner: str,
        repo: str,
        branch: str,
        path: str,
        max_bytes: int | None = None,
    ) -> str:
        assert path == "SKILL.md"
        assert max_bytes == github.GITHUB_SKILL_MD_MAX_BYTES
        return "---\nname: root-skill\n---\nSmall enough"

    monkeypatch.setattr(github, "fetch_github_dir", _fake_dir)
    monkeypatch.setattr(github, "fetch_github_file", _fake_file)

    skills = await github.scan_for_skills("owner", "repo", "main")

    assert skills[0]["name"] == "root-skill"


@pytest.mark.asyncio
async def test_install_github_skills_rejects_too_many_requested_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github, "GITHUB_INSTALL_MAX_SKILLS", 2, raising=False)

    async def _should_not_scan(*args, **kwargs):
        raise AssertionError("oversized install request should not scan GitHub")

    monkeypatch.setattr(github, "scan_for_skills", _should_not_scan)

    with pytest.raises(AppError) as exc:
        await github.install_github_skills(
            github.GitHubInstallRequest(
                repo_url="owner/repo",
                skill_names=["one", "two", "three"],
            ),
            user=type("User", (), {"sub": "user-1"})(),
        )

    assert exc.value.error_code.code == "github_install_limit"
    assert exc.value.http_status == 400
    assert exc.value.args_data == {"max": 2}

from __future__ import annotations

from src.infra.backend.skills_store import SkillsStoreBackend
from src.infra.skill.binary import build_binary_ref_content
from src.infra.skill.storage_helpers import SKILL_EFFECTIVE_LOAD_LIMIT


def _field(value, name: str):
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


class _FakeSkillStorage:
    def __init__(self) -> None:
        self.files = {
            "visible": {
                "SKILL.md": "visible skill",
                "notes.txt": "needle in visible notes",
                "multi.txt": "alpha\nbeta\ngamma\ndelta\n",
            },
            "hidden": {
                "SKILL.md": "hidden skill",
                "notes.txt": "needle in hidden notes",
            },
        }

    async def get_effective_skills(self, user_id: str) -> dict:
        return {
            "skills": {
                name: {
                    "name": name,
                    "description": f"Skill: {name}",
                    "files": files,
                    "enabled": True,
                }
                for name, files in self.files.items()
            }
        }

    async def get_skill_file(self, skill_name: str, file_name: str, user_id: str) -> str | None:
        return self.files.get(skill_name, {}).get(file_name)

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        return list(self.files.get(skill_name, {}).keys())

    async def batch_get_skill_files(self, skill_keys: list[tuple[str, str]]) -> dict:
        return {
            (skill_name, user_id): self.files.get(skill_name, {})
            for skill_name, user_id in skill_keys
        }

    async def get_all_user_skill_names(
        self,
        user_id: str,
        limit: int | None = None,
    ) -> list[str]:
        names = sorted(self.files.keys())
        if limit is not None:
            names = names[:limit]
        return names


class _FakeRuntime:
    def __init__(
        self,
        disabled_skills: list[str] | None = None,
        enabled_skills: list[str] | None = None,
    ) -> None:
        self.config = {
            "configurable": {
                "disabled_skills": disabled_skills,
                "enabled_skills": enabled_skills,
            }
        }


async def test_skills_store_backend_hides_disabled_skills_from_ls_and_read() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=["hidden"])
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]

    visible = await backend.aread("/skills/visible/SKILL.md")
    assert _field(visible, "file_data")["content"] == "visible skill"

    hidden = await backend.aread("/skills/hidden/SKILL.md")
    assert _field(hidden, "error") == "Skill 'hidden' not found"

    hidden_dir = await backend.als("/skills/hidden/")
    assert _field(hidden_dir, "entries") == []


async def test_skills_store_backend_hides_disabled_skills_from_grep_and_glob() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=["hidden"])
    backend._storage = _FakeSkillStorage()

    grep_result = await backend.agrep("needle", "/skills/")
    assert [_field(match, "path") for match in _field(grep_result, "matches")] == [
        "/visible/notes.txt"
    ]

    glob_result = await backend.aglob("*", "/skills/")
    assert [_field(entry, "path") for entry in _field(glob_result, "matches")] == ["/visible/"]


async def test_skills_store_backend_reads_disabled_skills_from_runtime_config() -> None:
    backend = SkillsStoreBackend(user_id="user-1", runtime=_FakeRuntime(["hidden"]))
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]


async def test_skills_store_backend_reads_disabled_skills_from_graph_config(
    monkeypatch,
) -> None:
    from src.infra.backend import skills_store as module

    def fake_get_config():
        return {"configurable": {"disabled_skills": ["hidden"]}}

    monkeypatch.setattr(module, "get_config", fake_get_config, raising=False)
    backend = SkillsStoreBackend(user_id="user-1")
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]


async def test_skills_store_backend_enabled_skills_does_not_gate_file_operations() -> None:
    """enabled_skills 仅用于提示词注入，不限制 SkillsStoreBackend 的文件操作。"""
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=["visible"])
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    # enabled_skills 不再过滤 ls，应能看到所有 skill
    assert [_field(entry, "path") for entry in _field(result, "entries")] == [
        "/hidden/",
        "/visible/",
    ]

    visible = await backend.aread("/skills/visible/SKILL.md")
    assert _field(visible, "file_data")["content"] == "visible skill"

    hidden = await backend.aread("/skills/hidden/SKILL.md")
    assert _field(hidden, "file_data")["content"] == "hidden skill"

    hidden_dir = await backend.als("/skills/hidden/")
    assert _field(hidden_dir, "entries") != []


async def test_skills_store_backend_enabled_skills_does_not_gate_search() -> None:
    """enabled_skills 仅用于提示词注入，不限制 grep/glob 操作。"""
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=["visible"])
    backend._storage = _FakeSkillStorage()

    grep_result = await backend.agrep("needle", "/skills/")
    # enabled_skills 不再过滤搜索，应能搜到所有 skill
    assert [_field(match, "path") for match in _field(grep_result, "matches")] == [
        "/hidden/notes.txt",
        "/visible/notes.txt",
    ]

    glob_result = await backend.aglob("*", "/skills/")
    assert [_field(entry, "path") for entry in _field(glob_result, "matches")] == [
        "/hidden/",
        "/visible/",
    ]


async def test_skills_store_backend_root_grep_scans_skills_incrementally() -> None:
    class _ManySkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files = {f"skill-{index}": {"notes.txt": f"needle-{index}"} for index in range(5)}
            self.batch_sizes: list[int] = []

        async def get_effective_skills(self, user_id: str) -> dict:
            raise AssertionError("root grep should not load every effective skill file at once")

        async def batch_get_skill_files(self, skill_keys: list[tuple[str, str]]) -> dict:
            self.batch_sizes.append(len(skill_keys))
            return await super().batch_get_skill_files(skill_keys)

    storage = _ManySkillStorage()
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = storage

    result = await backend.agrep("needle", "/skills/")

    assert len(_field(result, "matches")) == 5
    assert storage.batch_sizes == [1, 1, 1, 1, 1]


async def test_skills_store_backend_offloads_grep_content_scan(monkeypatch) -> None:
    from src.infra.backend import _skills_search as search_module

    class _BlockingText(str):
        def split(self, sep=None, maxsplit=-1):
            assert getattr(
                search_module,
                "_inside_fake_blocking_io",
                False,
            ), "skill grep content scan must be offloaded"
            return super().split(sep, maxsplit)

    class _LargeSkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files = {
                "visible": {
                    "notes.txt": _BlockingText("needle in visible notes\nother line"),
                }
            }

    async def fake_run_blocking_io(func, *args, **kwargs):
        monkeypatch.setattr(search_module, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(search_module, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(search_module, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(search_module, "_inside_fake_blocking_io", False, raising=False)

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _LargeSkillStorage()

    result = await backend.agrep("needle", "/skills/visible/")

    assert [_field(match, "path") for match in _field(result, "matches")] == ["/visible/notes.txt"]


async def test_skills_store_backend_root_ls_does_not_load_skill_file_contents() -> None:
    class _ManySkillStorage(_FakeSkillStorage):
        async def get_effective_skills(self, user_id: str) -> dict:
            raise AssertionError("root ls should not load every skill file")

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=["hidden"])
    backend._storage = _ManySkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]


async def test_skills_store_backend_root_glob_does_not_load_skill_file_contents() -> None:
    class _ManySkillStorage(_FakeSkillStorage):
        async def get_effective_skills(self, user_id: str) -> dict:
            raise AssertionError("root glob should not load every skill file")

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=["hidden"])
    backend._storage = _ManySkillStorage()

    result = await backend.aglob("*", "/skills/")

    assert [_field(entry, "path") for entry in _field(result, "matches")] == ["/visible/"]


async def test_skills_store_backend_root_operations_limit_skill_name_queries() -> None:
    class _RecordingSkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.limits: list[int | None] = []

        async def get_all_user_skill_names(
            self,
            user_id: str,
            limit: int | None = None,
        ) -> list[str]:
            self.limits.append(limit)
            return await super().get_all_user_skill_names(user_id, limit=limit)

    storage = _RecordingSkillStorage()
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = storage

    await backend.als("/skills/")
    await backend.agrep("needle", "/skills/")
    await backend.aglob("*", "/skills/")

    assert storage.limits == [
        SKILL_EFFECTIVE_LOAD_LIMIT,
        SKILL_EFFECTIVE_LOAD_LIMIT,
        SKILL_EFFECTIVE_LOAD_LIMIT,
    ]


async def test_skills_store_backend_enabled_skills_from_runtime_config_does_not_gate() -> None:
    """runtime config 中的 enabled_skills 也不应限制 SkillsStoreBackend。"""
    backend = SkillsStoreBackend(
        user_id="user-1",
        runtime=_FakeRuntime(enabled_skills=["visible"]),
    )
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    # enabled_skills 不再过滤，应能看到所有 skill
    assert [_field(entry, "path") for entry in _field(result, "entries")] == [
        "/hidden/",
        "/visible/",
    ]


async def test_skills_store_backend_enabled_skills_from_graph_config_does_not_gate(
    monkeypatch,
) -> None:
    from src.infra.backend import skills_store as module

    def fake_get_config():
        return {"configurable": {"enabled_skills": ["visible"]}}

    monkeypatch.setattr(module, "get_config", fake_get_config)
    backend = SkillsStoreBackend(user_id="user-1")
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    # enabled_skills 不再过滤，应能看到所有 skill
    assert [_field(entry, "path") for entry in _field(result, "entries")] == [
        "/hidden/",
        "/visible/",
    ]


async def test_skills_store_backend_empty_enabled_skills_does_not_hide_all() -> None:
    """空 enabled_skills 列表不再隐藏所有 skill（enabled_skills 不限制文件操作）。"""
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    # enabled_skills=[] 不再隐藏所有 skill，应能看到所有
    assert [_field(entry, "path") for entry in _field(result, "entries")] == [
        "/hidden/",
        "/visible/",
    ]


async def test_skills_store_backend_read_reports_offset_past_eof() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.aread("/skills/visible/SKILL.md", offset=400, limit=100)

    assert _field(result, "error") == "Line offset 400 exceeds file length (1 lines)"


async def test_skills_store_backend_read_slices_file_data_for_offset_reads() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.aread("/skills/visible/multi.txt", offset=1, limit=2)

    assert _field(result, "file_data")["content"] == "beta\ngamma\n"
    assert _field(result, "start_line") == 2
    assert _field(result, "end_line") == 3
    assert _field(result, "next_offset") == 3
    assert _field(result, "total_lines") == 4


async def test_skills_store_backend_zero_limit_returns_uninspected_window() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.aread("/skills/visible/multi.txt", offset=0, limit=0)

    assert _field(result, "file_data")["content"] == ""
    assert _field(result, "no_lines_requested") is True
    assert _field(result, "start_line") is None
    assert _field(result, "next_offset") is None


async def test_skills_store_backend_grep_honors_max_count() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.agrep("needle", "/skills/", max_count=1)

    assert len(_field(result, "matches")) == 1
    assert _field(result, "truncated") is True


async def test_skills_store_backend_sync_read_rejects_running_event_loop() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    try:
        backend.read("/skills/visible/SKILL.md")
    except RuntimeError as exc:
        assert "async" in str(exc).lower()
    else:
        raise AssertionError("expected sync read to reject running event loop")


async def test_skills_store_backend_download_files_skips_large_binary_ref(monkeypatch) -> None:
    from src.infra.backend import skills_store as module

    class _FakeBinarySkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files["visible"]["huge.png"] = build_binary_ref_content(
                "skills/user-1/visible/huge.png",
                "image/png",
                64,
            )

    async def fail_get_or_init_storage():
        raise AssertionError("large binary refs should be rejected before S3 download")

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fail_get_or_init_storage,
    )
    monkeypatch.setattr(module, "SKILL_BINARY_DOWNLOAD_MAX_BYTES", 8, raising=False)

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeBinarySkillStorage()

    responses = await backend.adownload_files(["/skills/visible/huge.png"])

    assert len(responses) == 1
    assert _field(responses[0], "content") is None
    assert _field(responses[0], "error") == "file_too_large"


async def test_skills_store_backend_download_files_rejects_too_many_paths(monkeypatch) -> None:
    from src.infra.backend import skills_store as module

    class _StorageShouldNotLoadFiles(_FakeSkillStorage):
        async def batch_get_skill_files(self, skill_keys: list[tuple[str, str]]) -> dict:
            raise AssertionError("too many paths should not batch load skill files")

    monkeypatch.setattr(module, "SKILL_DOWNLOAD_FILES_LIMIT", 2, raising=False)
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _StorageShouldNotLoadFiles()

    responses = await backend.adownload_files(
        [
            "/skills/visible/SKILL.md",
            "/skills/visible/notes.txt",
            "/skills/visible/multi.txt",
        ]
    )

    assert len(responses) == 3
    assert [_field(response, "error") for response in responses] == [
        "too_many_files",
        "too_many_files",
        "too_many_files",
    ]


async def test_skills_store_backend_download_files_spools_binary_ref(monkeypatch) -> None:
    class _FakeBinarySkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files["visible"]["image.png"] = build_binary_ref_content(
                "skills/user-1/visible/image.png",
                "image/png",
                4,
            )

    class _FakeStorageService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def download_file(self, key: str) -> bytes:
            raise AssertionError("binary refs should download into a spool file")

        async def download_to_file(self, key: str, file, *, chunk_size: int = 1024 * 1024) -> int:
            del chunk_size
            self.calls.append(key)
            file.write(b"png!")
            file.seek(0)
            return 4

    fake_storage = _FakeStorageService()

    async def fake_get_or_init_storage():
        return fake_storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeBinarySkillStorage()

    responses = await backend.adownload_files(["/skills/visible/image.png"])

    assert fake_storage.calls == ["skills/user-1/visible/image.png"]
    assert len(responses) == 1
    assert _field(responses[0], "content") == b"png!"
    assert _field(responses[0], "error") is None


async def test_skills_store_backend_offloads_spooled_binary_read(monkeypatch) -> None:
    from src.infra.backend import skills_store as module

    class _FakeBinarySkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files["visible"]["image.png"] = build_binary_ref_content(
                "skills/user-1/visible/image.png",
                "image/png",
                4,
            )

    class _BlockingOnlySpooledFile:
        def __init__(self, *args, **kwargs) -> None:
            self.data = bytearray()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def write(self, data: bytes) -> int:
            self.data.extend(data)
            return len(data)

        def seek(self, position: int) -> int:
            return position

        def read(self) -> bytes:
            if not getattr(module, "_inside_fake_blocking_io", False):
                raise AssertionError("spooled binary reads must run in blocking IO executor")
            return bytes(self.data)

    class _FakeStorageService:
        async def download_to_file(self, key: str, file, *, chunk_size: int = 1024 * 1024) -> int:
            del key, chunk_size
            file.write(b"png!")
            file.seek(0)
            return 4

    async def fake_get_or_init_storage():
        return _FakeStorageService()

    async def fake_run_blocking_io(func, *args, **kwargs):
        monkeypatch.setattr(module, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(module, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(module, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(module, "_inside_fake_blocking_io", False, raising=False)

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeBinarySkillStorage()

    responses = await backend.adownload_files(["/skills/visible/image.png"])

    assert _field(responses[0], "content") == b"png!"
    assert _field(responses[0], "error") is None


async def test_skills_store_backend_rechecks_actual_binary_download_size(monkeypatch) -> None:
    from src.infra.backend import skills_store as module

    class _FakeBinarySkillStorage(_FakeSkillStorage):
        def __init__(self) -> None:
            super().__init__()
            self.files["visible"]["image.png"] = build_binary_ref_content(
                "skills/user-1/visible/image.png",
                "image/png",
                4,
            )

    class _FakeStorageService:
        async def download_to_file(self, key: str, file, *, chunk_size: int = 1024 * 1024) -> int:
            assert key == "skills/user-1/visible/image.png"
            del chunk_size
            file.write(b"x" * 16)
            file.seek(0)
            return 16

    async def fake_get_or_init_storage():
        return _FakeStorageService()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(module, "SKILL_BINARY_DOWNLOAD_MAX_BYTES", 8, raising=False)

    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeBinarySkillStorage()

    responses = await backend.adownload_files(["/skills/visible/image.png"])

    assert len(responses) == 1
    assert _field(responses[0], "content") is None
    assert _field(responses[0], "error") == "file_too_large"

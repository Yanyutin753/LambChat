from __future__ import annotations

import deepagents.backends.protocol as deepagents_protocol

for _missing_name in (
    "EditResult",
    "FileDownloadResponse",
    "FileInfo",
    "FileUploadResponse",
    "GlobResult",
    "GrepMatch",
    "GrepResult",
    "LsResult",
    "ReadResult",
    "WriteResult",
):
    if not hasattr(deepagents_protocol, _missing_name):
        setattr(deepagents_protocol, _missing_name, dict)


from src.infra.backend.skills_store import SkillsStoreBackend


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


async def test_skills_store_backend_limits_root_and_reads_to_enabled_skills() -> None:
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=["visible"])
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]

    visible = await backend.aread("/skills/visible/SKILL.md")
    assert _field(visible, "file_data")["content"] == "visible skill"

    hidden = await backend.aread("/skills/hidden/SKILL.md")
    assert _field(hidden, "error") == "Skill 'hidden' not found"

    hidden_dir = await backend.als("/skills/hidden/")
    assert _field(hidden_dir, "entries") == []


async def test_skills_store_backend_limits_search_to_enabled_skills() -> None:
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=["visible"])
    backend._storage = _FakeSkillStorage()

    grep_result = await backend.agrep("needle", "/skills/")
    assert [_field(match, "path") for match in _field(grep_result, "matches")] == [
        "/visible/notes.txt"
    ]

    glob_result = await backend.aglob("*", "/skills/")
    assert [_field(entry, "path") for entry in _field(glob_result, "matches")] == ["/visible/"]


async def test_skills_store_backend_reads_enabled_skills_from_runtime_config() -> None:
    backend = SkillsStoreBackend(
        user_id="user-1",
        runtime=_FakeRuntime(enabled_skills=["visible"]),
    )
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert [_field(entry, "path") for entry in _field(result, "entries")] == ["/visible/"]


async def test_skills_store_backend_empty_enabled_skills_hides_all_skills() -> None:
    backend = SkillsStoreBackend(user_id="user-1", enabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.als("/skills/")

    assert _field(result, "entries") == []


async def test_skills_store_backend_read_reports_offset_past_eof() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    result = await backend.aread("/skills/visible/SKILL.md", offset=400, limit=100)

    assert _field(result, "error") == "Line offset 400 exceeds file length (1 lines)"


async def test_skills_store_backend_sync_read_rejects_running_event_loop() -> None:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=[])
    backend._storage = _FakeSkillStorage()

    try:
        backend.read("/skills/visible/SKILL.md")
    except RuntimeError as exc:
        assert "async" in str(exc).lower()
    else:
        raise AssertionError("expected sync read to reject running event loop")

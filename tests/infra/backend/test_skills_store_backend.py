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
    def __init__(self, disabled_skills: list[str]) -> None:
        self.config = {"configurable": {"disabled_skills": disabled_skills}}


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

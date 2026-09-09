"""SkillsStoreBackend glob 共享契约（`**` 递归 / 路径相对匹配）测试。

对应后端契约（deepagents BackendProtocol.glob）：
- 不含 `/` 的模式匹配任意深度的 basename；
- 含 `/` 的模式按相对路径匹配，支持 `**` 递归；
- 只返回常规文件，不返回目录（根目录裸模式列举 skill 目录是既有行为，单独保护）。
"""

from __future__ import annotations

from src.infra.backend.skills_store import SkillsStoreBackend


def _field(value, name: str):
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def _paths(result) -> list[str]:
    return [_field(entry, "path") for entry in _field(result, "matches")]


class _NestedSkillStorage:
    """带子目录层级的 skill 存储（file path 为相对 skill 根的带斜杠路径）。"""

    def __init__(self) -> None:
        self.files = {
            "demo": {
                "SKILL.md": "demo skill",
                "README.md": "readme",
                "docs/x.md": "docs x",
                "scripts/browse.py": "browse",
                "scripts/sub/deep.py": "deep",
            },
            "browser": {
                "SKILL.md": "browser skill",
                "scripts/interact.py": "interact",
            },
            "hidden": {
                "SKILL.md": "hidden skill",
            },
        }

    async def get_effective_skills(self, user_id: str) -> dict:
        return {
            "skills": {
                name: {"name": name, "description": name, "files": files, "enabled": True}
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


def _backend() -> SkillsStoreBackend:
    backend = SkillsStoreBackend(user_id="user-1", disabled_skills=["hidden"])
    backend._storage = _NestedSkillStorage()
    return backend


async def test_root_glob_double_star_pattern_matches_files_across_skills() -> None:
    result = await _backend().aglob("**/SKILL.md", "/skills")

    assert _paths(result) == ["/browser/SKILL.md", "/demo/SKILL.md"]


async def test_root_glob_double_star_all_returns_nested_files_only() -> None:
    result = await _backend().aglob("**/*", "/skills")

    assert _paths(result) == [
        "/browser/SKILL.md",
        "/browser/scripts/interact.py",
        "/demo/README.md",
        "/demo/SKILL.md",
        "/demo/docs/x.md",
        "/demo/scripts/browse.py",
        "/demo/scripts/sub/deep.py",
    ]
    assert not _field(result, "truncated")


async def test_root_glob_bare_pattern_still_lists_skill_dirs() -> None:
    result = await _backend().aglob("*", "/skills")

    assert _paths(result) == ["/browser/", "/demo/"]


async def test_skill_glob_recursive_double_star_matches_nested_files() -> None:
    result = await _backend().aglob("**/*.py", "/skills/demo")

    assert _paths(result) == ["/demo/scripts/browse.py", "/demo/scripts/sub/deep.py"]


async def test_skill_glob_slash_pattern_matches_path_relative_not_basename() -> None:
    result = await _backend().aglob("scripts/*.py", "/skills/demo")

    # `*` 不跨目录：scripts/*.py 只匹配 scripts 直接子文件，不含 scripts/sub/deep.py
    assert _paths(result) == ["/demo/scripts/browse.py"]


async def test_skill_glob_bare_pattern_matches_basename_at_any_depth() -> None:
    result = await _backend().aglob("*.md", "/skills/demo")

    assert _paths(result) == ["/demo/README.md", "/demo/SKILL.md", "/demo/docs/x.md"]


async def test_skill_glob_from_subdirectory_searches_below_it() -> None:
    result = await _backend().aglob("**/deep.py", "/skills/demo/scripts")

    assert _paths(result) == ["/demo/scripts/sub/deep.py"]

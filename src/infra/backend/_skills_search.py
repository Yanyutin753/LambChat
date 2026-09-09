"""
Search helpers for SkillsStoreBackend.

Contains grep and glob utility methods used by the backend.
"""

import fnmatch

from deepagents.backends.utils import compile_grep_include_glob

from src.infra.async_utils import run_blocking_io
from src.infra.backend.protocol_compat import FileInfo, GrepMatch
from src.infra.logging import get_logger

logger = get_logger(__name__)
SKILLS_GREP_MAX_MATCHES = 1000


def _iter_text_lines(content: str):
    start = 0
    line_number = 1
    while True:
        newline_index = content.find("\n", start)
        if newline_index < 0:
            yield line_number, content[start:]
            return
        yield line_number, content[start:newline_index]
        start = newline_index + 1
        line_number += 1


def _grep_skill_files(
    pattern: str,
    skill_name: str,
    file_paths: list[str],
    files: dict[str, str],
    max_matches: int,
) -> list[GrepMatch]:
    matches: list[GrepMatch] = []
    for fp in file_paths:
        content = files.get(fp)
        if content is None:
            continue
        for line_number, line in _iter_text_lines(content):
            if pattern in line:
                matches.append(
                    GrepMatch(
                        path=f"/{skill_name}/{fp}",
                        line=line_number,
                        text=line[:2000],
                    )
                )
                if len(matches) >= max_matches:
                    return matches

    return matches


async def grep_single_skill(
    pattern: str,
    glob_pattern: str | None,
    skill_name: str,
    storage,
    file_paths: list[str],
    user_id: str,
    is_skill_visible_fn,
    max_matches: int = SKILLS_GREP_MAX_MATCHES,
) -> list[GrepMatch]:
    """在单个 skill 的指定文件中搜索"""
    if not is_skill_visible_fn(skill_name):
        return []

    if not file_paths:
        return []

    if glob_pattern:
        file_paths = [
            p
            for p in file_paths
            if fnmatch.fnmatch(p, glob_pattern) or fnmatch.fnmatch(p.split("/")[-1], glob_pattern)
        ]

    if not file_paths:
        return []

    files_map = await storage.batch_get_skill_files([(skill_name, user_id)])
    files = files_map.get((skill_name, user_id), {})

    return await run_blocking_io(
        _grep_skill_files,
        pattern,
        skill_name,
        file_paths,
        files,
        max_matches,
    )


def grep_across_skills(
    pattern: str,
    glob_pattern: str | None,
    all_files: dict[tuple[str, str], dict[str, str]],
    max_matches: int = SKILLS_GREP_MAX_MATCHES,
) -> list[GrepMatch]:
    """在多个 skill 中搜索"""
    matches: list[GrepMatch] = []
    for (skill_name, _user_id), files in all_files.items():
        file_paths = list(files)
        if glob_pattern:
            file_paths = [
                fp
                for fp in file_paths
                if fnmatch.fnmatch(fp, glob_pattern)
                or fnmatch.fnmatch(fp.split("/")[-1], glob_pattern)
            ]
        skill_matches = _grep_skill_files(
            pattern,
            skill_name,
            file_paths,
            files,
            max_matches - len(matches),
        )
        matches.extend(skill_matches)
        if len(matches) >= max_matches:
            return matches
    return matches


def build_file_list_from_paths(skill_name: str, prefix: str, paths: list[str]) -> list[FileInfo]:
    """构建 skill 目录的文件列表（仅路径，无内容大小）"""
    entries: list[FileInfo] = []
    seen_dirs: set[str] = set()

    prefix_slash = f"{prefix}/" if prefix else ""

    for file_path in paths:
        if not file_path.startswith(prefix_slash):
            continue

        relative = file_path[len(prefix_slash) :]
        slash_idx = relative.find("/")
        if slash_idx >= 0:
            dir_name = relative[:slash_idx]
            if dir_name not in seen_dirs:
                seen_dirs.add(dir_name)
                entries.append(
                    FileInfo(
                        path=f"/{skill_name}/{prefix_slash}{dir_name}/",
                        is_dir=True,
                    )
                )
        else:
            entries.append(
                FileInfo(
                    path=f"/{skill_name}/{file_path}",
                    is_dir=False,
                )
            )

    return entries


def glob_files_from_paths(
    skill_name: str, prefix: str, pattern: str, paths: list[str]
) -> list[FileInfo]:
    """在 skill 文件路径中按共享 glob 契约匹配（无内容大小）。

    契约与 deepagents BackendProtocol.glob 对齐：不含 ``/`` 的模式匹配任意深度的
    basename；含 ``/`` 的模式按相对搜索根的路径匹配并支持 ``**`` 递归。
    """
    prefix_slash = f"{prefix}/" if prefix else ""
    matcher = compile_grep_include_glob(pattern)
    entries: list[FileInfo] = []

    for file_path in sorted(paths):
        if not file_path.startswith(prefix_slash):
            continue

        relative = file_path[len(prefix_slash) :]
        if matcher(relative):
            entries.append(
                FileInfo(
                    path=f"/{skill_name}/{file_path}",
                    is_dir=False,
                )
            )

    return entries

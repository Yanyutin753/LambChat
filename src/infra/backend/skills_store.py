"""
Skills Store Backend

为 DeepAgent 提供 Skills 的读写后端，连接到 MongoDB。

路径格式：/skills/{skill_name}/{file_path}

特性：
- 读取：从 MongoDB 获取 skill 文件的 content
- 写入：更新 MongoDB 中 skill 的 files 字段
- 编辑：在 skill 文件中进行字符串替换
- 列表：列出所有 skills 或某个 skill 下的文件
"""

import fnmatch
from typing import TYPE_CHECKING, Any, Optional

from deepagents.backends.utils import (
    create_file_data,
    format_content_with_line_numbers,
    slice_read_response,
)

from src.infra.backend._skills_path_utils import (
    SKILL_NAME_PATTERN,
    _get_cached_storage,
    _run_async,
    get_skill_name_from_dir,
    is_skill_dir,
    is_skills_root,
    normalize_path,
    parse_skill_path,
)
from src.infra.backend._skills_search import (
    build_file_list_from_paths,
    glob_files_from_paths,
    grep_across_skills,
    grep_single_skill,
)
from src.infra.backend.protocol_compat import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from src.infra.logging import get_logger
from src.infra.skill.binary import is_binary_file, parse_binary_ref
from src.infra.skill.storage import SkillStorage

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


def _render_text_read(content: str, offset: int, limit: int) -> str:
    if not content:
        return ""
    sliced = slice_read_response(create_file_data(content), offset, limit)
    if isinstance(sliced, ReadResult):
        return str(sliced)
    return format_content_with_line_numbers(sliced, start_line=offset + 1)  # type: ignore[arg-type]


class SkillsStoreBackend(BackendProtocol):
    """
    Skills 存储后端

    将 /skills/ 路径映射到 MongoDB 中的 skills 集合。

    支持：
    - 读取：read("/skills/my-skill/SKILL.md")
    - 写入：write("/skills/my-skill/SKILL.md", content)
    - 编辑：edit("/skills/my-skill/SKILL.md", old, new)
    - 列表：ls("/skills/") 或 ls("/skills/my-skill/")
    - 搜索：grep("pattern", "/skills/my-skill/")
    - 匹配：glob("*.md", "/skills/my-skill/")
    """

    def __init__(
        self,
        user_id: str,
        runtime: Any = None,
        disabled_skills: Optional[list[str]] = None,
    ):
        self._user_id = user_id
        self._runtime = runtime
        self._disabled_skills = disabled_skills
        self._storage: Optional[SkillStorage] = None

    async def _get_storage(self) -> SkillStorage:
        """获取 SkillStorage 实例（使用全局缓存）"""
        if self._storage is None:
            self._storage = await _get_cached_storage(self._user_id)
        return self._storage

    def _get_disabled_skill_names(self) -> set[str]:
        """获取当前会话禁用的 skill 名称集合。"""
        if self._disabled_skills is not None:
            return {str(name) for name in self._disabled_skills}

        if not self._runtime or not hasattr(self._runtime, "config"):
            return set()

        try:
            configurable = self._runtime.config.get("configurable", {})
            disabled_skills = configurable.get("disabled_skills") or []
            if isinstance(disabled_skills, list):
                return {str(name) for name in disabled_skills}
        except Exception:
            pass

        return set()

    def _is_skill_visible(self, skill_name: str) -> bool:
        """检查 skill 是否在当前会话中可见。"""
        return skill_name not in self._get_disabled_skill_names()

    @staticmethod
    def _skill_not_found_error(skill_name: str) -> str:
        return f"Skill '{skill_name}' not found"

    def _filter_effective_skills(self, skills: dict[str, Any]) -> dict[str, Any]:
        """过滤当前会话禁用的 skills。"""
        disabled = self._get_disabled_skill_names()
        if not disabled:
            return skills
        return {name: data for name, data in skills.items() if name not in disabled}

    async def _get_skill_file_paths(self, storage, skill_name: str) -> list[str]:
        """获取 skill 文件路径"""
        if not self._is_skill_visible(skill_name):
            return []
        paths = await storage.list_skill_file_paths(skill_name, user_id=self._user_id)
        return paths or []

    async def _emit_skills_changed(self, action: str, skill_name: str, files_count: int = 1):
        """发送 skills 变更事件"""
        if not self._runtime:
            return
        presenter = (
            self._runtime.config.get("configurable", {}).get("presenter")
            if hasattr(self._runtime, "config")
            else None
        )
        if presenter:
            await presenter.emit_skills_changed(
                action=action,
                skill_name=skill_name,
                files_count=files_count,
            )

    # ==========================================
    # 读取操作
    # ==========================================

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return _run_async(self.aread(file_path, offset, limit))

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """异步读取 skill 文件"""
        file_path = normalize_path(file_path)

        parsed = parse_skill_path(file_path)
        if not parsed:
            return ReadResult(
                error=f"Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"
            )

        skill_name, file_name = parsed
        if not self._is_skill_visible(skill_name):
            return ReadResult(error=self._skill_not_found_error(skill_name))
        storage = await self._get_storage()

        try:
            content = await storage.get_skill_file(skill_name, file_name, self._user_id)

            if content is None:
                paths = await storage.list_skill_file_paths(skill_name, user_id=self._user_id)
                if not paths:
                    return ReadResult(error=f"Skill '{skill_name}' not found")
                if file_name not in paths:
                    return ReadResult(error=f"File '{file_name}' not found in skill '{skill_name}'")
                return ReadResult(error=f"File '{file_name}' not found in skill '{skill_name}'")

            binary_ref = parse_binary_ref(content)
            if binary_ref:
                file_url = f"/api/upload/file/{binary_ref.storage_key}"
                desc = (
                    f"[Binary file: {file_name}]\n"
                    f"- MIME type: {binary_ref.mime_type}\n"
                    f"- Size: {binary_ref.size} bytes\n"
                    f"- URL: {file_url}\n"
                    f"\nThis is a binary file stored in object storage. "
                    f"Access it via the URL above."
                )
                return ReadResult(
                    file_data={"content": desc, "encoding": "utf-8"},
                    rendered_content=_render_text_read(desc, offset, limit),
                )

            return ReadResult(
                file_data={"content": content, "encoding": "utf-8"},
                rendered_content=_render_text_read(content, offset, limit),
            )

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return ReadResult(error=str(e))

    # ==========================================
    # 写入操作
    # ==========================================

    def write(self, file_path: str, content: str) -> WriteResult:
        return _run_async(self.awrite(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """异步写入 skill 文件（无需注册 - 写文件即 skill 存在）"""
        file_path = normalize_path(file_path)

        parsed = parse_skill_path(file_path)
        if not parsed:
            return WriteResult(
                error=f"Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"
            )

        skill_name, file_name = parsed
        if not self._is_skill_visible(skill_name):
            return WriteResult(error=f"Skill '{skill_name}' is disabled for this conversation")

        if not SKILL_NAME_PATTERN.match(skill_name):
            return WriteResult(
                error=f"Invalid skill name '{skill_name}'. Only letters, numbers, underscores, hyphens, dots and CJK characters are allowed."
            )

        storage = await self._get_storage()

        try:
            existing_meta = await storage.get_skill_meta(skill_name, self._user_id)
            is_new_skill = existing_meta is None

            await storage.set_skill_file(skill_name, file_name, content, self._user_id)

            if is_new_skill:
                await storage.set_skill_meta(skill_name, self._user_id)

            await storage.invalidate_user_cache(self._user_id)

            await self._emit_skills_changed("created" if is_new_skill else "updated", skill_name)

            return WriteResult(path=file_path, files_update=None)

        except Exception as e:
            logger.error(f"Failed to write {file_path}: {e}", exc_info=True)
            return WriteResult(error=str(e))

    # ==========================================
    # 编辑操作
    # ==========================================

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return _run_async(self.aedit(file_path, old_string, new_string, replace_all))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """异步编辑 skill 文件"""
        file_path = normalize_path(file_path)

        parsed = parse_skill_path(file_path)
        if not parsed:
            return EditResult(error=f"Invalid skills path: {file_path}")

        skill_name, file_name = parsed
        if not self._is_skill_visible(skill_name):
            return EditResult(error=self._skill_not_found_error(skill_name))
        storage = await self._get_storage()

        try:
            content = await storage.get_skill_file(skill_name, file_name, user_id=self._user_id)
            if content is None:
                paths = await storage.list_skill_file_paths(skill_name, user_id=self._user_id)
                if not paths:
                    return EditResult(error=f"Skill '{skill_name}' not found")
                return EditResult(error=f"File '{file_name}' not found in skill '{skill_name}'")

            if old_string not in content:
                return EditResult(error=f"String not found in file: {old_string[:50]}...")

            if not replace_all:
                count = content.count(old_string)
                if count > 1:
                    return EditResult(
                        error=f"Found {count} occurrences. Use replace_all=True or provide more context."
                    )

            if replace_all:
                new_content = content.replace(old_string, new_string)
                occurrences = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                occurrences = 1

            success = await storage.update_skill_file_cas(
                skill_name, file_name, content, new_content, user_id=self._user_id
            )
            if not success:
                return EditResult(
                    error="File was modified concurrently. Please re-read and try again."
                )

            await storage.invalidate_user_cache(self._user_id)
            await self._emit_skills_changed("updated", skill_name)

            logger.info(
                f"Edited user skill '{skill_name}' file '{file_name}' ({occurrences} replacements)"
            )
            return EditResult(path=file_path, files_update=None, occurrences=occurrences)

        except Exception as e:
            logger.error(f"Failed to edit {file_path}: {e}")
            return EditResult(error=str(e))

    # ==========================================
    # 列表操作
    # ==========================================

    def ls(self, path: str) -> LsResult:
        return _run_async(self.als(path))

    def ls_info(self, path: str) -> list[FileInfo]:
        result = self.ls(path)
        return result.entries or []

    async def als_info(self, path: str) -> list[FileInfo]:
        result = await self.als(path)
        return result.entries or []

    async def als(self, path: str) -> LsResult:
        """异步列出 skills 或文件"""
        path = normalize_path(path)
        storage = await self._get_storage()

        try:
            if is_skills_root(path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = self._filter_effective_skills(effective_skills.get("skills", {}))
                logger.info(
                    f"[Skills ls] user={self._user_id}, found {len(skills)} effective skills: {list(skills.keys())}"
                )

                entries: list[FileInfo] = []
                for skill_name in skills.keys():
                    entries.append(
                        FileInfo(
                            path=f"/{skill_name}/",
                            is_dir=True,
                        )
                    )

                return LsResult(entries=entries)

            parsed = parse_skill_path(path)
            if not parsed:
                if is_skill_dir(path):
                    dir_skill_name: str | None = get_skill_name_from_dir(path)
                    if dir_skill_name:
                        paths = await self._get_skill_file_paths(storage, dir_skill_name)
                        return LsResult(
                            entries=build_file_list_from_paths(dir_skill_name, "", paths)
                        )
                return LsResult(entries=[])

            skill_name, sub_path = parsed
            sub_path = sub_path.rstrip("/")

            paths = await self._get_skill_file_paths(storage, skill_name)

            if sub_path in paths:
                content = await storage.get_skill_file(skill_name, sub_path, self._user_id)
                size = len(content) if content is not None else 0
                return LsResult(
                    entries=[
                        FileInfo(
                            path=f"/{skill_name}/{sub_path}",
                            is_dir=False,
                            size=size,
                        )
                    ]
                )

            return LsResult(entries=build_file_list_from_paths(skill_name, sub_path, paths))

        except Exception as e:
            logger.error(f"Failed to list {path}: {e}", exc_info=True)
            return LsResult(error=str(e))

    # ==========================================
    # 批量操作
    # ==========================================

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return _run_async(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量读取文件（异步，支持二进制文件下载）"""
        storage = await self._get_storage()

        groups: dict[str, list[tuple[str, str]]] = {}
        for path in paths:
            normalized_path = normalize_path(path)
            parsed = parse_skill_path(normalized_path)
            if not parsed:
                groups.setdefault("__invalid__", []).append((path, ""))
                continue
            skill_name, file_name = parsed
            groups.setdefault(skill_name, []).append((path, file_name))

        results: list[FileDownloadResponse] = []

        if not groups:
            return results

        skill_keys: list[tuple[str, str]] = []
        for skill_name in groups:
            if skill_name == "__invalid__":
                continue
            skill_keys.append((skill_name, self._user_id))
        files_map = await storage.batch_get_skill_files(skill_keys)

        for skill_name, items in groups.items():
            if skill_name == "__invalid__":
                for path, _ in items:
                    results.append(
                        FileDownloadResponse(path=path, content=None, error="invalid_path")
                    )
                continue

            if not self._is_skill_visible(skill_name):
                for original_path, _ in items:
                    results.append(
                        FileDownloadResponse(
                            path=original_path, content=None, error="file_not_found"
                        )
                    )
                continue

            files = files_map.get((skill_name, self._user_id), {})

            for original_path, file_name in items:
                if not files or file_name not in files:
                    results.append(
                        FileDownloadResponse(
                            path=original_path, content=None, error="file_not_found"
                        )
                    )
                    continue

                content = files[file_name]

                binary_ref = parse_binary_ref(content)
                if binary_ref:
                    try:
                        from src.infra.storage.s3.service import get_or_init_storage

                        storage_service = await get_or_init_storage()
                        data = await storage_service.download_file(binary_ref.storage_key)
                        results.append(
                            FileDownloadResponse(path=original_path, content=data, error=None)
                        )
                    except Exception as e:
                        logger.error(f"Failed to download binary {binary_ref.storage_key}: {e}")
                        results.append(
                            FileDownloadResponse(
                                path=original_path, content=None, error="file_not_found"
                            )
                        )
                else:
                    content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                    results.append(
                        FileDownloadResponse(path=original_path, content=content_bytes, error=None)
                    )

        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return _run_async(self.aupload_files(files))

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量写入文件（异步，支持二进制）"""
        results = []
        for path, content in files:
            if isinstance(content, bytes) and is_binary_file(path, content):
                normalized_path = normalize_path(path)
                parsed = parse_skill_path(normalized_path)
                if not parsed:
                    results.append(FileUploadResponse(path=path, error="invalid_path"))
                    continue

                skill_name, file_name = parsed
                if not SKILL_NAME_PATTERN.match(skill_name):
                    results.append(FileUploadResponse(path=path, error="invalid_path"))
                    continue

                if not self._is_skill_visible(skill_name):
                    results.append(FileUploadResponse(path=path, error="permission_denied"))
                    continue

                storage = await self._get_storage()
                try:
                    from src.infra.skill.binary import guess_mime_type

                    await storage.set_skill_binary_file(
                        skill_name,
                        file_name,
                        content,
                        self._user_id,
                        mime_type=guess_mime_type(file_name),
                    )
                    await storage.invalidate_user_cache(self._user_id)
                    results.append(FileUploadResponse(path=path, error=None))
                except Exception as e:
                    logger.error(f"Failed to upload binary {path}: {e}")
                    results.append(FileUploadResponse(path=path, error="permission_denied"))
            else:
                content_str = content.decode("utf-8") if isinstance(content, bytes) else content
                result = await self.awrite(path, content_str)
                if result.error:
                    results.append(FileUploadResponse(path=path, error="permission_denied"))
                else:
                    results.append(FileUploadResponse(path=path, error=None))

        return results

    # ==========================================
    # 搜索操作（grep）
    # ==========================================

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        return _run_async(self.agrep(pattern, path, glob))

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        """异步在 skill 文件中搜索文本模式（精确子串匹配）"""
        normalized_path = normalize_path(path or "/")
        storage = await self._get_storage()

        try:
            if is_skills_root(normalized_path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = self._filter_effective_skills(effective_skills.get("skills", {}))
                skill_keys = [(name, self._user_id) for name in skills]
                all_files = await storage.batch_get_skill_files(skill_keys)
                matches = grep_across_skills(pattern, glob, all_files)
                return GrepResult(matches=matches)

            parsed = parse_skill_path(normalized_path.rstrip("/"))
            if not parsed:
                skill_name = get_skill_name_from_dir(normalized_path)
                if not skill_name:
                    return GrepResult(error=f"Invalid skills path: {normalized_path}")
                paths = await self._get_skill_file_paths(storage, skill_name)
                matches = await grep_single_skill(
                    pattern, glob, skill_name, storage, paths, self._user_id, self._is_skill_visible
                )
                return GrepResult(matches=matches)

            skill_name, sub_path = parsed
            paths = await self._get_skill_file_paths(storage, skill_name)
            prefix = f"{sub_path}/" if sub_path else ""
            filtered = [p for p in paths if p.startswith(prefix)]
            matches = await grep_single_skill(
                pattern, glob, skill_name, storage, filtered, self._user_id, self._is_skill_visible
            )
            return GrepResult(matches=matches)

        except Exception as e:
            logger.error(f"Failed to grep {path}: {e}", exc_info=True)
            return GrepResult(error=str(e))

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        result = self.grep(pattern, path, glob)
        if result.error:
            return result.error if result.error.startswith("Error:") else f"Error: {result.error}"
        return result.matches or []

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        result = await self.agrep(pattern, path, glob)
        if result.error:
            return result.error if result.error.startswith("Error:") else f"Error: {result.error}"
        return result.matches or []

    # ==========================================
    # Glob 操作
    # ==========================================

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        return _run_async(self.aglob(pattern, path))

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        result = self.glob(pattern, path)
        return result.matches or []

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        result = await self.aglob(pattern, path)
        return result.matches or []

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        """异步版本"""
        normalized_path = normalize_path(path)
        storage = await self._get_storage()

        try:
            if is_skills_root(normalized_path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = self._filter_effective_skills(effective_skills.get("skills", {}))
                entries: list[FileInfo] = []
                for skill_name in skills:
                    if fnmatch.fnmatch(skill_name, pattern):
                        entries.append(FileInfo(path=f"/{skill_name}/", is_dir=True))
                return GlobResult(matches=entries)

            parsed = parse_skill_path(normalized_path.rstrip("/"))
            if not parsed:
                glob_skill_name: str | None = get_skill_name_from_dir(normalized_path)
                if glob_skill_name:
                    paths = await self._get_skill_file_paths(storage, glob_skill_name)
                    return GlobResult(
                        matches=glob_files_from_paths(glob_skill_name, "", pattern, paths)
                    )
                return GlobResult(matches=[])

            skill_name, sub_path = parsed
            paths = await self._get_skill_file_paths(storage, skill_name)
            return GlobResult(matches=glob_files_from_paths(skill_name, sub_path, pattern, paths))

        except Exception as e:
            logger.error(f"Failed to glob {path}: {e}")
            return GlobResult(error=str(e))

    def close(self) -> None:
        """关闭连接（SkillStorage 由全局缓存管理，不在此关闭）"""
        pass

    @classmethod
    async def cleanup_storage_cache(cls) -> int:
        """清理全局 SkillStorage 缓存（用于 user session 结束时调用）"""
        from src.infra.backend._skills_path_utils import _storage_cache, _storage_lock

        async with _storage_lock:
            count = len(_storage_cache)
            _storage_cache.clear()
            return count


def create_skills_backend(
    user_id: str,
    runtime: Any = None,
    disabled_skills: Optional[list[str]] = None,
) -> SkillsStoreBackend:
    """
    创建 Skills Store Backend

    Args:
        user_id: 用户 ID
        runtime: ToolRuntime 实例（可选）
        disabled_skills: 会话级禁用的 skills（可选）

    Returns:
        SkillsStoreBackend 实例
    """
    return SkillsStoreBackend(
        user_id=user_id,
        runtime=runtime,
        disabled_skills=disabled_skills,
    )

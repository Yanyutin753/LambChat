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

import asyncio
import fnmatch
import re
from typing import TYPE_CHECKING, Any, Optional

from deepagents.backends.protocol import (
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


# 路径格式：/skills/{skill_name}/{file_path}
# 内部统一使用带 /skills/ 前缀的路径
SKILLS_PATH_PATTERN = re.compile(r"^/skills/([^/]+)/(.+)$")
SKILLS_ROOT_PATTERN = re.compile(r"^/skills/?$")
SKILLS_DIR_PATTERN = re.compile(r"^/skills/([^/]+)/?$")

# Skill name 校验（与前端 SkillForm 保持一致）
SKILL_NAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\-.]+$")

# 全局 MongoDB 连接池（按 user_id 共享 SkillStorage）
# 注意：SkillStorage 本身是无状态的，数据都在 MongoDB
# 这个缓存只是为了复用 MongoDB 连接，减少连接数
_storage_cache: dict[str, SkillStorage] = {}
_storage_lock = asyncio.Lock()
MAX_STORAGE_CACHE_SIZE = 1000


async def _get_cached_storage(user_id: str) -> SkillStorage:
    """获取缓存的 SkillStorage 实例（async-safe，带容量上限）"""
    async with _storage_lock:
        if user_id not in _storage_cache:
            # 缓存满时淘汰最早插入的条目
            if len(_storage_cache) >= MAX_STORAGE_CACHE_SIZE:
                _storage_cache.pop(next(iter(_storage_cache)))
            _storage_cache[user_id] = SkillStorage()
        return _storage_cache[user_id]


def _run_async(coro):
    """
    在同步上下文中安全地运行异步协程。

    使用场景：
    - 同步方法（read/write/edit/ls）被外部同步代码调用
    - CLI 工具或测试脚本

    注意：
    - 在 FastAPI 异步环境中，应该直接调用异步方法（aread/awrite 等）
    - deepagents 内部会正确处理同步/异步调用

    实现策略：
    1. 如果没有运行中的事件循环 → 使用 asyncio.run()
    2. 如果已有运行中的事件循环 → 使用 nest_asyncio 或 run_in_executor
       避免使用 future.result()，因为它会阻塞事件循环线程导致死锁
    """
    try:
        asyncio.get_running_loop()
        # 已在异步上下文中 — 不能用 future.result()，会死锁
        # 创建新线程来运行 asyncio.run()，避免阻塞事件循环
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    except RuntimeError:
        # 没有运行中的事件循环，直接运行
        return asyncio.run(coro)


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

    def __init__(self, user_id: str, runtime: Any = None):
        """
        初始化 Skills Store Backend

        Args:
            user_id: 用户 ID，用于获取用户可见的 skills
            runtime: ToolRuntime 实例（可选，用于获取 presenter 发送事件）
        """
        self._user_id = user_id
        self._runtime = runtime
        # 使用缓存的 SkillStorage 实例
        self._storage: Optional[SkillStorage] = None

    async def _get_storage(self) -> SkillStorage:
        """获取 SkillStorage 实例（使用全局缓存）"""
        if self._storage is None:
            self._storage = await _get_cached_storage(self._user_id)
        return self._storage

    def _normalize_path(self, path: str) -> str:
        """
        标准化路径，确保始终以 /skills/ 开头

        CompositeBackend 路由时会去掉 /skills/ 前缀，
        这个方法确保内部处理时路径总是带前缀的。

        Args:
            path: 原始路径，可能有或没有 /skills/ 前缀

        Returns:
            带 /skills/ 前缀的标准化路径
        """
        if not path:
            return "/skills/"

        # 已经有正确前缀
        if path.startswith("/skills/"):
            return path

        # skills/ 开头（CompositeBackend 去掉前导 / 后的情况）
        if path.startswith("skills/"):
            return f"/{path}"

        # 其他 / 开头的路径
        if path.startswith("/"):
            return f"/skills{path}"

        # 相对路径，添加前缀
        return f"/skills/{path}"

    def _parse_skill_path(self, path: str) -> Optional[tuple[str, str]]:
        """
        解析 skills 路径

        Args:
            path: 文件路径，如 /skills/my-skill/SKILL.md

        Returns:
            (skill_name, file_path) 或 None（如果路径无效）
        """
        match = SKILLS_PATH_PATTERN.match(path)
        if match:
            return match.group(1), match.group(2)
        return None

    def _is_skills_root(self, path: str) -> bool:
        """检查是否是 skills 根路径"""
        normalized = self._normalize_path(path)
        return normalized in ("/skills/", "/skills") or bool(SKILLS_ROOT_PATTERN.match(normalized))

    def _is_skill_dir(self, path: str) -> bool:
        """检查是否是某个 skill 的目录"""
        normalized = self._normalize_path(path)
        return bool(SKILLS_DIR_PATTERN.match(normalized))

    def _get_skill_name_from_dir(self, path: str) -> Optional[str]:
        """从目录路径获取 skill 名称"""
        normalized = self._normalize_path(path)
        match = SKILLS_DIR_PATTERN.match(normalized)
        if match:
            return match.group(1)
        return None

    # ==========================================
    # 读取操作
    # ==========================================

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        return _run_async(self.aread(file_path, offset, limit))

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        """
        异步读取 skill 文件

        Args:
            file_path: 文件路径（会自动添加 /skills/ 前缀）
            offset: 起始行号（0-indexed）
            limit: 最大行数

        Returns:
            ReadResult — middleware 负责行号格式化和截断
        """
        file_path = self._normalize_path(file_path)

        parsed = self._parse_skill_path(file_path)
        if not parsed:
            return ReadResult(
                error=f"Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"
            )

        skill_name, file_name = parsed
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
                return ReadResult(file_data={"content": desc, "encoding": "utf-8"})

            # Apply offset: skip lines before offset, middleware handles line numbering + limit truncation
            if offset > 0:
                lines = content.split("\n")
                content = "\n".join(lines[offset:])

            return ReadResult(file_data={"content": content, "encoding": "utf-8"})

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return ReadResult(error=str(e))

    # ==========================================
    # 写入操作
    # ==========================================

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入 skill 文件（同步，内部调用异步）"""
        return _run_async(self.awrite(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """异步写入 skill 文件（无需注册 - 写文件即 skill 存在）"""
        file_path = self._normalize_path(file_path)

        parsed = self._parse_skill_path(file_path)
        if not parsed:
            return WriteResult(
                error=f"Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"
            )

        skill_name, file_name = parsed

        # 校验 skill name 格式
        if not SKILL_NAME_PATTERN.match(skill_name):
            return WriteResult(
                error=f"Invalid skill name '{skill_name}'. Only letters, numbers, underscores, hyphens, dots and CJK characters are allowed."
            )

        storage = await self._get_storage()

        try:
            # 检查 skill 是否已存在（有 __meta__ 或有文件）
            existing_meta = await storage.get_skill_meta(skill_name, self._user_id)
            is_new_skill = existing_meta is None

            # 直接 upsert 文件（user_id = 当前用户）
            await storage.set_skill_file(skill_name, file_name, content, self._user_id)

            # 新 skill 自动创建 __meta__
            if is_new_skill:
                await storage.set_skill_meta(skill_name, self._user_id)

            # 失效缓存
            await storage.invalidate_user_cache(self._user_id)

            # 发送 skills 变更事件（区分 created / updated）
            if self._runtime:
                presenter = (
                    self._runtime.config.get("configurable", {}).get("presenter")
                    if hasattr(self._runtime, "config")
                    else None
                )
                if presenter:
                    await presenter.emit_skills_changed(
                        action="created" if is_new_skill else "updated",
                        skill_name=skill_name,
                        files_count=1,
                    )

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
        """编辑 skill 文件（同步，内部调用异步）"""
        return _run_async(self.aedit(file_path, old_string, new_string, replace_all))

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """
        异步编辑 skill 文件

        Args:
            file_path: 文件路径（会自动添加 /skills/ 前缀）
            old_string: 要替换的字符串
            new_string: 新字符串
            replace_all: 是否替换所有出现

        Returns:
            EditResult 表示操作结果
        """
        # 标准化路径，确保有 /skills/ 前缀
        file_path = self._normalize_path(file_path)

        parsed = self._parse_skill_path(file_path)
        if not parsed:
            return EditResult(error=f"Invalid skills path: {file_path}")

        skill_name, file_name = parsed
        storage = await self._get_storage()

        try:
            # 检查文件是否存在（只需确认 skill 存在 - 即有文件）
            content = await storage.get_skill_file(skill_name, file_name, user_id=self._user_id)
            if content is None:
                # 检查 skill 是否有任何文件
                paths = await storage.list_skill_file_paths(skill_name, user_id=self._user_id)
                if not paths:
                    return EditResult(error=f"Skill '{skill_name}' not found")
                return EditResult(error=f"File '{file_name}' not found in skill '{skill_name}'")

            # 检查 old_string 是否存在
            if old_string not in content:
                return EditResult(error=f"String not found in file: {old_string[:50]}...")

            # 检查唯一性（如果不是 replace_all）
            if not replace_all:
                count = content.count(old_string)
                if count > 1:
                    return EditResult(
                        error=f"Found {count} occurrences. Use replace_all=True or provide more context."
                    )

            # 执行替换
            if replace_all:
                new_content = content.replace(old_string, new_string)
                occurrences = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                occurrences = 1

            # 使用 CAS 写入，防止并发修改丢失更新
            success = await storage.update_skill_file_cas(
                skill_name, file_name, content, new_content, user_id=self._user_id
            )
            if not success:
                return EditResult(
                    error="File was modified concurrently. Please re-read and try again."
                )

            # 清除缓存
            await storage.invalidate_user_cache(self._user_id)

            # 发送 skills 变更事件
            if self._runtime:
                presenter = (
                    self._runtime.config.get("configurable", {}).get("presenter")
                    if hasattr(self._runtime, "config")
                    else None
                )
                if presenter:
                    await presenter.emit_skills_changed(
                        action="updated",
                        skill_name=skill_name,
                        files_count=1,
                    )

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
        """列出文件（同步，内部调用异步）"""
        return _run_async(self.als(path))

    async def als(self, path: str) -> LsResult:
        """
        异步列出 skills 或文件

        Args:
            path: 路径（会自动添加 /skills/ 前缀）

        Returns:
            LsResult 包含文件/目录信息
        """
        path = self._normalize_path(path)
        storage = await self._get_storage()

        try:
            if self._is_skills_root(path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = effective_skills.get("skills", {})
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

            parsed = self._parse_skill_path(path)
            if not parsed:
                if self._is_skill_dir(path):
                    dir_skill_name: str | None = self._get_skill_name_from_dir(path)
                    if dir_skill_name:
                        paths = await self._get_skill_file_paths(storage, dir_skill_name)
                        return LsResult(
                            entries=self._build_file_list_from_paths(dir_skill_name, "", paths)
                        )
                return LsResult(entries=[])

            skill_name, sub_path = parsed
            sub_path = sub_path.rstrip("/")

            # Use paths list to check for exact file match, avoiding a full content read
            paths = await self._get_skill_file_paths(storage, skill_name)

            if sub_path in paths:
                # Exact file match — get content only when needed for size
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

            # List as directory prefix
            return LsResult(entries=self._build_file_list_from_paths(skill_name, sub_path, paths))

        except Exception as e:
            logger.error(f"Failed to list {path}: {e}", exc_info=True)
            return LsResult(error=str(e))

    async def _get_skill_file_paths(self, storage, skill_name: str) -> list[str]:
        """获取 skill 文件路径"""
        paths = await storage.list_skill_file_paths(skill_name, user_id=self._user_id)
        return paths or []

    @staticmethod
    def _build_file_list_from_paths(
        skill_name: str, prefix: str, paths: list[str]
    ) -> list[FileInfo]:
        """
        构建 skill 目录的文件列表（仅路径，无内容大小）。

        Args:
            skill_name: skill 名称
            prefix: 子目录前缀（空字符串表示 skill 根目录）
            paths: skill 的所有文件路径列表
        """
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

    # ==========================================
    # 批量操作
    # ==========================================

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量读取文件（同步）"""
        return _run_async(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量读取文件（异步，支持二进制文件下载）"""
        storage = await self._get_storage()

        # 按 skill_name 分组，减少 MongoDB 查询次数
        groups: dict[str, list[tuple[str, str]]] = {}  # skill_name -> [(original_path, file_name)]
        for path in paths:
            normalized_path = self._normalize_path(path)
            parsed = self._parse_skill_path(normalized_path)
            if not parsed:
                groups.setdefault("__invalid__", []).append((path, ""))
                continue
            skill_name, file_name = parsed
            groups.setdefault(skill_name, []).append((path, file_name))

        results: list[FileDownloadResponse] = []

        if not groups:
            return results

        # Batch-fetch all skills' files in one query
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

                # 检查是否为二进制文件引用
                binary_ref = parse_binary_ref(content)
                if binary_ref:
                    # 从 S3/local 存储下载实际二进制数据
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
                    # 文本文件
                    content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                    results.append(
                        FileDownloadResponse(path=original_path, content=content_bytes, error=None)
                    )

        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量写入文件（同步）"""
        return _run_async(self.aupload_files(files))

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量写入文件（异步，支持二进制）"""
        results = []
        for path, content in files:
            # 检测是否为二进制文件
            if isinstance(content, bytes) and is_binary_file(path, content):
                # 二进制文件：上传到 S3，存储引用
                normalized_path = self._normalize_path(path)
                parsed = self._parse_skill_path(normalized_path)
                if not parsed:
                    results.append(FileUploadResponse(path=path, error="invalid_path"))
                    continue

                skill_name, file_name = parsed
                if not SKILL_NAME_PATTERN.match(skill_name):
                    results.append(FileUploadResponse(path=path, error="invalid_path"))
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
                # 文本文件：直接写入 MongoDB
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
        """在 skill 文件中搜索文本模式（同步）"""
        return _run_async(self.agrep(pattern, path, glob))

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        """异步在 skill 文件中搜索文本模式（精确子串匹配）"""
        normalized_path = self._normalize_path(path or "/")
        storage = await self._get_storage()

        try:
            if self._is_skills_root(normalized_path):
                # Search across all skills
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = effective_skills.get("skills", {})
                skill_keys = [(name, self._user_id) for name in skills]
                all_files = await storage.batch_get_skill_files(skill_keys)
                matches = self._grep_across_skills(pattern, glob, all_files)
                return GrepResult(matches=matches)

            parsed = self._parse_skill_path(normalized_path.rstrip("/"))
            if not parsed:
                skill_name = self._get_skill_name_from_dir(normalized_path)
                if not skill_name:
                    return GrepResult(error=f"Invalid skills path: {normalized_path}")
                paths = await self._get_skill_file_paths(storage, skill_name)
                return await self._grep_single_skill(pattern, glob, skill_name, storage, paths)

            skill_name, sub_path = parsed
            paths = await self._get_skill_file_paths(storage, skill_name)
            # Filter to files under sub_path
            prefix = f"{sub_path}/" if sub_path else ""
            filtered = [p for p in paths if p.startswith(prefix)]
            return await self._grep_single_skill(pattern, glob, skill_name, storage, filtered)

        except Exception as e:
            logger.error(f"Failed to grep {path}: {e}", exc_info=True)
            return GrepResult(error=str(e))

    async def _grep_single_skill(
        self,
        pattern: str,
        glob_pattern: str | None,
        skill_name: str,
        storage: SkillStorage,
        file_paths: list[str],
    ) -> GrepResult:
        """在单个 skill 的指定文件中搜索"""
        if not file_paths:
            return GrepResult(matches=[])

        # Apply glob filter on file paths
        if glob_pattern:
            file_paths = [
                p
                for p in file_paths
                if fnmatch.fnmatch(p, glob_pattern)
                or fnmatch.fnmatch(p.split("/")[-1], glob_pattern)
            ]

        if not file_paths:
            return GrepResult(matches=[])

        files_map = await storage.batch_get_skill_files([(skill_name, self._user_id)])
        files = files_map.get((skill_name, self._user_id), {})

        matches: list[GrepMatch] = []
        for fp in file_paths:
            content = files.get(fp)
            if content is None:
                continue
            for i, line in enumerate(content.split("\n"), start=1):
                if pattern in line:
                    matches.append(
                        GrepMatch(
                            path=f"/{skill_name}/{fp}",
                            line=i,
                            text=line[:2000],
                        )
                    )

        return GrepResult(matches=matches)

    @staticmethod
    def _grep_across_skills(
        pattern: str,
        glob_pattern: str | None,
        all_files: dict[tuple[str, str], dict[str, str]],
    ) -> list[GrepMatch]:
        """在多个 skill 中搜索"""
        matches: list[GrepMatch] = []
        for (skill_name, _user_id), files in all_files.items():
            for fp, content in files.items():
                if glob_pattern and not (
                    fnmatch.fnmatch(fp, glob_pattern)
                    or fnmatch.fnmatch(fp.split("/")[-1], glob_pattern)
                ):
                    continue
                for i, line in enumerate(content.split("\n"), start=1):
                    if pattern in line:
                        matches.append(
                            GrepMatch(
                                path=f"/{skill_name}/{fp}",
                                line=i,
                                text=line[:2000],
                            )
                        )
        return matches

    # ==========================================
    # Glob 操作
    # ==========================================

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        """使用 glob 模式查找文件（同步）"""
        return _run_async(self.aglob(pattern, path))

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        """异步版本"""
        normalized_path = self._normalize_path(path)
        storage = await self._get_storage()

        try:
            if self._is_skills_root(normalized_path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = effective_skills.get("skills", {})
                entries: list[FileInfo] = []
                for skill_name in skills:
                    if fnmatch.fnmatch(skill_name, pattern):
                        entries.append(FileInfo(path=f"/{skill_name}/", is_dir=True))
                return GlobResult(matches=entries)

            parsed = self._parse_skill_path(normalized_path.rstrip("/"))
            if not parsed:
                glob_skill_name: str | None = self._get_skill_name_from_dir(normalized_path)
                if glob_skill_name:
                    paths = await self._get_skill_file_paths(storage, glob_skill_name)
                    return GlobResult(
                        matches=self._glob_files_from_paths(glob_skill_name, "", pattern, paths)
                    )
                return GlobResult(matches=[])

            skill_name, sub_path = parsed
            paths = await self._get_skill_file_paths(storage, skill_name)
            return GlobResult(
                matches=self._glob_files_from_paths(skill_name, sub_path, pattern, paths)
            )

        except Exception as e:
            logger.error(f"Failed to glob {path}: {e}")
            return GlobResult(error=str(e))

    @staticmethod
    def _glob_files_from_paths(
        skill_name: str, prefix: str, pattern: str, paths: list[str]
    ) -> list[FileInfo]:
        """在 skill 文件路径中按 glob 模式匹配（无内容大小）"""
        prefix_slash = f"{prefix}/" if prefix else ""
        entries: list[FileInfo] = []

        for file_path in paths:
            if not file_path.startswith(prefix_slash):
                continue

            relative = file_path[len(prefix_slash) :]
            basename = relative.rsplit("/", 1)[-1] if "/" in relative else relative

            if fnmatch.fnmatch(basename, pattern):
                entries.append(
                    FileInfo(
                        path=f"/{skill_name}/{file_path}",
                        is_dir=False,
                    )
                )

        return entries

    def close(self) -> None:
        """关闭连接（SkillStorage 由全局缓存管理，不在此关闭）"""
        pass

    @classmethod
    async def cleanup_storage_cache(cls) -> int:
        """清理全局 SkillStorage 缓存（用于 user session 结束时调用）"""
        async with _storage_lock:
            count = len(_storage_cache)
            _storage_cache.clear()
            return count


def create_skills_backend(user_id: str, runtime: Any = None) -> SkillsStoreBackend:
    """
    创建 Skills Store Backend

    Args:
        user_id: 用户 ID
        runtime: ToolRuntime 实例（可选）

    Returns:
        SkillsStoreBackend 实例
    """
    return SkillsStoreBackend(user_id=user_id, runtime=runtime)

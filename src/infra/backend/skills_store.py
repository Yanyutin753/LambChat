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
import logging
import re
import threading
from typing import TYPE_CHECKING, Any, Optional

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)

from src.infra.skill.storage import SkillStorage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 路径格式：/skills/{skill_name}/{file_path}
# 内部统一使用带 /skills/ 前缀的路径
SKILLS_PATH_PATTERN = re.compile(r"^/skills/([^/]+)/(.+)$")
SKILLS_ROOT_PATTERN = re.compile(r"^/skills/?$")
SKILLS_DIR_PATTERN = re.compile(r"^/skills/([^/]+)/?$")

# 全局 MongoDB 连接池（按 user_id 共享 SkillStorage）
# 注意：SkillStorage 本身是无状态的，数据都在 MongoDB
# 这个缓存只是为了复用 MongoDB 连接，减少连接数
_storage_cache: dict[str, SkillStorage] = {}
_storage_lock = threading.Lock()


def _get_cached_storage(user_id: str) -> SkillStorage:
    """
    获取缓存的 SkillStorage 实例（线程安全）

    注意：这个缓存是进程内的，在分布式环境下每个进程有自己的缓存。
    但这不是问题，因为：
    1. SkillStorage 是无状态的，数据都在 MongoDB
    2. Skills 缓存（get_effective_skills 的结果）存储在 Redis，是分布式的
    3. 写入操作会通过 Redis 失效缓存，所有进程都会重新从 MongoDB 读取

    这个缓存的主要目的是复用 MongoDB 连接，避免每个请求都创建新连接。
    """
    with _storage_lock:
        if user_id not in _storage_cache:
            _storage_cache[user_id] = SkillStorage()
        return _storage_cache[user_id]


def _run_async(coro):
    """
    在同步上下文中安全地运行异步协程。

    使用场景：
    - 同步方法（read/write/edit/ls_info）被外部同步代码调用
    - CLI 工具或测试脚本

    注意：
    - 在 FastAPI 异步环境中，应该直接调用异步方法（aread/awrite 等）
    - deepagents 内部会正确处理同步/异步调用

    实现策略：
    1. 如果没有运行中的事件循环 → 使用 asyncio.run()
    2. 如果已有运行中的事件循环 → 在新线程中创建新事件循环运行
       （这避免了 Motor 客户端绑定到错误事件循环的问题）
    """
    try:
        asyncio.get_running_loop()
        # 已在异步上下文中
        # 在新线程中创建新的事件循环运行，避免 Motor 客户端事件循环绑定问题
        result = None
        exception = None

        def run_in_thread():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                new_loop.close()
            except Exception as e:
                exception = e

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        if exception:
            raise exception
        return result

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
    - 列表：ls_info("/skills/") 或 ls_info("/skills/my-skill/")
    """

    def __init__(self, user_id: str, runtime: Any = None):
        """
        初始化 Skills Store Backend

        Args:
            user_id: 用户 ID，用于获取用户可见的 skills
            runtime: ToolRuntime 实例（可选，用于兼容性）
        """
        self._user_id = user_id
        self._runtime = runtime
        # 使用缓存的 SkillStorage 实例
        self._storage: Optional[SkillStorage] = None

    def _get_storage(self) -> SkillStorage:
        """获取 SkillStorage 实例（使用全局缓存）"""
        if self._storage is None:
            self._storage = _get_cached_storage(self._user_id)
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

        # 已经有前缀
        if path.startswith("/skills/"):
            return path

        # 添加前缀
        if path.startswith("/"):
            return f"/skills{path}"
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

    def _format_content_with_line_numbers(
        self, content: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        格式化内容为带行号的格式（类似 cat -n）

        Args:
            content: 文件内容
            offset: 起始行号（0-indexed）
            limit: 最大行数

        Returns:
            带行号的格式化内容
        """
        lines = content.split("\n")
        start = offset
        end = min(offset + limit, len(lines))

        result_lines = []
        for i in range(start, end):
            line_num = i + 1  # 1-indexed
            line_content = lines[i]
            # 截断超长行
            if len(line_content) > 2000:
                line_content = line_content[:2000] + "..."
            result_lines.append(f"{line_num:6d}\t{line_content}")

        return "\n".join(result_lines)

    # ==========================================
    # 读取操作
    # ==========================================

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """读取 skill 文件内容（同步，内部调用异步）"""
        return _run_async(self.aread(file_path, offset, limit))

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """
        异步读取 skill 文件

        Args:
            file_path: 文件路径（会自动添加 /skills/ 前缀）
            offset: 起始行号（0-indexed）
            limit: 最大行数

        Returns:
            带行号的文件内容，或错误信息字符串
        """
        # 标准化路径，确保有 /skills/ 前缀
        file_path = self._normalize_path(file_path)

        parsed = self._parse_skill_path(file_path)
        if not parsed:
            return f"Error: Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"

        skill_name, file_name = parsed
        storage = self._get_storage()

        try:
            # 先尝试用户 skill
            files = await storage.get_skill_files(skill_name, user_id=self._user_id)
            if not files:
                # 再尝试系统 skill
                files = await storage.get_skill_files(skill_name, user_id=None)

            if not files:
                return f"Error: Skill '{skill_name}' not found"

            if file_name not in files:
                return f"Error: File '{file_name}' not found in skill '{skill_name}'"

            content = files[file_name]
            return self._format_content_with_line_numbers(content, offset, limit)

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return f"Error: {e}"

    # ==========================================
    # 写入操作
    # ==========================================

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入 skill 文件（同步，内部调用异步）"""
        return _run_async(self.awrite(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """
        异步写入 skill 文件

        Args:
            file_path: 文件路径（会自动添加 /skills/ 前缀）
            content: 文件内容

        Returns:
            WriteResult 表示操作结果
        """
        # 标准化路径，确保有 /skills/ 前缀
        file_path = self._normalize_path(file_path)

        parsed = self._parse_skill_path(file_path)
        if not parsed:
            return WriteResult(
                error=f"Invalid skills path: {file_path}. Expected /skills/{{skill_name}}/{{file_path}}"
            )

        skill_name, file_name = parsed
        storage = self._get_storage()

        try:
            # 检查 skill 是否存在（用户 skill 或系统 skill）
            user_skill = await storage.get_user_skill(skill_name, self._user_id)
            system_skill = await storage.get_system_skill(skill_name)

            if user_skill:
                # 更新用户 skill
                files = await storage.get_skill_files(skill_name, user_id=self._user_id)
                files[file_name] = content
                await storage.sync_skill_files(skill_name, files, user_id=self._user_id)
                logger.info(f"Updated user skill '{skill_name}' file '{file_name}'")

            elif system_skill:
                # 系统技能是只读的，创建用户副本
                logger.info(f"Creating user copy of system skill '{skill_name}'")

                from src.kernel.schemas.skill import SkillCreate, SkillSource

                skill_create = SkillCreate(
                    name=skill_name,
                    description=system_skill.description,
                    content=system_skill.content,
                    files={**system_skill.files, file_name: content},
                    enabled=True,
                    source=SkillSource.MANUAL,
                )
                await storage.create_user_skill(skill_create, self._user_id)
                logger.info(f"Created user skill '{skill_name}' with modified file '{file_name}'")

            else:
                # Skill 不存在，自动创建新的用户 skill
                logger.info(f"Creating new user skill '{skill_name}'")
                from src.kernel.schemas.skill import SkillCreate, SkillSource

                # 尝试从 SKILL.md 解析名称和描述
                name = skill_name
                description = "Skill created by LLM"

                if file_name == "SKILL.md":
                    lines = content.split("\n")
                    for line in lines:
                        if line.startswith("# "):
                            name = line[2:].strip()
                            desc_lines = []
                            for desc_line in lines[lines.index(line) + 1 :]:
                                if desc_line.startswith("#") or desc_line.startswith("```"):
                                    break
                                if desc_line.strip():
                                    desc_lines.append(desc_line.strip())
                            if desc_lines:
                                description = " ".join(desc_lines)[:200]
                            break

                skill_create = SkillCreate(
                    name=name,
                    description=description,
                    content=content if file_name == "SKILL.md" else "",
                    files={file_name: content},
                    enabled=True,
                    source=SkillSource.MANUAL,
                )
                await storage.create_user_skill(skill_create, self._user_id)
                logger.info(f"Created user skill '{name}' with file '{file_name}'")

            # 清除缓存
            await storage._invalidate_user_skills_cache(self._user_id)

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
        storage = self._get_storage()

        try:
            # 只能编辑用户 skill
            user_skill = await storage.get_user_skill(skill_name, self._user_id)
            if not user_skill:
                return EditResult(
                    error=f"User skill '{skill_name}' not found. Cannot edit system skill files."
                )

            files = await storage.get_skill_files(skill_name, user_id=self._user_id)
            if file_name not in files:
                return EditResult(error=f"File '{file_name}' not found in skill '{skill_name}'")

            content = files[file_name]

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

            # 更新文件
            files[file_name] = new_content
            await storage.sync_skill_files(skill_name, files, user_id=self._user_id)

            # 清除缓存
            await storage._invalidate_user_skills_cache(self._user_id)

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

    def ls_info(self, path: str) -> list[FileInfo]:
        """列出文件（同步，内部调用异步）"""
        return _run_async(self.als_info(path))

    async def als_info(self, path: str) -> list[FileInfo]:
        """
        异步列出 skills 或文件

        Args:
            path: 路径（会自动添加 /skills/ 前缀）

        Returns:
            list[FileInfo] 包含文件/目录信息
        """
        # 标准化路径，确保有 /skills/ 前缀
        path = self._normalize_path(path)
        storage = self._get_storage()

        try:
            # 列出所有 skills
            if self._is_skills_root(path):
                effective_skills = await storage.get_effective_skills(self._user_id)
                skills = effective_skills.get("skills", {})

                entries: list[FileInfo] = []
                for skill_name in skills.keys():
                    entries.append(
                        FileInfo(
                            path=f"/skills/{skill_name}/",
                            is_dir=True,
                        )
                    )

                return entries

            # 列出某个 skill 下的文件
            if self._is_skill_dir(path):
                skill_name = self._get_skill_name_from_dir(path)
                if not skill_name:
                    return []

                # 先尝试用户 skill
                files = await storage.get_skill_files(skill_name, user_id=self._user_id)
                if not files:
                    # 再尝试系统 skill
                    files = await storage.get_skill_files(skill_name, user_id=None)

                if files is None:
                    files = {}

                skill_entries: list[FileInfo] = []
                for file_name in files.keys():
                    skill_entries.append(
                        FileInfo(
                            path=f"/skills/{skill_name}/{file_name}",
                            is_dir=False,
                            size=len(files[file_name]),
                        )
                    )

                return skill_entries

            return []

        except Exception as e:
            logger.error(f"Failed to list {path}: {e}")
            return []

    # ==========================================
    # 批量操作
    # ==========================================

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量读取文件（同步）"""
        return _run_async(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量读取文件（异步）"""
        results = []
        for path in paths:
            parsed = self._parse_skill_path(path)
            if not parsed:
                results.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
                continue

            skill_name, file_name = parsed
            storage = self._get_storage()

            try:
                # 先尝试用户 skill
                files = await storage.get_skill_files(skill_name, user_id=self._user_id)
                if not files:
                    # 再尝试系统 skill
                    files = await storage.get_skill_files(skill_name, user_id=None)

                if not files or file_name not in files:
                    results.append(
                        FileDownloadResponse(path=path, content=None, error="file_not_found")
                    )
                    continue

                content = files[file_name]
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                results.append(FileDownloadResponse(path=path, content=content_bytes, error=None))

            except Exception:
                # 使用 permission_denied 表示一般性错误
                results.append(
                    FileDownloadResponse(path=path, content=None, error="permission_denied")
                )

        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量写入文件（同步）"""
        return _run_async(self.aupload_files(files))

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量写入文件（异步）"""
        results = []
        for path, content in files:
            content_str = content.decode("utf-8") if isinstance(content, bytes) else content
            result = await self.awrite(path, content_str)
            if result.error:
                # 使用 permission_denied 表示一般性错误
                results.append(FileUploadResponse(path=path, error="permission_denied"))
            else:
                results.append(FileUploadResponse(path=path, error=None))

        return results

    # ==========================================
    # 搜索操作（grep）
    # ==========================================

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """在 skill 文件中搜索文本模式"""
        # Skills backend 不支持 grep，返回提示信息
        return "grep is not supported for skills backend. Use read() to view file content."

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """异步版本"""
        return self.grep_raw(pattern, path, glob)

    # ==========================================
    # Glob 操作
    # ==========================================

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """使用 glob 模式查找文件"""
        # 简化实现：只支持列出所有 skills
        if path == "/skills/" or path == "/skills":
            return self.ls_info("/skills/")
        return []

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """异步版本"""
        return self.glob_info(pattern, path)

    def close(self) -> None:
        """关闭连接（SkillStorage 由全局缓存管理，不在此关闭）"""
        pass


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

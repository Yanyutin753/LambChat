"""
Composite Backend

组合 SkillsStoreBackend 和真实 Sandbox Backend，提供统一的文件访问接口。

特性：
- /skills/ 路径 -> SkillsStoreBackend (MongoDB)
- 其他路径 -> 真实 Sandbox Backend (Daytona/Runloop/Modal)
- LLM 编辑 skills/ 文件时可以真实修改到用户数据库
- 向后兼容原有工具和 skills 管理功能
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, Union

from deepagents.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)

from src.infra.backend.skills_store import SkillsStoreBackend

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)

# Skills 路径前缀
SKILLS_PATH_PREFIX = "/skills/"


class CompositeBackend:
    """
    组合 Backend

    将 /skills/ 路径委托给 SkillsStoreBackend，
    其他路径委托给真实的 Sandbox Backend。

    这使得 LLM 可以：
    1. 读取 /skills/ 目录查看用户技能
    2. 写入 /skills/ 目录创建/修改用户技能
    3. 编辑 /skills/ 文件更新 MongoDB 中的技能数据
    """

    def __init__(
        self,
        sandbox_backend: "SandboxBackendProtocol",
        skills_backend: SkillsStoreBackend,
    ):
        """
        初始化组合 Backend

        Args:
            sandbox_backend: 真实的 Sandbox Backend (Daytona/Runloop/Modal)
            skills_backend: Skills Store Backend (MongoDB)
        """
        self._sandbox = sandbox_backend
        self._skills = skills_backend
        logger.info(
            f"CompositeBackend initialized with sandbox_id={sandbox_backend.id}, "
            f"skills_user_id={skills_backend._user_id}"
        )

    def _is_skills_path(self, path: str) -> bool:
        """检查是否是 skills 路径"""
        return path.startswith(SKILLS_PATH_PREFIX) or path == "/skills"

    # ==========================================
    # 属性
    # ==========================================

    @property
    def id(self) -> str:
        """Backend ID"""
        return self._sandbox.id

    @property
    def sandbox(self) -> "SandboxBackendProtocol":
        """获取底层 sandbox backend"""
        return self._sandbox

    @property
    def skills(self) -> SkillsStoreBackend:
        """获取 skills backend"""
        return self._skills

    # ==========================================
    # 读取操作
    # ==========================================

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """读取文件内容"""
        if self._is_skills_path(file_path):
            return self._skills.read(file_path, offset, limit)
        return self._sandbox.read(file_path, offset, limit)

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """异步读取文件内容"""
        if self._is_skills_path(file_path):
            return await self._skills.aread(file_path, offset, limit)
        return await self._sandbox.aread(file_path, offset, limit)

    # ==========================================
    # 写入操作
    # ==========================================

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入文件"""
        if self._is_skills_path(file_path):
            logger.info(f"Writing to skills backend: {file_path}")
            return self._skills.write(file_path, content)
        return self._sandbox.write(file_path, content)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """异步写入文件"""
        if self._is_skills_path(file_path):
            logger.info(f"Writing to skills backend: {file_path}")
            return await self._skills.awrite(file_path, content)
        return await self._sandbox.awrite(file_path, content)

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
        """编辑文件"""
        if self._is_skills_path(file_path):
            logger.info(f"Editing skills backend: {file_path}")
            return self._skills.edit(file_path, old_string, new_string, replace_all)
        return self._sandbox.edit(file_path, old_string, new_string, replace_all)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """异步编辑文件"""
        if self._is_skills_path(file_path):
            logger.info(f"Editing skills backend: {file_path}")
            return await self._skills.aedit(file_path, old_string, new_string, replace_all)
        return await self._sandbox.aedit(file_path, old_string, new_string, replace_all)

    # ==========================================
    # 列表操作
    # ==========================================

    def ls_info(self, path: str) -> list[FileInfo]:
        """列出目录内容"""
        if self._is_skills_path(path):
            return self._skills.ls_info(path)
        return self._sandbox.ls_info(path)

    async def als_info(self, path: str) -> list[FileInfo]:
        """异步列出目录内容"""
        if self._is_skills_path(path):
            return await self._skills.als_info(path)
        return await self._sandbox.als_info(path)

    # ==========================================
    # 批量操作
    # ==========================================

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量下载文件"""
        skills_paths = []
        sandbox_paths = []

        for path in paths:
            if self._is_skills_path(path):
                skills_paths.append(path)
            else:
                sandbox_paths.append(path)

        results = []

        if skills_paths:
            results.extend(self._skills.download_files(skills_paths))
        if sandbox_paths:
            results.extend(self._sandbox.download_files(sandbox_paths))

        return results

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """异步批量下载文件"""
        skills_paths = []
        sandbox_paths = []

        for path in paths:
            if self._is_skills_path(path):
                skills_paths.append(path)
            else:
                sandbox_paths.append(path)

        results = []

        if skills_paths:
            results.extend(await self._skills.adownload_files(skills_paths))
        if sandbox_paths:
            results.extend(await self._sandbox.adownload_files(sandbox_paths))

        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量上传文件"""
        skills_files = []
        sandbox_files = []

        for path, content in files:
            if self._is_skills_path(path):
                skills_files.append((path, content))
            else:
                sandbox_files.append((path, content))

        results = []

        if skills_files:
            logger.info(f"Uploading {len(skills_files)} files to skills backend")
            results.extend(self._skills.upload_files(skills_files))
        if sandbox_files:
            results.extend(self._sandbox.upload_files(sandbox_files))

        return results

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """异步批量上传文件"""
        skills_files = []
        sandbox_files = []

        for path, content in files:
            if self._is_skills_path(path):
                skills_files.append((path, content))
            else:
                sandbox_files.append((path, content))

        results = []

        if skills_files:
            logger.info(f"Uploading {len(skills_files)} files to skills backend")
            results.extend(await self._skills.aupload_files(skills_files))
        if sandbox_files:
            results.extend(await self._sandbox.aupload_files(sandbox_files))

        return results

    # ==========================================
    # 执行操作 (仅 Sandbox)
    # ==========================================

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """执行命令（仅 Sandbox）"""
        return self._sandbox.execute(command, timeout=timeout)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """异步执行命令（仅 Sandbox）"""
        return await self._sandbox.aexecute(command, timeout=timeout)

    # ==========================================
    # 搜索操作
    # ==========================================

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """搜索文件内容"""
        if path and self._is_skills_path(path):
            return self._skills.grep_raw(pattern, path, glob)
        return self._sandbox.grep_raw(pattern, path, glob)

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """异步搜索文件内容"""
        if path and self._is_skills_path(path):
            return await self._skills.agrep_raw(pattern, path, glob)
        return await self._sandbox.agrep_raw(pattern, path, glob)

    # ==========================================
    # Glob 操作
    # ==========================================

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """使用 glob 模式查找文件"""
        if self._is_skills_path(path):
            return self._skills.glob_info(pattern, path)
        return self._sandbox.glob_info(pattern, path)

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """异步 glob 查找"""
        if self._is_skills_path(path):
            return await self._skills.aglob_info(pattern, path)
        return await self._sandbox.aglob_info(pattern, path)

    # ==========================================
    # 其他操作
    # ==========================================

    def close(self) -> None:
        """关闭连接"""
        try:
            self._skills.close()
        except Exception as e:
            logger.warning(f"Failed to close skills backend: {e}")

        try:
            self._sandbox.close()
        except Exception as e:
            logger.warning(f"Failed to close sandbox backend: {e}")


def create_composite_backend(
    sandbox_backend: "SandboxBackendProtocol",
    user_id: str,
    runtime: Any = None,
) -> CompositeBackend:
    """
    创建组合 Backend

    Args:
        sandbox_backend: 真实的 Sandbox Backend
        user_id: 用户 ID
        runtime: ToolRuntime 实例（可选）

    Returns:
        CompositeBackend 实例
    """
    skills_backend = SkillsStoreBackend(user_id=user_id, runtime=runtime)
    return CompositeBackend(sandbox_backend=sandbox_backend, skills_backend=skills_backend)

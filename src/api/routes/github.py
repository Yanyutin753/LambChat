"""
GitHub Skills 导入 API

提供从 GitHub 仓库预览和安装技能的功能。
"""

import asyncio
import codecs
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional, TypeVar

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.api.routes.plugin_guard import plugin_route_guard
from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.skill.parser import parse_skill_md
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import InstalledFrom
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

GITHUB_INSTALLER_PLUGIN_ID = "github_installer"

router = APIRouter(dependencies=[Depends(plugin_route_guard(GITHUB_INSTALLER_PLUGIN_ID))])

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_SCAN_CONCURRENCY = 8
GITHUB_IMPORT_MAX_FILES = 500
GITHUB_IMPORT_MAX_TOTAL_BYTES = 10 * 1024 * 1024
GITHUB_SKILL_MD_MAX_BYTES = 256 * 1024
GITHUB_INSTALL_MAX_SKILLS = 100

T = TypeVar("T")


@dataclass
class _GitHubImportLimits:
    file_count: int = 0
    total_bytes: int = 0


def _github_item_size(item: dict[str, Any]) -> int | None:
    raw_size = item.get("size")
    if raw_size is None:
        return None
    try:
        size = int(raw_size)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _github_import_too_large_message() -> str:
    max_mb = GITHUB_IMPORT_MAX_TOTAL_BYTES // (1024 * 1024)
    return f"GitHub skill content too large (max {max_mb}MB)"


def _bounded_requested_skill_names(skill_names: list[str]) -> list[str]:
    bounded: list[str] = []
    seen: set[str] = set()
    for skill_name in skill_names:
        if not isinstance(skill_name, str):
            continue
        normalized = skill_name.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        bounded.append(normalized)
        if len(bounded) > GITHUB_INSTALL_MAX_SKILLS:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot install more than {GITHUB_INSTALL_MAX_SKILLS} skills at once",
            )
    return bounded


async def _gather_limited(
    factories: list[Callable[[], Awaitable[T]]],
    limit: int = GITHUB_SCAN_CONCURRENCY,
) -> list[T]:
    """Run awaitable factories with bounded concurrency while preserving order."""
    if not factories:
        return []

    results: list[T | None] = [None] * len(factories)
    next_index = 0
    lock = asyncio.Lock()

    async def _worker() -> None:
        nonlocal next_index
        while True:
            async with lock:
                if next_index >= len(factories):
                    return
                index = next_index
                next_index += 1
            results[index] = await factories[index]()

    worker_count = min(max(1, limit), len(factories))
    await asyncio.gather(*(_worker() for _ in range(worker_count)))
    return [result for result in results if result is not None]


class GitHubPreviewRequest(BaseModel):
    """GitHub 预览请求"""

    repo_url: str
    branch: str = "main"


class GitHubSkillPreview(BaseModel):
    """GitHub 技能预览"""

    name: str
    path: str
    description: str


class GitHubPreviewResponse(BaseModel):
    """GitHub 预览响应"""

    repo_url: str
    branch: str
    skills: list[GitHubSkillPreview]


class GitHubInstallRequest(BaseModel):
    """GitHub 安装请求"""

    repo_url: str
    branch: str = "main"
    skill_names: list[str]


class GitHubInstallResponse(BaseModel):
    """GitHub 安装响应"""

    message: str
    installed: list[str]
    errors: list[str]


def parse_github_url(url: str) -> tuple[str, str]:
    """
    解析 GitHub URL，返回 (owner, repo)

    支持格式:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/branch
    - owner/repo
    """
    url = url.strip()

    # owner/repo 格式
    if re.match(r"^[\w-]+/[\w.-]+$", url):
        parts = url.split("/")
        return parts[0], parts[1]

    # https://github.com/owner/repo 格式
    match = re.match(r"https?://github\.com/([\w-]+)/([\w.-]+)", url)
    if match:
        return match.group(1), match.group(2)

    raise ValueError(f"Invalid GitHub URL: {url}")


async def fetch_github_dir(
    owner: str,
    repo: str,
    branch: str,
    path: str = "",
) -> list[dict]:
    """获取 GitHub 目录内容"""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=30.0)
        if resp.status_code == 404:
            return []
        if resp.status_code == 403:
            # GitHub API rate limit
            remaining = resp.headers.get("X-RateLimit-Remaining", "unknown")
            reset_ts = resp.headers.get("X-RateLimit-Reset", "")
            detail = f"GitHub API rate limit exceeded (remaining: {remaining})"
            if reset_ts:
                from datetime import datetime, timezone

                try:
                    reset_dt = datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
                    detail += f", resets at {reset_dt.isoformat()}"
                except (ValueError, OSError):
                    pass
            logger.warning(f"GitHub API rate limit: {detail}")
            raise HTTPException(status_code=429, detail=detail)
        resp.raise_for_status()
        return resp.json()


async def fetch_all_files_recursive(
    owner: str,
    repo: str,
    branch: str,
    dir_path: str = "",
    prefix: str = "",
    _limits: _GitHubImportLimits | None = None,
) -> dict[str, str]:
    """
    递归获取 GitHub 目录下所有文件内容

    Args:
        owner: GitHub owner
        repo: GitHub repo
        branch: 分支名
        dir_path: GitHub 上的目录路径
        prefix: 文件路径前缀（用于相对路径）

    Returns:
        {相对文件路径: 文件内容}
    """
    files: dict[str, str] = {}
    if _limits is None:
        _limits = _GitHubImportLimits()

    try:
        contents = await fetch_github_dir(owner, repo, branch, dir_path)
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub dir {owner}/{repo}/{dir_path}: {e}")
        return files

    # 分离文件和目录，并发获取文件内容
    file_tasks = []
    dir_items = []
    for item in contents:
        if item["name"].startswith(".") or item["name"] == "__pycache__":
            continue
        if item["type"] == "file":
            file_tasks.append(item)
        elif item["type"] == "dir":
            dir_items.append(item)

    _limits.file_count += len(file_tasks)
    if _limits.file_count > GITHUB_IMPORT_MAX_FILES:
        raise ValueError(f"GitHub skill contains too many files (max {GITHUB_IMPORT_MAX_FILES})")

    for item in file_tasks:
        known_size = _github_item_size(item)
        if known_size is None:
            continue
        if _limits.total_bytes + known_size > GITHUB_IMPORT_MAX_TOTAL_BYTES:
            raise ValueError(_github_import_too_large_message())
        _limits.total_bytes += known_size

    # 并发获取所有文件内容
    if file_tasks:

        async def _fetch_file(item: dict[str, Any]) -> tuple[str, str | None, int | None]:
            remaining_bytes = GITHUB_IMPORT_MAX_TOTAL_BYTES - _limits.total_bytes
            content = await fetch_github_file(
                owner,
                repo,
                branch,
                item["path"],
                max_bytes=max(0, remaining_bytes),
            )
            rel_path = f"{prefix}{item['name']}" if prefix else item["name"]
            return rel_path, content, _github_item_size(item)

        fetch_tasks: list[Callable[[], Awaitable[tuple[str, str | None, int | None]]]] = []
        for item in file_tasks:

            async def _fetch_current(
                item: dict[str, Any] = item,
            ) -> tuple[str, str | None, int | None]:
                return await _fetch_file(item)

            fetch_tasks.append(_fetch_current)

        results = await _gather_limited(fetch_tasks)
        for rel_path, content, known_size in results:
            if content is not None:
                actual_size = len(content.encode("utf-8"))
                if known_size is None:
                    _limits.total_bytes += actual_size
                else:
                    _limits.total_bytes += actual_size - known_size
                if _limits.total_bytes > GITHUB_IMPORT_MAX_TOTAL_BYTES:
                    raise ValueError(_github_import_too_large_message())
                files[rel_path] = content

    # 递归获取子目录
    if dir_items:
        dir_tasks: list[Callable[[], Awaitable[dict[str, str]]]] = []
        for item in dir_items:
            sub_prefix = f"{prefix}{item['name']}/" if prefix else f"{item['name']}/"

            async def _fetch_dir(
                item: dict[str, Any] = item,
                sub_prefix: str = sub_prefix,
            ) -> dict[str, str]:
                return await fetch_all_files_recursive(
                    owner, repo, branch, item["path"], sub_prefix, _limits
                )

            dir_tasks.append(_fetch_dir)
        dir_results = await _gather_limited(dir_tasks)
        for sub_files in dir_results:
            files.update(sub_files)

    return files


async def fetch_github_file(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    max_bytes: int | None = None,
) -> Optional[str]:
    """获取 GitHub 文件内容"""
    url = f"{GITHUB_RAW}/{owner}/{repo}/{branch}/{path}"
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, timeout=30.0) as resp:
            if resp.status_code != 200:
                return None
            decoder = codecs.getincrementaldecoder("utf-8")()
            text_buffer = io.StringIO()
            total_bytes = 0
            async for chunk in resp.aiter_bytes():
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if max_bytes is not None and total_bytes > max_bytes:
                    raise ValueError(_github_import_too_large_message())
                text = await run_blocking_io(decoder.decode, chunk, False)
                text_buffer.write(text)
                del chunk
            text_buffer.write(await run_blocking_io(decoder.decode, b"", True))
            return text_buffer.getvalue()


def _parse_skill_md(skill_md: str, fallback_name: str, fallback_source: str) -> dict[str, Any]:
    """从 SKILL.md 内容解析技能描述，名称优先使用 frontmatter 的 name 字段"""
    from src.infra.skill.parser import sanitize_skill_name

    parsed_name, description, tags = parse_skill_md(skill_md)
    name = sanitize_skill_name(parsed_name) if parsed_name else sanitize_skill_name(fallback_name)
    return {
        "name": name,
        "description": description or f"Skill from {fallback_source}",
        "tags": tags,
    }


async def scan_for_skills(
    owner: str,
    repo: str,
    branch: str,
    path: str = "",
    _depth: int = 0,
    max_depth: int = 3,
) -> list[dict[str, Any]]:
    """递归扫描 GitHub 仓库查找技能"""
    skills = []

    try:
        contents = await fetch_github_dir(owner, repo, branch, path)
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub dir {owner}/{repo}/{path}: {e}")
        return []

    sub_dirs = []
    for item in contents:
        if item["type"] == "dir":
            # 检查是否是技能目录（包含 SKILL.md）
            skill_md_url = f"{item['path']}/SKILL.md"
            skill_md = await fetch_github_file(
                owner,
                repo,
                branch,
                skill_md_url,
                max_bytes=GITHUB_SKILL_MD_MAX_BYTES,
            )
            if skill_md:
                parsed = _parse_skill_md(skill_md, item["name"], item["name"])
                parsed["path"] = item["path"]
                skills.append(parsed)
            else:
                # 没找到 SKILL.md，记录子目录稍后递归扫描
                sub_dirs.append(item)
        elif item["type"] == "file" and item["name"] == "SKILL.md":
            # 根目录的 SKILL.md
            skill_md = await fetch_github_file(
                owner,
                repo,
                branch,
                item["path"],
                max_bytes=GITHUB_SKILL_MD_MAX_BYTES,
            )
            if skill_md:
                parsed = _parse_skill_md(skill_md, repo, repo)
                parsed["path"] = ""
                skills.append(parsed)

    # 递归扫描未找到 SKILL.md 的子目录（限制深度）
    if sub_dirs and _depth < max_depth:
        scan_tasks: list[Callable[[], Awaitable[list[dict[str, Any]]]]] = []
        for directory in sub_dirs:

            async def _scan_dir(directory: dict[str, Any] = directory) -> list[dict[str, Any]]:
                return await scan_for_skills(
                    owner,
                    repo,
                    branch,
                    directory["path"],
                    _depth=_depth + 1,
                    max_depth=max_depth,
                )

            scan_tasks.append(_scan_dir)

        sub_results = await _gather_limited(scan_tasks)
        for sub_skills in sub_results:
            skills.extend(sub_skills)

    return skills


@router.post("/preview", response_model=GitHubPreviewResponse)
async def preview_github_skills(
    request: GitHubPreviewRequest,
    user: TokenPayload = Depends(require_permissions("skill:read")),
):
    """
    预览 GitHub 仓库中的技能

    扫描 GitHub 仓库，查找包含 SKILL.md 的目录作为技能。
    """
    try:
        owner, repo = parse_github_url(request.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        skills = await scan_for_skills(owner, repo, request.branch)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository or branch not found")
        raise HTTPException(status_code=500, detail=f"GitHub API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Failed to preview GitHub skills: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch repository: {str(e)}")

    if not skills:
        raise HTTPException(status_code=404, detail="No skills found in repository")

    return GitHubPreviewResponse(
        repo_url=request.repo_url,
        branch=request.branch,
        skills=[GitHubSkillPreview(**s) for s in skills],
    )


@router.post("/install", response_model=GitHubInstallResponse, status_code=201)
async def install_github_skills(
    request: GitHubInstallRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
):
    """
    从 GitHub 仓库安装技能

    下载选中的技能文件并保存到用户技能存储。
    """
    try:
        owner, repo = parse_github_url(request.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    requested_skill_names = _bounded_requested_skill_names(request.skill_names)
    storage = SkillStorage()
    installed = []
    errors = []

    # 只扫描一次仓库，避免重复请求 GitHub API
    try:
        all_skills = await scan_for_skills(owner, repo, request.branch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan repository: {str(e)}")

    for skill_name in requested_skill_names:
        try:
            skill_info = next((s for s in all_skills if s["name"] == skill_name), None)
            if not skill_info:
                errors.append(f"Skill '{skill_name}' not found")
                continue

            skill_path = skill_info["path"]

            # 递归获取技能目录中的所有文件（包括子目录）
            files = await fetch_all_files_recursive(owner, repo, request.branch, skill_path)
            if not files:
                errors.append(f"No files found for '{skill_name}'")
                continue

            # 检查是否已存在
            existing = await storage.get_skill_files(skill_name, user.sub)
            if existing:
                errors.append(f"Skill '{skill_name}' already exists")
                continue

            # 保存文件
            try:
                await storage.create_user_skill(
                    skill_name, files, user.sub, installed_from=InstalledFrom.MANUAL
                )
            except Exception as e:
                # 回滚：清理已写入的文件
                await storage.delete_skill_files(skill_name, user.sub)
                raise e

            installed.append(skill_name)

        except Exception as e:
            logger.error(f"Failed to install skill {skill_name}: {e}")
            errors.append(f"Failed to install '{skill_name}': {str(e)}")

    # 失效缓存
    if installed:
        await storage.invalidate_user_cache(user.sub)

    return GitHubInstallResponse(
        message=f"Installed {len(installed)} skill(s)",
        installed=installed,
        errors=errors,
    )

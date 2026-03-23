"""
GitHub Skills 导入 API

提供从 GitHub 仓库预览和安装技能的功能。
"""

import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.infra.logging import get_logger
from src.infra.skill.storage import SkillStorage
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"


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
    if re.match(r'^[\w-]+/[\w.-]+$', url):
        parts = url.split('/')
        return parts[0], parts[1]

    # https://github.com/owner/repo 格式
    match = re.match(r'https?://github\.com/([\w-]+)/([\w.-]+)', url)
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
        resp.raise_for_status()
        return resp.json()


async def fetch_github_file(
    owner: str,
    repo: str,
    branch: str,
    path: str,
) -> Optional[str]:
    """获取 GitHub 文件内容"""
    url = f"{GITHUB_RAW}/{owner}/{repo}/{branch}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=30.0)
        if resp.status_code != 200:
            return None
        return resp.text


async def scan_for_skills(
    owner: str,
    repo: str,
    branch: str,
    path: str = "",
) -> list[dict[str, Any]]:
    """扫描 GitHub 仓库查找技能"""
    skills = []

    try:
        contents = await fetch_github_dir(owner, repo, branch, path)
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub dir {owner}/{repo}/{path}: {e}")
        return []

    for item in contents:
        if item["type"] == "dir":
            # 检查是否是技能目录（包含 SKILL.md）
            skill_md_url = f"{item['path']}/SKILL.md"
            skill_md = await fetch_github_file(owner, repo, branch, skill_md_url)
            if skill_md:
                # 解析技能名称和描述
                name = item["name"]
                description = ""
                for line in skill_md.splitlines()[:10]:
                    if line.startswith("name:"):
                        name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("description:"):
                        description = line.split("description:", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("# ") and not description:
                        description = line[2:].strip()

                skills.append({
                    "name": name,
                    "path": item["path"],
                    "description": description or f"Skill from {item['name']}",
                })
        elif item["type"] == "file" and item["name"] == "SKILL.md":
            # 根目录的 SKILL.md
            skill_md = await fetch_github_file(owner, repo, branch, item["path"])
            if skill_md:
                name = repo
                description = ""
                for line in skill_md.splitlines()[:10]:
                    if line.startswith("name:"):
                        name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("description:"):
                        description = line.split("description:", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("# ") and not description:
                        description = line[2:].strip()

                skills.append({
                    "name": name,
                    "path": "",
                    "description": description or f"Skill from {repo}",
                })

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

    storage = SkillStorage()
    installed = []
    errors = []

    for skill_name in request.skill_names:
        try:
            # 查找技能路径
            skills = await scan_for_skills(owner, repo, request.branch)
            skill_info = next((s for s in skills if s["name"] == skill_name), None)
            if not skill_info:
                errors.append(f"Skill '{skill_name}' not found")
                continue

            skill_path = skill_info["path"]

            # 获取技能目录中的所有文件
            contents = await fetch_github_dir(owner, repo, request.branch, skill_path)
            if not contents:
                errors.append(f"Failed to fetch files for '{skill_name}'")
                continue

            # 下载所有文件
            files = {}
            for item in contents:
                if item["type"] == "file" and not item["name"].startswith("."):
                    content = await fetch_github_file(owner, repo, request.branch, item["path"])
                    if content is not None:
                        # 使用相对路径
                        rel_path = item["name"] if not skill_path else item["path"].replace(skill_path + "/", "")
                        files[rel_path] = content

            if not files:
                errors.append(f"No files found for '{skill_name}'")
                continue

            # 检查是否已存在
            existing = await storage.get_skill_files(skill_name, user.sub)
            if existing:
                errors.append(f"Skill '{skill_name}' already exists")
                continue

            # 保存文件
            for file_path, content in files.items():
                await storage.set_skill_file(skill_name, file_path, content, user.sub)

            # 创建开关记录
            await storage.upsert_toggle(skill_name, user.sub, enabled=True)

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

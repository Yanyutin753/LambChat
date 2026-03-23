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


async def fetch_all_files_recursive(
    owner: str,
    repo: str,
    branch: str,
    dir_path: str = "",
    prefix: str = "",
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

    try:
        contents = await fetch_github_dir(owner, repo, branch, dir_path)
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub dir {owner}/{repo}/{dir_path}: {e}")
        return files

    for item in contents:
        # 跳过隐藏文件和 __pycache__
        if item["name"].startswith(".") or item["name"] == "__pycache__":
            continue

        if item["type"] == "file":
            content = await fetch_github_file(owner, repo, branch, item["path"])
            if content is not None:
                rel_path = f"{prefix}{item['name']}" if prefix else item["name"]
                files[rel_path] = content
        elif item["type"] == "dir":
            # 递归进入子目录
            sub_prefix = f"{prefix}{item['name']}/" if prefix else f"{item['name']}/"
            sub_files = await fetch_all_files_recursive(
                owner, repo, branch, item["path"], sub_prefix
            )
            files.update(sub_files)

    return files


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


def _parse_skill_md(skill_md: str, fallback_name: str, fallback_source: str) -> dict[str, Any]:
    """从 SKILL.md 内容解析技能名称和描述，支持 YAML 多行值（|, >）"""
    name = fallback_name
    description = ""

    # 提取 --- ... --- frontmatter 块
    frontmatter = ""
    lines = skill_md.splitlines()
    in_frontmatter = False
    frontmatter_lines: list[str] = []
    for line in lines:
        if line.strip() == "---" and not in_frontmatter:
            in_frontmatter = True
            continue
        elif line.strip() == "---" and in_frontmatter:
            break
        elif in_frontmatter:
            frontmatter_lines.append(line)

    if frontmatter_lines:
        frontmatter = "\n".join(frontmatter_lines)
        # 使用 yaml 解析 frontmatter
        try:
            import yaml
            meta = yaml.safe_load(frontmatter) or {}
            if isinstance(meta.get("name"), str):
                name = meta["name"]
            if isinstance(meta.get("description"), str):
                description = meta["description"].strip()
        except Exception:
            # yaml 解析失败，回退到手动解析
            pass

    # 回退：手动逐行解析（处理非 frontmatter 或 yaml 不可用的情况）
    if not description:
        for line in lines[:20]:
            if line.startswith("name:") and name == fallback_name:
                name = line.split("name:", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("description:"):
                val = line.split("description:", 1)[1].strip()
                if val in ("|", ">"):
                    continue  # 多行指示符，跳过
                if not val.startswith("---"):
                    description = val.strip('"').strip("'")
            elif line.startswith("# ") and not description:
                description = line[2:].strip()

    return {
        "name": name,
        "description": description or f"Skill from {fallback_source}",
    }


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
                parsed = _parse_skill_md(skill_md, item["name"], item["name"])
                parsed["path"] = item["path"]
                skills.append(parsed)
        elif item["type"] == "file" and item["name"] == "SKILL.md":
            # 根目录的 SKILL.md
            skill_md = await fetch_github_file(owner, repo, branch, item["path"])
            if skill_md:
                parsed = _parse_skill_md(skill_md, repo, repo)
                parsed["path"] = ""
                skills.append(parsed)

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

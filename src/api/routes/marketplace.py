# src/api/routes/marketplace.py
"""
用户商城 API

提供商城浏览、安装和直接发布功能。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import (
    InstalledFrom,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


def get_storage() -> SkillStorage:
    return SkillStorage()


class MarketplaceCreateRequest(BaseModel):
    """直接在商店创建 Skill 的请求"""

    skill_name: str
    description: str = ""
    tags: list[str] = []
    version: str = "1.0.0"
    files: dict[str, str] = {}


class SetActiveRequest(BaseModel):
    """Admin 激活/停用请求"""

    is_active: bool


# ==========================================
# 用户商城 API
# ==========================================


@router.get("/", response_model=list[MarketplaceSkillResponse])
async def list_marketplace_skills(
    tags: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出商城 Skills（所有用户：激活的 skill + 自己发布的含停用的）"""
    tag_list = tags.split(",") if tags else None
    skills = await marketplace.list_marketplace_skills(
        tags=tag_list, search=search, include_inactive=False, viewer_id=user.sub,
    )
    return skills[skip : skip + limit]


@router.get("/tags")
async def list_tags(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取所有标签"""
    tags = await marketplace.list_all_tags()
    return {"tags": tags}


@router.post("/", response_model=MarketplaceSkillResponse, status_code=201)
async def create_marketplace_skill(
    data: MarketplaceCreateRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """直接在商店创建 Skill（不写入用户 skill_files）"""
    if not data.files:
        raise HTTPException(status_code=400, detail="Skill must have at least one file")

    try:
        create_data = MarketplaceSkillCreate(
            skill_name=data.skill_name,
            description=data.description,
            tags=data.tags,
            version=data.version,
        )
        await marketplace.create_marketplace_skill(create_data, user_id=user.sub)
        await marketplace.sync_marketplace_files(data.skill_name, data.files)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    response = await marketplace.get_marketplace_skill_response(data.skill_name, viewer_id=user.sub)
    return response


@router.get("/{name}", response_model=MarketplaceSkillResponse)
async def get_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """预览商城 Skill"""
    skill = await marketplace.get_marketplace_skill_response(name, viewer_id=user.sub)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return skill


@router.get("/{name}/files")
async def list_marketplace_skill_files(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出商城 Skill 的所有文件路径"""
    paths = await marketplace.list_marketplace_file_paths(name)
    if not paths:
        skill = await marketplace.get_marketplace_skill(name)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
    return {"files": paths}


@router.get("/{name}/files/{path:path}")
async def get_marketplace_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """读取商城 Skill 的单个文件"""
    content = await marketplace.get_marketplace_file(name, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content}


@router.post("/{name}/install")
async def install_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """安装商城 Skill 到用户目录"""
    # 1. 检查商城 Skill 是否存在且激活
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if not marketplace_skill.is_active:
        raise HTTPException(status_code=403, detail="This skill has been deactivated")

    # 2. 检查用户是否已安装
    existing_toggle = await storage.get_toggle(name, user.sub)
    if existing_toggle:
        raise HTTPException(status_code=400, detail=f"Skill '{name}' already installed")

    # 3. 获取商城文件并复制到用户目录
    marketplace_files = await marketplace.get_marketplace_files(name)
    if marketplace_files:
        await storage.sync_skill_files(name, marketplace_files, user.sub)

    # 4. 创建开关记录
    await storage.upsert_toggle(
        name,
        user.sub,
        enabled=True,
        installed_from=InstalledFrom.MARKETPLACE,
    )

    # 5. 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{name}' installed successfully",
        "skill_name": name,
        "file_count": len(marketplace_files),
    }


@router.post("/{name}/update")
async def update_from_marketplace(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """从商城更新用户的 Skill（覆盖）"""
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")

    toggle = await storage.get_toggle(name, user.sub)
    if not toggle:
        raise HTTPException(
            status_code=400, detail=f"Skill '{name}' not installed. Install it first."
        )

    marketplace_files = await marketplace.get_marketplace_files(name)
    await storage.sync_skill_files(name, marketplace_files, user.sub)

    await storage.upsert_toggle(
        name,
        user.sub,
        enabled=True,
        installed_from=InstalledFrom.MARKETPLACE,
    )

    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{name}' updated from marketplace",
        "skill_name": name,
        "file_count": len(marketplace_files),
    }


# ==========================================
# Admin 操作（集成在商城路由中）
# ==========================================


@router.patch("/{name}/activate", response_model=MarketplaceSkillResponse)
async def set_marketplace_active(
    name: str,
    data: SetActiveRequest,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """激活或停用商城 Skill（admin 或创建者可操作）"""
    skill = await marketplace.get_marketplace_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if "skill:admin" not in (user.permissions or []) and skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="Only admin or creator can activate/deactivate")

    await marketplace.set_marketplace_active(name, data.is_active)
    response = await marketplace.get_marketplace_skill_response(name, viewer_id=user.sub)
    return response


@router.delete("/{name}")
async def delete_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """删除商城 Skill（admin 或创建者可操作，不影响已安装用户的本地副本）"""
    skill = await marketplace.get_marketplace_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if "skill:admin" not in (user.permissions or []) and skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="Only admin or creator can delete")

    deleted = await marketplace.delete_marketplace_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return {"message": f"Marketplace skill '{name}' deleted"}

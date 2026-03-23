# src/api/routes/admin/marketplace.py
"""
管理员商城 API

提供商城 Skill 的管理功能（上传/编辑/删除）。
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.api.deps import require_permissions
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.types import (
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
    MarketplaceSkillUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


# ==========================================
# 管理员商城 API
# ==========================================


@router.get("/", response_model=list[MarketplaceSkillResponse])
async def admin_list_marketplace_skills(
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出所有商城 Skills"""
    return await marketplace.list_marketplace_skills()


@router.post("/", response_model=MarketplaceSkillResponse, status_code=201)
async def admin_create_marketplace_skill(
    data: MarketplaceSkillCreate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """创建商城 Skill 元数据"""
    try:
        skill = await marketplace.create_marketplace_skill(data, user.sub)
        return MarketplaceSkillResponse(
            skill_name=skill.skill_name,
            description=skill.description,
            tags=skill.tags,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=skill.created_by,
            file_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}", response_model=MarketplaceSkillResponse)
async def admin_get_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取商城 Skill 详情"""
    skill = await marketplace.get_marketplace_skill_response(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return skill


@router.put("/{name}", response_model=MarketplaceSkillResponse)
async def admin_update_marketplace_skill(
    name: str,
    data: MarketplaceSkillUpdate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """更新商城 Skill 元数据"""
    skill = await marketplace.update_marketplace_skill(name, data)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")

    response = await marketplace.get_marketplace_skill_response(name)
    return response


@router.delete("/{name}")
async def admin_delete_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """删除商城 Skill（元数据和文件）"""
    deleted = await marketplace.delete_marketplace_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return {"message": f"Marketplace skill '{name}' deleted"}


@router.post("/{name}/upload", response_model=MarketplaceSkillResponse)
async def admin_upload_skill_files(
    name: str,
    file: UploadFile,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """上传 Skill 文件（ZIP）"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    try:
        content = await file.read()
        await marketplace.upload_from_zip(name, content, user.sub)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response = await marketplace.get_marketplace_skill_response(name)
    return response

# src/api/routes/marketplace.py
"""
用户商城 API

提供商城浏览、安装和直接发布功能。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.infra.skill.binary import parse_binary_ref
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import (
    InstalledFrom,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
)
from src.kernel.schemas.user import TokenPayload


def sanitize_file_path(path: str) -> str:
    """Sanitize file path to prevent path traversal."""
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != ".."]
    return "/".join(parts)


router = APIRouter()
MARKETPLACE_SKILL_MAX_FILES = 100
MARKETPLACE_SKILL_MAX_FILE_CHARS = 256_000
MARKETPLACE_SKILL_MAX_TOTAL_CHARS = 1_000_000


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


def _validate_marketplace_files_payload(files: dict[str, str]) -> None:
    if len(files) > MARKETPLACE_SKILL_MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Marketplace skill contains too many files (max {MARKETPLACE_SKILL_MAX_FILES})",
        )

    total_chars = 0
    for path, content in files.items():
        safe_path = sanitize_file_path(path)
        if safe_path != path:
            raise HTTPException(status_code=400, detail=f"Invalid file path: {path}")
        content_chars = len(str(content))
        if content_chars > MARKETPLACE_SKILL_MAX_FILE_CHARS:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Marketplace skill file is too large "
                    f"(max {MARKETPLACE_SKILL_MAX_FILE_CHARS} characters)"
                ),
            )
        total_chars += content_chars
        if total_chars > MARKETPLACE_SKILL_MAX_TOTAL_CHARS:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Marketplace skill files are too large "
                    f"(max {MARKETPLACE_SKILL_MAX_TOTAL_CHARS} total characters)"
                ),
            )


async def _load_marketplace_files_payload(
    *,
    name: str,
    marketplace: MarketplaceStorage,
    expected_paths: list[str],
) -> dict[str, str]:
    files: dict[str, str] = {}
    async for batch in marketplace.iter_marketplace_file_batches(name):
        files.update(batch)
    missing_paths = set(expected_paths) - set(files)
    if missing_paths:
        raise HTTPException(
            status_code=500,
            detail="Marketplace skill files are incomplete",
        )
    _validate_marketplace_files_payload(files)
    return files


# ==========================================
# 用户商城 API
# ==========================================


@router.get("/", response_model=list[MarketplaceSkillResponse])
async def list_marketplace_skills(
    tags: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出商城 Skills（所有用户：激活的 skill + 自己发布的含停用的）"""
    tag_list = tags.split(",") if tags else None
    skills = await marketplace.list_marketplace_skills(
        tags=tag_list,
        search=search,
        include_inactive=False,
        viewer_id=user.sub,
        skip=skip,
        limit=limit,
    )
    return skills


@router.get("/tags")
async def list_tags(
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取所有标签"""
    tags = await marketplace.list_all_tags()
    return {"tags": tags}


@router.post("/", response_model=MarketplaceSkillResponse, status_code=201)
async def create_marketplace_skill(
    data: MarketplaceCreateRequest,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """在商店创建 Skill（仅发布，不写入用户本地）"""
    if not data.files:
        raise HTTPException(status_code=400, detail="Skill must have at least one file")
    _validate_marketplace_files_payload(data.files)

    from src.infra.skill.parser import sanitize_skill_name

    safe_name = sanitize_skill_name(data.skill_name)

    try:
        create_data = MarketplaceSkillCreate(
            skill_name=safe_name,
            description=data.description,
            tags=data.tags,
            version=data.version,
        )
        await marketplace.create_marketplace_skill(create_data, user_id=user.sub)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        await marketplace.sync_marketplace_files(safe_name, data.files)
    except Exception:
        await marketplace.delete_marketplace_skill(safe_name)
        raise HTTPException(
            status_code=500, detail="Failed to sync files, marketplace entry rolled back"
        )

    response = await marketplace.get_marketplace_skill_response(safe_name, viewer_id=user.sub)
    return response


@router.get("/{name}", response_model=MarketplaceSkillResponse)
async def get_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """预览商城 Skill"""
    skill = await marketplace.get_marketplace_skill_response(name, viewer_id=user.sub)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return skill


@router.put("/{name}", response_model=MarketplaceSkillResponse)
async def update_marketplace_skill(
    name: str,
    data: MarketplaceCreateRequest,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """直接更新商店 Skill（仅创建者可操作）"""
    skill = await marketplace.get_marketplace_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="Only creator can update")

    if not data.files:
        raise HTTPException(status_code=400, detail="Skill must have at least one file")
    _validate_marketplace_files_payload(data.files)

    # 更新元数据
    from src.infra.skill.types import MarketplaceSkillUpdate

    update_data = MarketplaceSkillUpdate(
        description=data.description,
        tags=data.tags,
        version=data.version,
        is_active=True,
    )
    await marketplace.update_marketplace_skill(name, update_data)

    # 同步文件
    await marketplace.sync_marketplace_files(name, data.files)

    response = await marketplace.get_marketplace_skill_response(name, viewer_id=user.sub)
    return response


@router.get("/{name}/files")
async def list_marketplace_skill_files(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
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
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """读取商城 Skill 的单个文件"""
    safe_path = sanitize_file_path(path)
    if safe_path != path:
        raise HTTPException(status_code=400, detail="Invalid file path")
    content = await marketplace.get_marketplace_file(name, safe_path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    # 检查是否为二进制文件引用
    binary_ref = parse_binary_ref(content)
    if binary_ref:
        file_url = f"/api/upload/file/{binary_ref.storage_key}"
        return {
            "content": content,
            "is_binary": True,
            "url": file_url,
            "mime_type": binary_ref.mime_type,
            "size": binary_ref.size,
        }

    return {"content": content}


@router.post("/{name}/install")
async def install_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """安装商城 Skill 到用户目录"""
    # 1. 检查商城 Skill 是否存在且激活（创建者可安装自己已停用的 skill）
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if not marketplace_skill.is_active and marketplace_skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="This skill has been deactivated")

    # 2. 检查用户是否已安装（检查 __meta__ 或文件是否存在）
    existing_meta = await storage.get_skill_meta(name, user.sub)
    if existing_meta:
        if existing_meta.installed_from == InstalledFrom.MARKETPLACE:
            raise HTTPException(status_code=409, detail=f"Skill '{name}' already installed")

    # 3. 获取商城文件数量
    file_paths = await marketplace.list_marketplace_file_paths(name)
    if not file_paths:
        raise HTTPException(status_code=400, detail="Marketplace skill has no files")

    # 4. 先完整读取商城文件，再替换用户本地副本；避免读取失败时删除本地手动技能。
    try:
        files = await _load_marketplace_files_payload(
            name=name,
            marketplace=marketplace,
            expected_paths=file_paths,
        )
        await storage.sync_skill_files(name, files, user.sub)
        await storage.set_skill_meta(
            name,
            user.sub,
            installed_from=InstalledFrom.MARKETPLACE,
        )
        await storage.invalidate_user_cache(user.sub)
    except Exception as e:
        err_msg = str(e).lower()
        if "duplicate" in err_msg or "already" in err_msg:
            raise HTTPException(status_code=409, detail=f"Skill '{name}' already installed")
        raise

    return {
        "message": f"Skill '{name}' installed successfully",
        "skill_name": name,
        "file_count": len(files),
    }


@router.post("/{name}/update")
async def update_from_marketplace(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """从商城更新用户的 Skill（覆盖）"""
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if not marketplace_skill.is_active and marketplace_skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="This skill has been deactivated")

    # Check if skill is installed by checking __meta__
    meta = await storage.get_skill_meta(name, user.sub)
    if not meta:
        raise HTTPException(
            status_code=400, detail=f"Skill '{name}' not installed. Install it first."
        )
    if meta.installed_from != InstalledFrom.MARKETPLACE:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{name}' is a manual skill and cannot be updated from marketplace.",
        )

    file_paths = await marketplace.list_marketplace_file_paths(name)
    if not file_paths:
        raise HTTPException(status_code=400, detail="Marketplace skill has no files")

    files = await _load_marketplace_files_payload(
        name=name,
        marketplace=marketplace,
        expected_paths=file_paths,
    )
    await storage.sync_skill_files(name, files, user.sub)

    # Update __meta__ doc (preserve installed_from and published_marketplace_name)
    await storage.set_skill_meta(
        name,
        user.sub,
        installed_from=meta.installed_from,
        published_marketplace_name=meta.published_marketplace_name,
    )

    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{name}' updated from marketplace",
        "skill_name": name,
        "file_count": len(files),
    }


# ==========================================
# Admin 操作（集成在商城路由中）
# ==========================================


@router.patch("/{name}/activate", response_model=MarketplaceSkillResponse)
async def set_marketplace_active(
    name: str,
    data: SetActiveRequest,
    user: TokenPayload = Depends(require_permissions("marketplace:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """激活或停用商城 Skill（admin 或创建者可操作）"""
    skill = await marketplace.get_marketplace_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if "marketplace:admin" not in (user.permissions or []) and skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="Only admin or creator can activate/deactivate")

    await marketplace.set_marketplace_active(name, data.is_active)
    response = await marketplace.get_marketplace_skill_response(name, viewer_id=user.sub)
    return response


@router.delete("/{name}")
async def delete_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """删除商城 Skill（admin 或创建者可操作，不影响已安装用户的本地副本）"""
    skill = await marketplace.get_marketplace_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    if "marketplace:admin" not in (user.permissions or []) and skill.created_by != user.sub:
        raise HTTPException(status_code=403, detail="Only admin or creator can delete")

    deleted = await marketplace.delete_marketplace_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return {"message": f"Marketplace skill '{name}' deleted"}

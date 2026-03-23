"""
用户 Skills API

提供用户 Skills 的 CRUD 和 Toggle 操作。
Simplified architecture: files + toggle, no system/user split.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import UserSkill
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_storage() -> SkillStorage:
    return SkillStorage()


# ==========================================
# 用户 Skills API
# ==========================================


@router.get("/", response_model=list[UserSkill])
async def list_user_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """列出用户安装的所有 Skills"""
    skills = await storage.list_user_skills(user.sub)
    return [
        UserSkill(
            skill_name=s["skill_name"],
            enabled=s["enabled"],
            file_count=s["file_count"],
            installed_from=s.get("installed_from"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
        )
        for s in skills
    ]


@router.get("/{name}", response_model=UserSkill)
async def get_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """获取用户某个 Skill 的详细信息"""
    skills = await storage.list_user_skills(user.sub)
    for s in skills:
        if s["skill_name"] == name:
            files = await storage.get_skill_files(name, user.sub)
            return UserSkill(
                skill_name=name,
                enabled=s["enabled"],
                files=list(files.keys()),
                file_count=s["file_count"],
                installed_from=s.get("installed_from"),
                created_at=s.get("created_at"),
                updated_at=s.get("updated_at"),
            )
    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


@router.get("/{name}/files/{path:path}")
async def get_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """读取 Skill 的单个文件"""
    content = await storage.get_skill_file(name, path, user.sub)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content}


@router.put("/{name}/files/{path:path}")
async def update_skill_file(
    name: str,
    path: str,
    body: dict,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """更新 Skill 的单个文件"""
    content = body.get("content", "")
    await storage.set_skill_file(name, path, content, user.sub)

    # 确保开关记录存在（enabled=True）
    await storage.upsert_toggle(name, user.sub, enabled=True)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": "File updated"}


@router.delete("/{name}")
async def delete_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除（卸载）用户的 Skill"""
    # 使用原子操作同时删除文件和开关
    await storage.delete_skill_and_toggle(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"Skill '{name}' deleted"}


@router.patch("/{name}/toggle")
async def toggle_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """切换 Skill 的启用状态"""
    toggle = await storage.toggle_skill(name, user.sub)
    if not toggle:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    await storage.invalidate_user_cache(user.sub)

    status = "enabled" if toggle.enabled else "disabled"
    return {
        "skill_name": name,
        "enabled": toggle.enabled,
        "message": f"Skill '{name}' is now {status}",
    }

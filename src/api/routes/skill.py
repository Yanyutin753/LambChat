"""
用户 Skills API

提供用户 Skills 的 CRUD、Toggle 和发布到商店操作。
Simplified architecture: files + toggle, no system/user split.
"""

import io
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import (
    InstalledFrom,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
    MarketplaceSkillUpdate,
    PublishToMarketplaceRequest,
    SkillToggle,
    UserSkill,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_storage() -> SkillStorage:
    return SkillStorage()


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10MB


class UpdateFileRequest(BaseModel):
    """更新文件内容的请求"""

    content: str


def _parse_zip_skills(zip_content: bytes) -> list[tuple[str, dict[str, str]]]:
    """
    解析 ZIP 内容，找到所有 SKILL.md 文件，每个 SKILL.md 的上级文件夹作为一个独立 skill。

    Returns:
        list of (skill_name, files_dict) tuples
    """
    if len(zip_content) > MAX_ZIP_SIZE:
        raise ValueError("ZIP file too large (max 10MB)")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")

    try:
        names = zf.namelist()

        # 检测并去掉单顶层目录前缀（如 awesome-claude-skills/xxx → xxx）
        top_level = set()
        for n in names:
            parts = n.split("/")
            if parts[0]:
                top_level.add(parts[0])
        prefix = ""
        if len(top_level) == 1:
            top = list(top_level)[0]
            is_dir = any(n.startswith(top + "/") for n in names)
            if is_dir:
                prefix = top + "/"

        # 读取所有有效文件
        all_files: dict[str, str] = {}
        for name in names:
            if (
                name.endswith("/")
                or "__MACOSX" in name
                or name.endswith(".DS_Store")
                or name.endswith("Thumbs.db")
                or ".git/" in name
            ):
                continue
            try:
                raw = zf.read(name)
            except Exception:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            all_files[name] = text

        # 去掉顶层目录前缀
        if prefix:
            all_files = {
                k[len(prefix) :]: v
                for k, v in all_files.items()
                if k.startswith(prefix) and k[len(prefix) :]
            }

        # 找到所有 SKILL.md 的路径
        skill_md_paths = [p for p in all_files.keys() if p.split("/")[-1].lower() == "skill.md"]

        if not skill_md_paths:
            raise ValueError("No SKILL.md found in ZIP")

        skills: list[tuple[str, dict[str, str]]] = []

        for skill_md_path in skill_md_paths:
            # SKILL.md 所在的文件夹就是 skill 的根目录
            skill_root = skill_md_path.rsplit("/", 1)[0] if "/" in skill_md_path else ""
            skill_prefix = skill_root + "/" if skill_root else ""

            # 收集该 skill 根目录下的所有文件（相对路径）
            files: dict[str, str] = {}
            for fpath, content in all_files.items():
                if fpath.startswith(skill_prefix):
                    rel = fpath[len(skill_prefix) :]
                    if rel:
                        files[rel] = content

            # 优先使用文件夹名（路径安全），回退到 SKILL.md 的 name 字段
            skill_md_content = files.get("SKILL.md", all_files.get(skill_md_path, ""))
            skill_name = None
            if skill_root:
                skill_name = skill_root
            if not skill_name and skill_md_content:
                try:
                    from src.infra.skill.parser import parse_skill_md, sanitize_skill_name

                    parsed_name, _, _ = parse_skill_md(skill_md_content)
                    if parsed_name:
                        skill_name = sanitize_skill_name(parsed_name)
                except Exception:
                    pass
            if not skill_name:
                skill_name = "unnamed-skill"

            if files:
                skills.append((skill_name, files))

        if not skills:
            raise ValueError("No valid skills found in ZIP")

        return skills
    finally:
        zf.close()


# ==========================================
# 用户 Skills API
# ==========================================


@router.post("/upload/preview")
async def preview_zip_skills(
    file: UploadFile,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """预览 ZIP 文件中的 skills（不创建，返回 skill 列表供用户选择）"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read file content")

    try:
        skills = _parse_zip_skills(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 批量检查哪些已存在
    user_skills = await storage.list_user_skills(user.sub)
    existing_names = {s["skill_name"] for s in user_skills}

    skill_list = []
    for skill_name, files in skills:
        # 提取 description
        description = ""
        skill_md_content = files.get("SKILL.md", "")
        if skill_md_content:
            try:
                from src.infra.skill.parser import parse_skill_md

                _, desc, tags = parse_skill_md(skill_md_content)
                if desc:
                    description = desc
            except Exception:
                pass

        skill_list.append(
            {
                "name": skill_name,
                "description": description,
                "file_count": len(files),
                "files": sorted(files.keys()),
                "already_exists": skill_name in existing_names,
            }
        )

    return {
        "skill_count": len(skill_list),
        "skills": skill_list,
    }


@router.post("/upload", status_code=201)
async def upload_skill_from_zip(
    file: UploadFile,
    skill_names: Optional[str] = Form(default=None),
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """从 ZIP 文件上传创建技能（支持多个 SKILL.md，可选择性安装）"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read file content")

    try:
        skills = _parse_zip_skills(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 如果指定了 skill_names，只安装选中的
    if skill_names:
        name_set = set(n.strip() for n in skill_names.split(",") if n.strip())
        skills = [(n, f) for n, f in skills if n in name_set]

    created: list[dict] = []
    errors: list[dict] = []

    # 批量获取已存在 skill
    user_skills = await storage.list_user_skills(user.sub)
    existing_names = {s["skill_name"] for s in user_skills}

    for skill_name, files in skills:
        if skill_name in existing_names:
            errors.append({"name": skill_name, "reason": "already exists"})
            continue

        try:
            await storage.create_user_skill(
                skill_name, files, user.sub, installed_from=InstalledFrom.MANUAL
            )
            created.append({"name": skill_name, "file_count": len(files)})
        except Exception as e:
            errors.append({"name": skill_name, "reason": str(e)})

    if not created and errors:
        raise HTTPException(status_code=400, detail=f"All skills failed: {errors[0]['reason']}")

    return {
        "message": f"Created {len(created)} skill(s)",
        "created": created,
        "errors": errors,
        "skill_count": len(created),
    }


@router.get("/", response_model=list[UserSkill])
async def list_user_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出用户安装的所有 Skills（含发布状态）"""
    skills = await storage.list_user_skills(user.sub)
    if not skills:
        return []

    # 批量查询发布状态
    published_map = await marketplace.get_user_published_skills(user.sub)

    # 批量获取所有 SKILL.md 用于提取 description
    from src.infra.skill.parser import parse_skill_md

    skill_names = [s["skill_name"] for s in skills]
    skill_md_map = await storage.batch_get_skill_md_contents(skill_names, user.sub)
    description_map: dict[str, str] = {}
    tags_map: dict[str, list[str]] = {}
    for name, content in skill_md_map.items():
        if content:
            _, parsed_desc, parsed_tags = parse_skill_md(content)
            if parsed_desc:
                description_map[name] = parsed_desc
            if parsed_tags:
                tags_map[name] = parsed_tags

    return [
        UserSkill(
            skill_name=s["skill_name"],
            description=description_map.get(s["skill_name"], ""),
            tags=tags_map.get(s["skill_name"], []),
            files=s.get("file_paths", []),
            enabled=s["enabled"],
            file_count=s["file_count"],
            installed_from=s.get("installed_from"),
            published_marketplace_name=s.get("published_marketplace_name"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            is_published=bool(s.get("published_marketplace_name")),
            marketplace_is_active=published_map.get(
                s.get("published_marketplace_name") or s["skill_name"], {}
            ).get("is_active", True),
        )
        for s in skills
    ]


@router.get("/{name}", response_model=UserSkill)
async def get_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取用户某个 Skill 的详细信息"""
    files = await storage.get_skill_files(name, user.sub)
    if not files:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    toggle = await storage.get_toggle(name, user.sub)
    published_map = await marketplace.get_user_published_skills(user.sub)

    # 使用文件聚合统计获取时间戳，与 list_user_skills 保持一致
    file_stats = await storage.get_skill_file_stats(name, user.sub)

    def extract_metadata(files: dict[str, str]) -> tuple[str, list[str]]:
        from src.infra.skill.parser import parse_skill_md

        _, desc, tags = parse_skill_md(files.get("SKILL.md", ""))
        return desc, tags

    description, tags = extract_metadata(files)

    return UserSkill(
        skill_name=name,
        description=description,
        tags=tags,
        enabled=toggle.enabled if toggle else True,
        files=list(files.keys()),
        file_count=file_stats["file_count"],
        installed_from=toggle.installed_from if toggle else None,
        published_marketplace_name=toggle.published_marketplace_name if toggle else None,
        created_at=file_stats.get("created_at"),
        updated_at=file_stats.get("updated_at"),
        is_published=bool(toggle.published_marketplace_name) if toggle else name in published_map,
        marketplace_is_active=published_map.get(
            (toggle.published_marketplace_name if toggle else None) or name, {}
        ).get("is_active", True),
    )


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
    body: UpdateFileRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """更新 Skill 的单个文件"""
    content = body.content

    # 检查 toggle 是否已存在，以决定 enabled 状态
    existing_toggle = await storage.get_toggle(name, user.sub)
    is_new = existing_toggle is None

    await storage.set_skill_file(name, path, content, user.sub)

    # 新 skill 自动启用；已有 skill 保留用户设定的 enabled 状态
    enabled = True if is_new else (existing_toggle.enabled if existing_toggle else True)
    await storage.upsert_toggle(name, user.sub, enabled=enabled)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": "File updated"}


@router.delete("/{name}/files/{path:path}")
async def delete_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除 Skill 的单个文件"""
    # 检查 skill 和文件是否存在
    existing_paths = await storage.list_skill_file_paths(name, user.sub)
    if not existing_paths:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    if path not in existing_paths:
        raise HTTPException(status_code=404, detail=f"File '{path}' not found in skill '{name}'")

    await storage.delete_skill_file(name, path, user.sub)

    # 检查 skill 是否还有剩余文件，若无则清理 toggle 避免幽灵 skill
    remaining = await storage.list_skill_file_paths(name, user.sub)
    if not remaining:
        await storage.delete_toggle(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"File '{path}' deleted"}


@router.delete("/{name}")
async def delete_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """删除（卸载）用户的 Skill，同时停用商店发布（不删除，保留其他已安装用户的访问）"""
    toggle = await storage.get_toggle(name, user.sub)
    published_marketplace_name = toggle.published_marketplace_name if toggle else None
    existing_mp = await marketplace.get_marketplace_skill(published_marketplace_name or name)
    if existing_mp and existing_mp.created_by == user.sub:
        await marketplace.set_marketplace_active(existing_mp.skill_name, is_active=False)

    # 删除用户的文件和开关
    await storage.delete_skill_and_toggle(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"Skill '{name}' deleted"}


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""

    names: list[str]


class BatchToggleRequest(BaseModel):
    """批量切换请求"""

    names: list[str]
    enabled: bool


class ToggleRequest(BaseModel):
    """Toggle 请求（可选指定目标状态）"""

    enabled: Optional[bool] = None


# ==========================================
# 批量操作
# ==========================================


@router.post("/batch/delete")
async def batch_delete_skills(
    body: BatchDeleteRequest,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """批量删除 Skills"""
    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for name in body.names:
        try:
            toggle = await storage.get_toggle(name, user.sub)
            published_marketplace_name = toggle.published_marketplace_name if toggle else None
            existing_mp = await marketplace.get_marketplace_skill(
                published_marketplace_name or name
            )
            if existing_mp and existing_mp.created_by == user.sub:
                await marketplace.set_marketplace_active(existing_mp.skill_name, is_active=False)

            await storage.delete_skill_and_toggle(name, user.sub)
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "reason": str(e)})

    if deleted:
        await storage.invalidate_user_cache(user.sub)

    return {"deleted": deleted, "errors": errors}


@router.post("/batch/toggle")
async def batch_toggle_skills(
    body: BatchToggleRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """批量切换 Skills 的启用状态"""
    updated: list[str] = []
    errors: list[dict[str, str]] = []

    for name in body.names:
        try:
            await storage.upsert_toggle(name, user.sub, enabled=body.enabled)
            updated.append(name)
        except Exception as e:
            errors.append({"name": name, "reason": str(e)})

    if updated:
        await storage.invalidate_user_cache(user.sub)

    return {"updated": updated, "errors": errors}


@router.patch("/{name}/toggle")
async def toggle_user_skill(
    name: str,
    body: Optional[ToggleRequest] = None,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """切换或设置 Skill 的启用状态"""
    target_enabled = body.enabled if body else None

    if target_enabled is not None:
        # 直接设置目标状态
        toggle: SkillToggle = await storage.upsert_toggle(name, user.sub, enabled=target_enabled)
    else:
        # Flip 当前状态
        toggled = await storage.toggle_skill(name, user.sub)
        if not toggled:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        toggle = toggled

    await storage.invalidate_user_cache(user.sub)

    status = "enabled" if toggle and toggle.enabled else "disabled"
    return {
        "skill_name": name,
        "enabled": toggle.enabled,
        "message": f"Skill '{name}' is now {status}",
    }


# ==========================================
# 发布到商店
# ==========================================


@router.post("/{name}/publish", response_model=MarketplaceSkillResponse)
async def publish_skill_to_marketplace(
    name: str,
    data: Optional[PublishToMarketplaceRequest] = None,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """将用户的 Skill 发布到商店（支持多次发布更新）"""
    user_files = await storage.get_skill_files(name, user.sub)
    if not user_files:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    from src.infra.skill.parser import parse_skill_md as _parse_md
    from src.infra.skill.parser import sanitize_skill_name

    _, default_description, default_tags = _parse_md(user_files.get("SKILL.md", ""))
    target_name = sanitize_skill_name(
        (data.skill_name if data and data.skill_name else name).strip()
    )
    if not target_name:
        raise HTTPException(status_code=400, detail="Marketplace skill name is required")

    existing = await marketplace.get_marketplace_skill(target_name)
    if existing:
        if existing.created_by != user.sub:
            raise HTTPException(
                status_code=409,
                detail=f"Marketplace skill name '{target_name}' is already taken",
            )
        update_data = MarketplaceSkillUpdate(
            description=data.description
            if data and data.description is not None
            else default_description,
            tags=data.tags if data and data.tags is not None else existing.tags,
            version=data.version if data and data.version is not None else existing.version,
            is_active=True,
        )
        await marketplace.update_marketplace_skill(target_name, update_data)
    else:
        create_data = MarketplaceSkillCreate(
            skill_name=target_name,
            description=data.description
            if data and data.description is not None
            else default_description,
            tags=data.tags if data and data.tags is not None else default_tags,
            version=data.version if data and data.version is not None else "1.0.0",
        )
        await marketplace.create_marketplace_skill(create_data, user_id=user.sub)

    try:
        await marketplace.sync_marketplace_files(target_name, user_files)
        await storage.upsert_toggle(
            name,
            user.sub,
            enabled=True,
            published_marketplace_name=target_name,
        )
    except Exception:
        if not existing:
            await marketplace.delete_marketplace_skill(target_name)
        raise HTTPException(status_code=500, detail="Failed to sync files to marketplace")

    response = await marketplace.get_marketplace_skill_response(target_name)
    if not response:
        raise HTTPException(status_code=500, detail="Failed to publish skill")
    return response

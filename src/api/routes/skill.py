"""
用户 Skills API

提供用户 Skills 的 CRUD、Toggle 和发布到商店操作。
Simplified architecture: files + metadata (stored in __meta__ doc), enabled/disabled in user metadata.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.api.routes import skill_uploads
from src.api.routes.upload import _read_upload_file_limited
from src.infra.async_utils import run_blocking_io
from src.infra.skill.binary import guess_mime_type, parse_binary_ref_async
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage, normalize_skill_name_list
from src.infra.skill.types import (
    InstalledFrom,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
    MarketplaceSkillUpdate,
    PublishToMarketplaceRequest,
    UserSkill,
    UserSkillListResponse,
    UserSkillPreferenceResponse,
    UserSkillPreferenceUpdate,
)
from src.infra.user.storage import UserStorage
from src.kernel.config import settings  # noqa: F401 - compatibility for route tests/patching
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
_ZIP_MEMBER_MAX_BYTES: int | None = None
_ZIP_MAX_MEMBERS = 500
SKILL_BATCH_OPERATION_MAX_NAMES = 100
_skill_uploads_get_skill_upload_max_size = skill_uploads._get_skill_upload_max_size


def _get_skill_upload_max_size() -> tuple[int, int]:
    return _skill_uploads_get_skill_upload_max_size()


def _sync_zip_upload_limits() -> None:
    skill_uploads._ZIP_MEMBER_MAX_BYTES = _ZIP_MEMBER_MAX_BYTES
    skill_uploads._ZIP_MAX_MEMBERS = _ZIP_MAX_MEMBERS
    skill_uploads._get_skill_upload_max_size = _get_skill_upload_max_size


def _parse_zip_skill_preview(zip_content: bytes) -> list[dict]:
    _sync_zip_upload_limits()
    return skill_uploads._parse_zip_skill_preview(zip_content)


def _parse_zip_skills(
    zip_content: bytes,
) -> list[tuple[str, dict[str, str], dict[str, bytes]]]:
    _sync_zip_upload_limits()
    return skill_uploads._parse_zip_skills(zip_content)


def get_storage() -> SkillStorage:
    return SkillStorage()


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


def sanitize_file_path(path: str) -> str:
    """Sanitize file path to prevent path traversal."""
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != ".."]
    return "/".join(parts)


def _count_unique_skill_names(values: list[str]) -> int:
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
    return len(seen)


def _reject_oversized_skill_batch(values: list[str]) -> None:
    if _count_unique_skill_names(values) > SKILL_BATCH_OPERATION_MAX_NAMES:
        raise AppError(ErrorCode.SKILL_BATCH_LIMIT, args={"max": SKILL_BATCH_OPERATION_MAX_NAMES})


def _merge_disabled_skill_names(
    current: object,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[str]:
    remove_set = set(normalize_skill_name_list(remove or []))
    add_names = normalize_skill_name_list(add or [])
    ordered = [name for name in add_names if name not in remove_set]
    ordered.extend(
        name
        for name in normalize_skill_name_list(current)
        if name not in remove_set and name not in ordered
    )
    return normalize_skill_name_list(ordered)


class UpdateFileRequest(BaseModel):
    """更新文件内容的请求"""

    content: str


async def _parse_skill_md_offload(content: str) -> tuple[Optional[str], str, list[str]]:
    from src.infra.skill.parser import parse_skill_md

    return await run_blocking_io(parse_skill_md, content)


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
        raise AppError(ErrorCode.ZIP_REQUIRED)

    try:
        max_size_bytes, max_size_mb = _get_skill_upload_max_size()
        content = await _read_upload_file_limited(
            file,
            max_size_bytes=max_size_bytes,
            max_size_mb=max_size_mb,
            purpose="ZIP file",
        )
    except AppError:
        raise
    except Exception:
        raise AppError(ErrorCode.FILE_READ_FAILED)

    try:
        skill_list = await run_blocking_io(_parse_zip_skill_preview, content)
    except ValueError as e:
        raise AppError(ErrorCode.SKILL_ERROR, message=str(e))

    # 批量检查哪些已存在
    user_skills = await storage.list_user_skills(user.sub)
    existing_names = {s["skill_name"] for s in user_skills}

    for skill in skill_list:
        skill["already_exists"] = skill["name"] in existing_names

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
        raise AppError(ErrorCode.ZIP_REQUIRED)

    try:
        max_size_bytes, max_size_mb = _get_skill_upload_max_size()
        content = await _read_upload_file_limited(
            file,
            max_size_bytes=max_size_bytes,
            max_size_mb=max_size_mb,
            purpose="ZIP file",
        )
    except AppError:
        raise
    except Exception:
        raise AppError(ErrorCode.FILE_READ_FAILED)

    try:
        skills = await run_blocking_io(_parse_zip_skills, content)
    except ValueError as e:
        raise AppError(ErrorCode.SKILL_ERROR, message=str(e))

    # 如果指定了 skill_names，只安装选中的
    if skill_names:
        name_set = set(n.strip() for n in skill_names.split(",") if n.strip())
        skills = [(n, t, b) for n, t, b in skills if n in name_set]

    created: list[dict] = []
    errors: list[dict] = []

    # 批量获取已存在 skill
    user_skills = await storage.list_user_skills(user.sub)
    existing_names = {s["skill_name"] for s in user_skills}

    for skill_name, text_files, binary_files in skills:
        if skill_name in existing_names:
            errors.append({"name": skill_name, "reason": "already exists"})
            continue

        try:
            await storage.create_user_skill(
                skill_name,
                text_files,
                user.sub,
                installed_from=InstalledFrom.MANUAL,
                binary_files=binary_files if binary_files else None,
            )
            created.append(
                {
                    "name": skill_name,
                    "file_count": len(text_files) + len(binary_files),
                    "binary_file_count": len(binary_files),
                }
            )
        except Exception as e:
            errors.append({"name": skill_name, "reason": str(e)})

    if not created and errors:
        raise AppError(
            ErrorCode.SKILL_BATCH_ALL_FAILED, message=f"All skills failed: {errors[0]['reason']}"
        )

    return {
        "message": f"Created {len(created)} skill(s)",
        "created": created,
        "errors": errors,
        "skill_count": len(created),
    }


@router.get("/", response_model=UserSkillListResponse)
async def list_user_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = None,
    tags: list[str] | None = Query(None),
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出用户安装的所有 Skills（含发布状态）"""
    # Get disabled_skills from user metadata
    user_storage = UserStorage()
    user_doc = await user_storage.get_by_id(user.sub)
    disabled_skills: list[str] = []
    pinned_skill_names: list[str] = []
    favorite_skill_names: list[str] = []
    if user_doc and user_doc.metadata:
        disabled_skills = normalize_skill_name_list(user_doc.metadata.get("disabled_skills", []))
        pinned_skill_names = normalize_skill_name_list(
            user_doc.metadata.get("pinned_skill_names", [])
        )
        favorite_skill_names = normalize_skill_name_list(
            user_doc.metadata.get("favorite_skill_names", [])
        )
    available_tags = await storage.list_user_skill_tags(user.sub)

    skills = await storage.list_user_skills(
        user.sub,
        skip=skip,
        limit=limit,
        disabled_skills=disabled_skills,
        pinned_skill_names=pinned_skill_names,
        favorite_skill_names=favorite_skill_names,
        q=q,
        tags=tags,
    )
    total = await storage.count_user_skills(user.sub, q=q, tags=tags)
    disabled_count = await storage.count_disabled_user_skills(
        user.sub,
        disabled_skills=disabled_skills,
        q=q,
        tags=tags,
    )
    enabled_count = total - disabled_count
    if not skills:
        return UserSkillListResponse(
            skills=[],
            total=total,
            enabled_count=max(enabled_count, 0),
            skip=skip,
            limit=limit,
            available_tags=available_tags,
        )

    skill_names = [s["skill_name"] for s in skills]
    # 批量查询当前页发布状态，避免按用户拉取全部发布记录
    published_map = await marketplace.get_user_published_skills(
        user.sub,
        skill_names=skill_names,
    )

    # 批量获取所有 SKILL.md 用于提取 description
    skill_md_map = await storage.batch_get_skill_md_contents(skill_names, user.sub)
    description_map: dict[str, str] = {}
    tags_map: dict[str, list[str]] = {}
    for name, content in skill_md_map.items():
        if content:
            _, parsed_desc, parsed_tags = await _parse_skill_md_offload(content)
            if parsed_desc:
                description_map[name] = parsed_desc
            if parsed_tags:
                tags_map[name] = parsed_tags

    items = [
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
            is_pinned=bool(s.get("is_pinned")),
            is_favorite=bool(s.get("is_favorite")),
        )
        for s in skills
    ]
    return UserSkillListResponse(
        skills=items,
        total=total,
        enabled_count=max(enabled_count, 0),
        skip=skip,
        limit=limit,
        available_tags=available_tags,
    )


@router.get("/{name}", response_model=UserSkill)
async def get_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取用户某个 Skill 的详细信息"""
    file_paths = await storage.list_skill_file_paths(name, user.sub)
    if not file_paths:
        raise AppError(ErrorCode.SKILL_NOT_FOUND, args={"name": name})

    # Get disabled_skills from user metadata
    user_storage = UserStorage()
    user_doc = await user_storage.get_by_id(user.sub)
    disabled_skills = set()
    if user_doc and user_doc.metadata:
        disabled_skills = set(
            normalize_skill_name_list(user_doc.metadata.get("disabled_skills", []))
        )
    pinned_skill_names = (
        set(normalize_skill_name_list((user_doc.metadata or {}).get("pinned_skill_names", [])))
        if user_doc
        else set()
    )
    favorite_skill_names = (
        set(normalize_skill_name_list((user_doc.metadata or {}).get("favorite_skill_names", [])))
        if user_doc
        else set()
    )
    enabled = name not in disabled_skills

    # Get metadata from __meta__ doc
    meta = await storage.get_skill_meta(name, user.sub)
    published_map = await marketplace.get_user_published_skills(
        user.sub,
        skill_names=[name],
    )

    # 使用文件聚合统计获取时间戳，与 list_user_skills 保持一致
    file_stats = await storage.get_skill_file_stats(name, user.sub)

    async def extract_metadata() -> tuple[str, list[str]]:
        skill_md = await storage.get_skill_file(name, "SKILL.md", user.sub)
        _, desc, tags = await _parse_skill_md_offload(skill_md or "")
        return desc, tags

    description, tags = await extract_metadata()

    return UserSkill(
        skill_name=name,
        description=description,
        tags=tags,
        enabled=enabled,
        files=file_paths,
        file_count=file_stats["file_count"],
        installed_from=meta.installed_from.value if meta else None,
        published_marketplace_name=meta.published_marketplace_name if meta else None,
        created_at=file_stats.get("created_at"),
        updated_at=file_stats.get("updated_at"),
        is_published=(bool(meta.published_marketplace_name) if meta else name in published_map),
        marketplace_is_active=published_map.get(
            (meta.published_marketplace_name if meta else None) or name, {}
        ).get("is_active", True),
        is_pinned=name in pinned_skill_names,
        is_favorite=name in favorite_skill_names,
    )


@router.get("/{name}/files/{path:path}")
async def get_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """读取 Skill 的单个文件（文本内容或二进制文件元数据）"""
    safe_path = sanitize_file_path(path)
    if safe_path != path:
        raise AppError(ErrorCode.INVALID_FILE_PATH)
    content = await storage.get_skill_file(name, safe_path, user.sub)
    if content is None:
        raise AppError(ErrorCode.FILE_NOT_FOUND)

    # 检查是否为二进制文件引用
    binary_ref = await parse_binary_ref_async(content)
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


@router.put("/{name}/files/{path:path}")
async def update_skill_file(
    name: str,
    path: str,
    body: UpdateFileRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """更新 Skill 的单个文件"""
    safe_path = sanitize_file_path(path)
    if safe_path != path:
        raise AppError(ErrorCode.INVALID_FILE_PATH)
    content = body.content

    # 检查 __meta__ 是否已存在，以决定是否是新 skill
    existing_meta = await storage.get_skill_meta(name, user.sub)
    is_new = existing_meta is None

    await storage.set_skill_file(name, safe_path, content, user.sub)

    # 新 skill 自动创建 __meta__
    if is_new:
        await storage.set_skill_meta(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": "File updated"}


@router.put("/{name}/binary-files/{path:path}")
async def upload_skill_binary_file(
    name: str,
    path: str,
    file: UploadFile,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """上传二进制文件到 Skill（自动存储到 S3/本地存储）"""
    safe_path = sanitize_file_path(path)
    if safe_path != path:
        raise AppError(ErrorCode.INVALID_FILE_PATH)

    max_file_size, max_file_size_mb = _get_skill_upload_max_size()
    data = await _read_upload_file_limited(
        file,
        max_size_bytes=max_file_size,
        max_size_mb=max_file_size_mb,
        purpose="Binary file",
    )

    if len(data) == 0:
        raise AppError(ErrorCode.EMPTY_FILE)

    # 检测 MIME 类型
    mime_type = file.content_type or guess_mime_type(safe_path)

    # 检查 skill 是否已存在
    existing_meta = await storage.get_skill_meta(name, user.sub)
    is_new = existing_meta is None

    try:
        binary_ref = await storage.set_skill_binary_file(
            name, safe_path, data, user.sub, mime_type=mime_type
        )
    except Exception as e:
        raise AppError(ErrorCode.SKILL_BINARY_UPLOAD_FAILED, message=str(e))

    # 新 skill 自动创建 __meta__
    if is_new:
        await storage.set_skill_meta(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {
        "message": "Binary file uploaded",
        "storage_key": binary_ref.storage_key,
        "url": f"/api/upload/file/{binary_ref.storage_key}",
        "mime_type": binary_ref.mime_type,
        "size": binary_ref.size,
    }


@router.delete("/{name}/files/{path:path}")
async def delete_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除 Skill 的单个文件"""
    safe_path = sanitize_file_path(path)
    if safe_path != path:
        raise AppError(ErrorCode.INVALID_FILE_PATH)
    # 检查 skill 和文件是否存在
    existing_paths = await storage.list_skill_file_paths(name, user.sub)
    if not existing_paths:
        raise AppError(ErrorCode.SKILL_NOT_FOUND, args={"name": name})
    if safe_path not in existing_paths:
        raise AppError(ErrorCode.SKILL_FILE_NOT_FOUND, args={"path": path, "skill": name})

    await storage.delete_skill_file(name, safe_path, user.sub)

    # 检查 skill 是否还有剩余文件（排除 __meta__），若无则清理 __meta__ 避免幽灵 skill
    remaining = await storage.list_skill_file_paths(name, user.sub)
    if not remaining:
        await storage.delete_skill_meta(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"File '{path}' deleted"}


@router.delete("/{name}")
async def delete_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除（卸载）用户的 Skill（不影响商店发布状态）"""
    await storage.delete_skill_and_meta(name, user.sub)

    # 清理 disabled_skills 中的条目（如果有）
    user_storage = UserStorage()
    user_doc = await user_storage.get_by_id(user.sub)
    if user_doc and user_doc.metadata:
        disabled = _merge_disabled_skill_names(
            user_doc.metadata.get("disabled_skills", []),
            remove=[name],
        )
        await user_storage.update_metadata(user.sub, {"disabled_skills": disabled})

    await storage.remove_user_skill_preference(user.sub, [name])

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


async def _ensure_skill_exists(storage: SkillStorage, skill_name: str, user_id: str) -> None:
    """Reject toggle operations for non-existent skills to avoid ghost disabled state."""
    paths = await storage.list_skill_file_paths(skill_name, user_id)
    if not paths:
        raise AppError(ErrorCode.SKILL_NOT_FOUND, args={"name": skill_name})


@router.patch("/{name}/preference", response_model=UserSkillPreferenceResponse)
async def update_skill_preference(
    name: str,
    preference: UserSkillPreferenceUpdate,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """更新当前用户对 Skill 的置顶/收藏偏好。"""
    await _ensure_skill_exists(storage, name, user.sub)
    updated = await storage.update_user_preference(
        user_id=user.sub,
        skill_name=name,
        update=preference.model_dump(mode="json"),
    )
    return UserSkillPreferenceResponse(skill_name=name, **updated)


# ==========================================
# 批量操作
# ==========================================


@router.post("/batch/delete")
async def batch_delete_skills(
    body: BatchDeleteRequest,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
):
    """批量删除 Skills"""
    _reject_oversized_skill_batch(body.names)
    names = normalize_skill_name_list(body.names)
    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for name in names:
        try:
            await storage.delete_skill_and_meta(name, user.sub)
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "reason": str(e)})

    if deleted:
        await storage.invalidate_user_cache(user.sub)

        # 清理 disabled_skills 中已删除的 skill
        user_storage = UserStorage()
        user_doc = await user_storage.get_by_id(user.sub)
        if user_doc and user_doc.metadata:
            disabled = _merge_disabled_skill_names(
                user_doc.metadata.get("disabled_skills", []),
                remove=deleted,
            )
            await user_storage.update_metadata(user.sub, {"disabled_skills": disabled})
        await storage.remove_user_skill_preference(user.sub, deleted)

    return {"deleted": deleted, "errors": errors}


@router.post("/batch/toggle")
async def batch_toggle_skills(
    body: BatchToggleRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """批量切换 Skills 的启用状态"""
    missing_names = []
    _reject_oversized_skill_batch(body.names)
    names = normalize_skill_name_list(body.names)
    for name in names:
        try:
            await _ensure_skill_exists(storage, name, user.sub)
        except AppError:
            missing_names.append(name)

    if missing_names:
        missing = ", ".join(sorted(missing_names))
        raise AppError(ErrorCode.SKILLS_NOT_FOUND, args={"missing": str(missing)})

    # Get current disabled_skills from user metadata
    user_storage = UserStorage()
    user_doc = await user_storage.get_by_id(user.sub)
    if user_doc is None:
        raise AppError(ErrorCode.USER_NOT_FOUND)

    if body.enabled:
        disabled = _merge_disabled_skill_names(
            (user_doc.metadata or {}).get("disabled_skills", []),
            remove=names,
        )
    else:
        disabled = _merge_disabled_skill_names(
            (user_doc.metadata or {}).get("disabled_skills", []),
            add=names,
        )

    # Invalidate cache first, then update metadata
    # This ensures clients see fresh data even if metadata update fails
    await storage.invalidate_user_cache(user.sub)
    await user_storage.update_metadata(
        user.sub,
        {"disabled_skills": disabled},
    )

    return {"updated": names, "errors": []}


@router.patch("/{name}/toggle")
async def toggle_user_skill(
    name: str,
    body: Optional[ToggleRequest] = None,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """切换或设置 Skill 的启用状态"""
    await _ensure_skill_exists(storage, name, user.sub)

    # Get current disabled_skills from user metadata
    user_storage = UserStorage()
    user_doc = await user_storage.get_by_id(user.sub)
    if user_doc is None:
        raise AppError(ErrorCode.USER_NOT_FOUND)
    current_disabled = normalize_skill_name_list(
        (user_doc.metadata or {}).get("disabled_skills", [])
    )

    target_enabled = body.enabled if body else None

    if target_enabled is not None:
        # 直接设置目标状态
        if target_enabled:
            disabled = _merge_disabled_skill_names(current_disabled, remove=[name])
        else:
            disabled = _merge_disabled_skill_names(current_disabled, add=[name])
    else:
        # Flip 当前状态
        if name in current_disabled:
            disabled = _merge_disabled_skill_names(current_disabled, remove=[name])
        else:
            disabled = _merge_disabled_skill_names(current_disabled, add=[name])

    # Invalidate cache first, then update metadata
    await storage.invalidate_user_cache(user.sub)
    await user_storage.update_metadata(
        user.sub,
        {"disabled_skills": disabled},
    )

    is_enabled = name not in disabled
    status = "enabled" if is_enabled else "disabled"
    return {
        "skill_name": name,
        "enabled": is_enabled,
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
        raise AppError(ErrorCode.SKILL_NOT_FOUND, args={"name": name})

    from src.infra.skill.parser import parse_skill_md as _parse_md
    from src.infra.skill.parser import sanitize_skill_name

    _, default_description, default_tags = _parse_md(user_files.get("SKILL.md", ""))
    target_name = sanitize_skill_name(
        (data.skill_name if data and data.skill_name else name).strip()
    )
    if not target_name:
        raise AppError(ErrorCode.MARKETPLACE_SKILL_NAME_REQUIRED)

    existing = await marketplace.get_marketplace_skill(target_name)
    if existing:
        if existing.created_by != user.sub:
            raise AppError(ErrorCode.MARKETPLACE_NAME_TAKEN, args={"name": target_name})
        update_data = MarketplaceSkillUpdate(
            description=(
                data.description if data and data.description is not None else default_description
            ),
            tags=data.tags if data and data.tags is not None else existing.tags,
            version=(data.version if data and data.version is not None else existing.version),
            is_active=True,
        )
        await marketplace.update_marketplace_skill(target_name, update_data)
    else:
        create_data = MarketplaceSkillCreate(
            skill_name=target_name,
            description=(
                data.description if data and data.description is not None else default_description
            ),
            tags=data.tags if data and data.tags is not None else default_tags,
            version=data.version if data and data.version is not None else "1.0.0",
        )
        await marketplace.create_marketplace_skill(create_data, user_id=user.sub)

    try:
        await marketplace.sync_marketplace_files(target_name, user_files)
        # Update __meta__ doc with published_marketplace_name
        meta = await storage.get_skill_meta(name, user.sub)
        await storage.set_skill_meta(
            name,
            user.sub,
            installed_from=meta.installed_from if meta else InstalledFrom.MANUAL,
            published_marketplace_name=target_name,
        )
    except Exception:
        if not existing:
            await marketplace.delete_marketplace_skill(target_name)
        raise AppError(ErrorCode.MARKETPLACE_SYNC_FAILED)

    response = await marketplace.get_marketplace_skill_response(target_name)
    if not response:
        raise AppError(ErrorCode.PUBLISH_SKILL_FAILED)
    return response

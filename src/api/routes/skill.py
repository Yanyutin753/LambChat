"""
用户 Skills API

提供用户 Skills 的 CRUD 和 Toggle 操作。
Simplified architecture: files + toggle, no system/user split.
"""

import io
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.api.deps import require_permissions
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import UserSkill
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_storage() -> SkillStorage:
    return SkillStorage()


MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10MB


def _parse_zip_content(zip_content: bytes) -> tuple[str, dict[str, str]]:
    """
    解析 ZIP 内容，提取 skill 名称和文件。

    Returns:
        tuple: (skill_name, files_dict)
    """
    if len(zip_content) > MAX_ZIP_SIZE:
        raise ValueError("ZIP file too large (max 10MB)")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")

    try:
        all_files: dict[str, str] = {}

        names = zf.namelist()
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

        for name in names:
            if (
                name.endswith("/")
                or "__MACOSX" in name
                or name.endswith(".DS_Store")
                or name.endswith("Thumbs.db")
                or ".git/" in name
            ):
                continue
            if name.startswith(prefix):
                rel_path = name[len(prefix) :]
            else:
                rel_path = name
            if not rel_path:
                continue

            try:
                raw = zf.read(name)
            except Exception:
                continue

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            all_files[rel_path] = text

        # 从 SKILL.md 提取 skill 名称
        skill_name = None
        skill_md = all_files.get("SKILL.md", "")
        for line in skill_md.splitlines():
            if line.startswith("name:"):
                skill_name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                break

        # 如果没有 name 字段，使用顶级目录名或第一个文件名
        if not skill_name:
            if prefix:
                skill_name = prefix.rstrip("/")
            elif all_files:
                first_file = list(all_files.keys())[0]
                skill_name = first_file.split("/")[0] if "/" in first_file else first_file

        if not skill_name:
            raise ValueError("Cannot determine skill name from ZIP")

        return skill_name, all_files
    finally:
        zf.close()


# ==========================================
# 用户 Skills API
# ==========================================


@router.post("/upload", status_code=201)
async def upload_skill_from_zip(
    file: UploadFile,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """从 ZIP 文件上传创建技能"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read file content")

    try:
        skill_name, files = _parse_zip_content(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 检查是否已存在
    existing = await storage.get_skill_files(skill_name, user.sub)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{skill_name}' already exists"
        )

    # 创建技能文件
    for file_path, file_content in files.items():
        await storage.set_skill_file(skill_name, file_path, file_content, user.sub)

    # 创建开关记录
    await storage.upsert_toggle(skill_name, user.sub, enabled=True)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{skill_name}' created",
        "skill_name": skill_name,
        "file_count": len(files),
    }


@router.get("/", response_model=list[UserSkill])
async def list_user_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """列出用户安装的所有 Skills"""
    skills = await storage.list_user_skills(user.sub)
    if not skills:
        return []

    # 批量获取所有 skill 的文件
    skill_keys = [(s["skill_name"], user.sub) for s in skills]
    all_files = await storage.batch_get_skill_files(skill_keys)

    def extract_description(files: dict[str, str]) -> str:
        """从 SKILL.md 提取 description"""
        content = files.get("SKILL.md", "")
        for line in content.splitlines():
            if line.startswith("description:"):
                return line.split("description:", 1)[1].strip().strip('"').strip("'")
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    return [
        UserSkill(
            skill_name=s["skill_name"],
            description=extract_description(all_files.get((s["skill_name"], user.sub), {})),
            files=list(all_files.get((s["skill_name"], user.sub), {}).keys()),
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


@router.delete("/{name}/files/{path:path}")
async def delete_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除 Skill 的单个文件"""
    await storage.delete_skill_file(name, path, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"File '{path}' deleted"}


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

# src/api/routes/plugin.py
"""插件中心 API。

统一插件体系：一个插件可携带技能负载、MCP server 声明与可选角色预设。
权限沿用 marketplace 三档（read / publish / admin）。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.deps import require_permissions
from src.infra.logging import get_logger
from src.infra.mcp.storage import MCPStorage
from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.plugin.constants import (
    PLUGIN_FILE_MAX_CHARS,
    PLUGIN_FILES_PER_SKILL_LIMIT,
)
from src.infra.plugin.materialize import (
    delete_plugin_mcp,
    disable_plugin_mcp,
    materialize_plugin_mcp,
)
from src.infra.plugin.storage import PluginStorage
from src.infra.plugin.types import (
    PluginCreate,
    PluginInstalledListResponse,
    PluginInstallResponse,
    PluginListResponse,
    PluginResponse,
    PluginStatus,
    PluginTagsResponse,
    PluginUpdate,
)
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import InstalledFrom
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.persona_preset import PersonaPresetCreate
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()

PLUGIN_TOTAL_MAX_CHARS = 1_000_000


def get_plugin_storage() -> PluginStorage:
    return PluginStorage()


def get_skill_storage() -> SkillStorage:
    return SkillStorage()


def get_mcp_storage_dep() -> MCPStorage:
    return MCPStorage()


class SetPluginActiveRequest(BaseModel):
    """Admin 激活/停用插件请求。"""

    is_active: bool


class PluginSkillFilesRequest(BaseModel):
    """写入插件技能负载文件。"""

    files: dict[str, str] = {}


def _require_owner_or_admin(doc: dict, *, user_id: str, is_admin: bool) -> None:
    if is_admin:
        return
    if doc.get("created_by") != user_id:
        raise AppError(ErrorCode.PLUGIN_NO_EDIT_PERMISSION, args={"name": doc.get("name", "")})


def _validate_plugin_files(files: dict[str, str]) -> None:
    if not files:
        raise AppError(ErrorCode.PLUGIN_INVALID_PAYLOAD, args={"reason": "files required"})
    if len(files) > PLUGIN_FILES_PER_SKILL_LIMIT:
        raise AppError(
            ErrorCode.PLUGIN_INVALID_PAYLOAD,
            args={"reason": f"too many files (max {PLUGIN_FILES_PER_SKILL_LIMIT})"},
        )
    total = 0
    for path, content in files.items():
        chars = len(str(content))
        if chars > PLUGIN_FILE_MAX_CHARS:
            raise AppError(
                ErrorCode.PLUGIN_INVALID_PAYLOAD,
                args={"reason": f"file {path} too large"},
            )
        total += chars
        if total > PLUGIN_TOTAL_MAX_CHARS:
            raise AppError(
                ErrorCode.PLUGIN_INVALID_PAYLOAD,
                args={"reason": "payload too large"},
            )


async def _validate_plugin_payload_ready(doc: dict, storage: PluginStorage) -> None:
    """激活前校验：每个声明的技能负载须至少有一个文件（防呆空技能）。"""
    for skill in doc.get("skills", []) or []:
        skill_name = skill.get("skill_name")
        if not skill_name:
            continue
        paths = await storage.list_skill_file_paths(doc["name"], skill_name)
        if not paths:
            raise AppError(
                ErrorCode.PLUGIN_INVALID_PAYLOAD,
                args={"reason": f"skill '{skill_name}' has no payload files"},
            )


async def _sync_plugin_skills_to_user(
    plugin_doc: dict,
    storage: PluginStorage,
    skill_storage: SkillStorage,
    user_id: str,
) -> list[str]:
    """把插件技能负载整树同步到用户技能库，返回技能名列表。"""
    installed: list[str] = []
    for skill in plugin_doc.get("skills", []) or []:
        skill_name = skill.get("skill_name")
        if not skill_name:
            continue
        files: dict[str, str] = {}
        async for batch in storage.iter_skill_file_batches(plugin_doc["name"], skill_name):
            files.update(batch)
        if not files:
            continue
        await skill_storage.sync_skill_files(skill_name, files, user_id)
        await skill_storage.set_skill_meta(skill_name, user_id, installed_from=InstalledFrom.PLUGIN)
        installed.append(skill_name)
    if installed:
        await skill_storage.invalidate_user_cache(user_id)
    return installed


async def _install_plugin_persona(
    plugin_doc: dict,
    user_id: str,
) -> bool:
    """把插件角色负载复制为用户私有 persona 草稿。"""
    persona = plugin_doc.get("persona")
    if not isinstance(persona, dict) or not persona.get("system_prompt"):
        return False
    manager = PersonaPresetManager()
    await manager.create_preset(
        PersonaPresetCreate(
            name=persona.get("name", plugin_doc["name"]),
            description=persona.get("description", ""),
            avatar=persona.get("avatar"),
            tags=persona.get("tags", []),
            system_prompt=persona["system_prompt"],
            starter_prompts=persona.get("starter_prompts", []),
        ),
        user_id=user_id,
        is_admin=False,
    )
    return True


# ==========================================
# 用户侧：浏览 / 安装
# ==========================================


@router.get("/", response_model=PluginListResponse)
async def list_plugins(
    tags: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, ge=1, le=100),
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """列出平台插件（active + 自己投稿的草稿/停用项）。"""
    tag_list = tags.split(",") if tags else None
    plugins, total = await storage.list_plugins(
        tags=tag_list,
        search=search,
        include_inactive=False,
        viewer_id=user.sub,
        user_id=user.sub,
        skip=skip,
        limit=limit,
    )
    return PluginListResponse(plugins=plugins, total=total, skip=skip, limit=limit)


@router.get("/tags", response_model=PluginTagsResponse)
async def list_plugin_tags(
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    return PluginTagsResponse(tags=await storage.list_tags())


@router.get("/installed", response_model=PluginInstalledListResponse)
async def list_installed_plugins(
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    installs = await storage.list_installs(user.sub)
    return PluginInstalledListResponse(installs=installs, total=len(installs))


@router.get("/{name}", response_model=PluginResponse)
async def get_plugin(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    plugin = await storage.get_plugin_response(name, viewer_id=user.sub, user_id=user.sub)
    if not plugin:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    return plugin


@router.get("/{name}/skills/{skill_name}/files")
async def list_plugin_skill_files(
    name: str,
    skill_name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """列出插件技能负载文件路径。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    paths = await storage.list_skill_file_paths(name, skill_name)
    return {"plugin_name": name, "skill_name": skill_name, "file_paths": paths}


@router.get("/{name}/skills/{skill_name}/files/{file_path:path}")
async def read_plugin_skill_file(
    name: str,
    skill_name: str,
    file_path: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """读取插件技能负载单文件。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    content = await storage.read_skill_file(name, skill_name, file_path)
    if content is None:
        raise AppError(ErrorCode.PLUGIN_FILE_NOT_FOUND, args={"name": name, "path": file_path})
    return {"content": content}


@router.post("/{name}/install", response_model=PluginInstallResponse)
async def install_plugin(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
    skill_storage: SkillStorage = Depends(get_skill_storage),
):
    """安装插件：技能负载落用户技能库，角色负载复制为私有草稿。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    if doc.get("status") != PluginStatus.ACTIVE.value:
        raise AppError(ErrorCode.PLUGIN_INACTIVE, args={"name": name})

    existing = await storage.get_install(user.sub, name)
    if existing:
        raise AppError(ErrorCode.PLUGIN_ALREADY_INSTALLED, args={"name": name})

    installed_skills = await _sync_plugin_skills_to_user(doc, storage, skill_storage, user.sub)
    persona_created = await _install_plugin_persona(doc, user.sub)

    await storage.upsert_install(user.sub, name, doc.get("version", "1.0.0"))
    await storage.increment_install_count(name)
    return PluginInstallResponse(
        message=f"Plugin '{name}' installed successfully",
        plugin_name=name,
        version=doc.get("version", "1.0.0"),
        installed_skills=installed_skills,
        persona_created=persona_created,
    )


@router.post("/{name}/update", response_model=PluginInstallResponse)
async def update_plugin_install(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
    skill_storage: SkillStorage = Depends(get_skill_storage),
):
    """从平台拉取插件最新版并覆盖本地技能副本。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    if not await storage.get_install(user.sub, name):
        raise AppError(ErrorCode.PLUGIN_NOT_INSTALLED, args={"name": name})
    if doc.get("status") != PluginStatus.ACTIVE.value:
        raise AppError(ErrorCode.PLUGIN_INACTIVE, args={"name": name})

    installed_skills = await _sync_plugin_skills_to_user(doc, storage, skill_storage, user.sub)
    await storage.upsert_install(user.sub, name, doc.get("version", "1.0.0"))
    return PluginInstallResponse(
        message=f"Plugin '{name}' updated successfully",
        plugin_name=name,
        version=doc.get("version", "1.0.0"),
        installed_skills=installed_skills,
    )


@router.post("/{name}/uninstall")
async def uninstall_plugin(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:read")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """卸载插件（移除安装记录；技能/角色副本由用户在既有面板管理）。"""
    if not await storage.delete_install(user.sub, name):
        raise AppError(ErrorCode.PLUGIN_NOT_INSTALLED, args={"name": name})
    return {"message": f"Plugin '{name}' uninstalled", "plugin_name": name}


# ==========================================
# 投稿 / 管理
# ==========================================


@router.post("/", response_model=PluginResponse)
async def create_plugin(
    data: PluginCreate,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """创建插件（投稿为 draft；admin 可携带 activate=true 直接上架）。"""
    if await storage.plugin_name_exists(data.name):
        raise AppError(ErrorCode.PLUGIN_NAME_EXISTS, args={"name": data.name})

    is_admin = "marketplace:admin" in (user.permissions or [])
    status = PluginStatus.ACTIVE if (data.activate and is_admin) else PluginStatus.DRAFT
    doc = data.model_dump(mode="json", exclude={"activate"})
    doc["status"] = status.value
    doc["created_by"] = user.sub
    created = await storage.create_plugin(doc)

    if status is PluginStatus.ACTIVE:
        await _validate_plugin_payload_ready(created, storage)
        await materialize_plugin_mcp(created, admin_user_id=user.sub)
    return await storage.get_plugin_response(data.name, viewer_id=user.sub, user_id=user.sub)


@router.put("/{name}/skills/{skill_name}/files")
async def write_plugin_skill_files(
    name: str,
    skill_name: str,
    data: PluginSkillFilesRequest,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """写入/替换插件技能负载文件（创建者或 admin）。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    _require_owner_or_admin(
        doc, user_id=user.sub, is_admin="marketplace:admin" in (user.permissions or [])
    )
    _validate_plugin_files(data.files)
    await storage.write_skill_files(name, skill_name, data.files)
    return {"message": "ok", "plugin_name": name, "skill_name": skill_name}


@router.put("/{name}", response_model=PluginResponse)
async def update_plugin(
    name: str,
    data: PluginUpdate,
    user: TokenPayload = Depends(require_permissions("marketplace:publish")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """更新插件元数据/负载（创建者或 admin；版本自增语义由调用方传入）。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    is_admin = "marketplace:admin" in (user.permissions or [])
    _require_owner_or_admin(doc, user_id=user.sub, is_admin=is_admin)

    update = data.model_dump(mode="json", exclude_unset=True)
    updated = await storage.update_plugin(name, update)
    if updated and updated.get("status") == PluginStatus.ACTIVE.value:
        await materialize_plugin_mcp(updated, admin_user_id=user.sub)
    return await storage.get_plugin_response(name, viewer_id=user.sub, user_id=user.sub)


@router.patch("/{name}/activate", response_model=PluginResponse)
async def activate_plugin(
    name: str,
    data: SetPluginActiveRequest,
    user: TokenPayload = Depends(require_permissions("marketplace:admin")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """Admin 激活/停用插件（激活含 MCP 物化，停用仅禁用物化 server）。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})

    if data.is_active:
        await _validate_plugin_payload_ready(doc, storage)
        await materialize_plugin_mcp(doc, admin_user_id=user.sub)
        await storage.set_plugin_status(name, PluginStatus.ACTIVE)
    else:
        await disable_plugin_mcp(name)
        await storage.set_plugin_status(name, PluginStatus.DEACTIVATED)
    return await storage.get_plugin_response(name, viewer_id=user.sub, user_id=user.sub)


@router.delete("/{name}")
async def delete_plugin(
    name: str,
    user: TokenPayload = Depends(require_permissions("marketplace:admin")),
    storage: PluginStorage = Depends(get_plugin_storage),
):
    """Admin 删除插件（含物化 MCP server 清理）。"""
    doc = await storage.get_plugin_doc(name)
    if not doc:
        raise AppError(ErrorCode.PLUGIN_NOT_FOUND, args={"name": name})
    await delete_plugin_mcp(name)
    await storage.delete_plugin(name)
    return {"message": f"Plugin '{name}' deleted", "plugin_name": name}

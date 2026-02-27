"""
Skill API router

Provides endpoints for managing skill configurations.
Follows the same pattern as MCP routes for consistency.
"""

from typing import Optional, cast

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.skill.github_sync import GitHubSyncService
from src.infra.skill.storage import SkillStorage, SystemSkill, UserSkill
from src.kernel.schemas.skill import (
    GitHubInstallRequest,
    GitHubPreviewResponse,
    SkillCreate,
    SkillExportResponse,
    SkillImportRequest,
    SkillImportResponse,
    SkillMoveRequest,
    SkillMoveResponse,
    SkillResponse,
    SkillSource,
    SkillsResponse,
    SkillToggleResponse,
    SkillUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
admin_router = APIRouter()


# Dependency to get SkillStorage
async def get_skill_storage() -> SkillStorage:
    return SkillStorage()


# Dependency to get GitHubSyncService
async def get_github_sync_service() -> GitHubSyncService:
    return GitHubSyncService()


def _is_admin(user: TokenPayload) -> bool:
    """Check if user has admin permissions"""
    return "skill:admin" in (user.permissions or [])


# ==========================================
# User API Endpoints - Static routes first
# ==========================================


@router.get("/", response_model=SkillsResponse)
async def list_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Get all visible skills (system + user's own)"""
    is_admin = _is_admin(user)
    skills = await storage.get_visible_skills(user.sub, is_admin)
    return SkillsResponse(skills=skills, total=len(skills))


@router.post("/", response_model=SkillResponse, status_code=201)
async def create_skill(
    data: SkillCreate,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Create a new user skill"""
    # Check if name already exists in user's skills
    existing = await storage.get_user_skill(data.name, user.sub)
    if existing:
        raise HTTPException(status_code=400, detail=f"Skill '{data.name}' already exists")

    # Also check system skills (users can't override with same name unless admin)
    system_existing = await storage.get_system_skill(data.name)
    if system_existing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{data.name}' already exists as a system skill",
        )

    skill = await storage.create_user_skill(data, user.sub)

    # Get files for response
    files = data.files
    if not files and data.content:
        files = {"SKILL.md": data.content}

    return SkillResponse(
        name=skill.name,
        description=skill.description,
        content=skill.content,
        files=files,
        enabled=skill.enabled,
        source=skill.source,
        github_url=skill.github_url,
        version=skill.version,
        is_system=False,
        can_edit=True,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.post("/import", response_model=SkillImportResponse)
async def import_skills(
    data: SkillImportRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Import skills from JSON configuration"""
    result = await storage.import_skills(data, user.sub, is_admin=False)
    return result


@router.get("/export", response_model=SkillExportResponse)
async def export_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Export user's skills as JSON configuration"""
    config = await storage.export_user_skills(user.sub)
    return config


@router.post("/github/preview", response_model=GitHubPreviewResponse)
async def preview_github_skills(
    data: GitHubInstallRequest,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    github_sync: GitHubSyncService = Depends(get_github_sync_service),
):
    """Preview skills available in a GitHub repository"""
    try:
        result = await github_sync.fetch_skills_from_repo(data.repo_url, data.branch)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch skills from repository: {str(e)}"
        )


@router.post("/github/install", response_model=SkillImportResponse)
async def install_github_skills(
    data: GitHubInstallRequest,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_skill_storage),
    github_sync: GitHubSyncService = Depends(get_github_sync_service),
):
    """Install skills from a GitHub repository"""
    try:
        # First fetch the preview to get skill paths
        preview = await github_sync.fetch_skills_from_repo(data.repo_url, data.branch)

        if not preview.skills:
            return SkillImportResponse(
                message="No skills found in repository",
                imported_count=0,
                skipped_count=0,
                errors=[],
            )

        # Filter to selected skills if specified
        skill_paths = (
            [s.path for s in preview.skills if s.name in data.skill_names]
            if data.skill_names
            else [s.path for s in preview.skills]
        )

        # Fetch full content for each skill
        skills_data = await github_sync.fetch_all_skill_contents(
            data.repo_url, skill_paths, data.branch
        )

        # Install skills
        result = await storage.install_github_skills(data, skills_data, user.sub, is_admin=False)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to install skills: {str(e)}")


# ==========================================
# User API Endpoints - Dynamic routes (with path parameters)
# MUST come after static routes to avoid route shadowing
# ==========================================


@router.get("/{name}", response_model=SkillResponse)
async def get_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Get a specific skill"""
    # Try user skill first
    skill = await storage.get_user_skill(name, user.sub)
    if skill:
        return SkillResponse(
            name=skill.name,
            description=skill.description,
            content=skill.content,
            enabled=skill.enabled,
            source=skill.source,
            github_url=skill.github_url,
            version=skill.version,
            is_system=False,
            can_edit=True,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )

    # Try system skill
    system_skill = await storage.get_system_skill(name)
    if system_skill:
        is_admin = _is_admin(user)
        return SkillResponse(
            name=system_skill.name,
            description=system_skill.description,
            content=system_skill.content,
            enabled=system_skill.enabled,
            source=system_skill.source,
            github_url=system_skill.github_url,
            version=system_skill.version,
            is_system=True,
            can_edit=is_admin,
            created_at=system_skill.created_at,
            updated_at=system_skill.updated_at,
        )

    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


@router.put("/{name}", response_model=SkillResponse)
async def update_skill(
    name: str,
    data: SkillUpdate,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Update a user skill or system skill (admin can change is_system type)"""
    is_admin = _is_admin(user)

    # Check if admin is trying to change is_system type
    if is_admin and data.is_system is not None:
        # Get current skill type
        user_skill = await storage.get_user_skill(name, user.sub)
        system_skill = await storage.get_system_skill(name)

        current_is_system = system_skill is not None
        new_is_system = data.is_system

        # Remove is_system from updates to avoid passing it to update methods
        update_data = data.model_copy()
        update_data.is_system = None

        if current_is_system and not new_is_system:
            # Demote system skill to user skill
            skill: Optional[UserSkill] | Optional[SystemSkill] = await storage.demote_to_user_skill(
                name, user.sub, user.sub
            )
            if not skill:
                raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")
            # Apply remaining updates to the new user skill
            if any(
                [
                    update_data.description is not None,
                    update_data.content is not None,
                    update_data.enabled is not None,
                    update_data.files is not None,
                ]
            ):
                skill = await storage.update_user_skill(name, update_data, user.sub)
        elif not current_is_system and new_is_system:
            # Promote user skill to system skill
            skill = await storage.promote_to_system_skill(name, user.sub, user.sub)
            if not skill:
                raise HTTPException(status_code=404, detail=f"User skill '{name}' not found")
            # Apply remaining updates to the new system skill
            if any(
                [
                    update_data.description is not None,
                    update_data.content is not None,
                    update_data.enabled is not None,
                    update_data.files is not None,
                ]
            ):
                skill = await storage.update_system_skill(name, update_data, user.sub)
        else:
            # No type change, just update in place
            if system_skill:
                skill = await storage.update_system_skill(name, update_data, user.sub)
                if not skill:
                    raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")
            elif user_skill:
                skill = await storage.update_user_skill(name, update_data, user.sub)
                if not skill:
                    raise HTTPException(
                        status_code=404,
                        detail=f"User skill '{name}' not found or not owned by user",
                    )
            else:
                raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    else:
        # Non-admin or no is_system change, update user skill only
        # Remove is_system from updates if present (non-admin can't change it)
        update_data = data.model_copy()
        update_data.is_system = None

        skill = await storage.update_user_skill(name, update_data, user.sub)
        if not skill:
            raise HTTPException(
                status_code=404, detail=f"Skill '{name}' not found or not owned by user"
            )

    # After this point, skill is guaranteed to be not None
    skill = cast(UserSkill | SystemSkill, skill)

    # Determine the correct user_id for file sync
    final_system_skill = await storage.get_system_skill(skill.name)
    file_user_id = "system" if final_system_skill else user.sub

    if data.files is not None:
        await storage.sync_skill_files(skill.name, data.files, user_id=file_user_id)
    elif data.content is not None:
        # Backward compatibility: sync content as SKILL.md
        await storage.sync_skill_files(skill.name, {"SKILL.md": data.content}, user_id=file_user_id)

    # Determine final skill type and response
    if final_system_skill:
        return SkillResponse(
            name=final_system_skill.name,
            description=final_system_skill.description,
            content=final_system_skill.content,
            enabled=final_system_skill.enabled,
            source=final_system_skill.source,
            github_url=final_system_skill.github_url,
            version=final_system_skill.version,
            is_system=True,
            can_edit=is_admin,
            created_at=final_system_skill.created_at,
            updated_at=final_system_skill.updated_at,
        )
    else:
        # Cast to UserSkill since we know it's a user skill here
        user_skill = cast(UserSkill, skill)
        return SkillResponse(
            name=user_skill.name,
            description=user_skill.description,
            content=user_skill.content,
            enabled=user_skill.enabled,
            source=user_skill.source,
            github_url=user_skill.github_url,
            version=user_skill.version,
            is_system=False,
            can_edit=True,
            created_at=user_skill.created_at,
            updated_at=user_skill.updated_at,
        )


@router.delete("/{name}")
async def delete_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Delete a user skill"""
    deleted = await storage.delete_user_skill(name, user.sub)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Skill '{name}' not found or not owned by user"
        )

    return {"message": f"Skill '{name}' deleted successfully"}


@router.patch("/{name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Toggle a skill's enabled status (user preferences for system skills)"""
    skill = await storage.toggle_skill(name, user.sub)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    status_text = "enabled" if skill.enabled else "disabled"
    return SkillToggleResponse(
        skill=skill,
        message=f"Skill '{name}' has been {status_text}",
    )


# ==========================================
# Admin API Endpoints - Static routes first
# ==========================================


@admin_router.get("/", response_model=SkillsResponse)
async def admin_list_skills(
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Get all skills (admin view - includes all system skills)"""
    skills = await storage.get_visible_skills(user.sub, is_admin=True)
    return SkillsResponse(skills=skills, total=len(skills))


@admin_router.post("/", response_model=SkillResponse, status_code=201)
async def admin_create_skill(
    data: SkillCreate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Create a new system skill (admin only)"""
    existing = await storage.get_system_skill(data.name)
    if existing:
        raise HTTPException(status_code=400, detail=f"System skill '{data.name}' already exists")

    # Set source to builtin if not specified
    if data.source == SkillSource.MANUAL:
        data.source = SkillSource.BUILTIN

    skill = await storage.create_system_skill(data, user.sub)

    # Get files for response
    files = data.files
    if not files and data.content:
        files = {"SKILL.md": data.content}

    return SkillResponse(
        name=skill.name,
        description=skill.description,
        content=skill.content,
        files=files,
        enabled=skill.enabled,
        source=skill.source,
        github_url=skill.github_url,
        version=skill.version,
        is_system=True,
        can_edit=True,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@admin_router.get("/export", response_model=SkillExportResponse)
async def admin_export_skills(
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Export all system skills as JSON configuration (admin only)"""
    config = await storage.export_all_skills()
    return config


@admin_router.post("/import", response_model=SkillImportResponse)
async def admin_import_skills(
    data: SkillImportRequest,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Import skills as system skills (admin only)"""
    result = await storage.import_skills(data, user.sub, is_admin=True)
    return result


@admin_router.post("/github/install", response_model=SkillImportResponse)
async def admin_install_github_skills(
    data: GitHubInstallRequest,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
    github_sync: GitHubSyncService = Depends(get_github_sync_service),
):
    """Install skills from GitHub as system skills (admin only)"""
    try:
        # First fetch the preview to get skill paths
        preview = await github_sync.fetch_skills_from_repo(data.repo_url, data.branch)

        if not preview.skills:
            return SkillImportResponse(
                message="No skills found in repository",
                imported_count=0,
                skipped_count=0,
                errors=[],
            )

        # Filter to selected skills if specified
        skill_paths = (
            [s.path for s in preview.skills if s.name in data.skill_names]
            if data.skill_names
            else [s.path for s in preview.skills]
        )

        # Fetch full content for each skill
        skills_data = await github_sync.fetch_all_skill_contents(
            data.repo_url, skill_paths, data.branch
        )

        # Install skills as system skills
        result = await storage.install_github_skills(data, skills_data, user.sub, is_admin=True)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to install skills: {str(e)}")


# ==========================================
# Admin API Endpoints - Dynamic routes (with path parameters)
# MUST come after static routes to avoid route shadowing
# ==========================================


@admin_router.get("/{name}", response_model=SkillResponse)
async def admin_get_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Get a system skill (admin only)"""
    skill = await storage.get_system_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")

    return SkillResponse(
        name=skill.name,
        description=skill.description,
        content=skill.content,
        enabled=skill.enabled,
        source=skill.source,
        github_url=skill.github_url,
        version=skill.version,
        is_system=True,
        can_edit=True,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@admin_router.put("/{name}", response_model=SkillResponse)
async def admin_update_skill(
    name: str,
    data: SkillUpdate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Update a system skill (admin only)"""
    skill = await storage.update_system_skill(name, data, user.sub)
    if not skill:
        raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")

    if data.files is not None:
        await storage.sync_skill_files(skill.name, data.files, user_id="system")
    elif data.content is not None:
        # Backward compatibility: sync content as SKILL.md
        await storage.sync_skill_files(skill.name, {"SKILL.md": data.content}, user_id="system")

    return SkillResponse(
        name=skill.name,
        description=skill.description,
        content=skill.content,
        enabled=skill.enabled,
        source=skill.source,
        github_url=skill.github_url,
        version=skill.version,
        is_system=True,
        can_edit=True,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@admin_router.delete("/{name}")
async def admin_delete_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Delete a system skill (admin only)"""
    deleted = await storage.delete_system_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")

    return {"message": f"System skill '{name}' deleted successfully"}


@admin_router.patch("/{name}/toggle", response_model=SkillToggleResponse)
async def admin_toggle_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """Toggle a system skill's enabled status (admin only)"""
    skill = await storage.toggle_system_skill(name)

    if not skill:
        raise HTTPException(status_code=404, detail=f"System skill '{name}' not found")

    status_text = "enabled" if skill.enabled else "disabled"
    return SkillToggleResponse(
        skill=skill,
        message=f"System skill '{name}' has been {status_text}",
    )


# ==========================================
# Skill Type Conversion (Admin only)
# ==========================================


@admin_router.post("/{name}/promote", response_model=SkillMoveResponse)
async def promote_skill(
    name: str,
    data: SkillMoveRequest,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """
    Promote a user skill to system skill (admin only).

    Requires the owner's user_id in request body to identify which user's skill to promote.
    """
    if not data.target_user_id:
        raise HTTPException(
            status_code=400, detail="target_user_id is required to identify the user skill"
        )

    skill = await storage.promote_to_system_skill(name, data.target_user_id, user.sub)

    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"User skill '{name}' not found or system skill with same name exists",
        )

    return SkillMoveResponse(
        skill=SkillResponse(
            name=skill.name,
            description=skill.description,
            content=skill.content,
            enabled=skill.enabled,
            source=skill.source,
            github_url=skill.github_url,
            version=skill.version,
            is_system=True,
            can_edit=True,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        ),
        message=f"Skill '{name}' has been promoted to system skill",
        from_type="user",
        to_type="system",
    )


@admin_router.post("/{name}/demote", response_model=SkillMoveResponse)
async def demote_skill(
    name: str,
    data: SkillMoveRequest,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    storage: SkillStorage = Depends(get_skill_storage),
):
    """
    Demote a system skill to user skill (admin only).

    Requires target_user_id in request body to specify who will own the skill.
    """
    if not data.target_user_id:
        raise HTTPException(
            status_code=400, detail="target_user_id is required to specify the new owner"
        )

    skill = await storage.demote_to_user_skill(name, data.target_user_id, user.sub)

    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"System skill '{name}' not found or user already has skill with same name",
        )

    return SkillMoveResponse(
        skill=SkillResponse(
            name=skill.name,
            description=skill.description,
            content=skill.content,
            enabled=skill.enabled,
            source=skill.source,
            github_url=skill.github_url,
            version=skill.version,
            is_system=False,
            can_edit=True,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        ),
        message=f"System skill '{name}' has been demoted to user skill",
        from_type="system",
        to_type="user",
    )

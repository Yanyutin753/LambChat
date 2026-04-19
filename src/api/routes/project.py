"""
项目路由

所有项目操作都需要认证，用户只能访问自己的项目。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required
from src.infra.folder.storage import get_project_storage
from src.infra.session.storage import SessionStorage
from src.kernel.schemas.project import Project, ProjectCreate, ProjectUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("", response_model=list[Project])
async def list_projects(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出所有项目

    自动确保收藏项目存在。
    """
    storage = get_project_storage()

    # Ensure favorites project exists
    await storage.ensure_favorites_project(user.sub)

    projects = await storage.list_projects(user.sub)
    return projects


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建项目

    不允许创建 type="favorites" 的项目。
    """
    storage = get_project_storage()

    # Prevent creating favorites project manually
    if project_data.type == "favorites":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能创建收藏项目",
        )

    project = await storage.create(project_data, user.sub)
    return project


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    project_data: ProjectUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新项目（重命名）

    只能更新自己拥有的项目。
    """
    storage = get_project_storage()

    # Check if project exists and belongs to user
    project = await storage.get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在",
        )

    updated_project = await storage.update(project_id, user.sub, project_data)
    if not updated_project:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新失败",
        )

    return updated_project


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    delete_sessions: bool = Query(False, description="是否同时删除项目内的所有会话"),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除项目

    - 不能删除收藏项目
    - delete_sessions=false: 项目内的会话会被移动到未分类
    - delete_sessions=true: 同时删除项目内的所有会话
    """
    storage = get_project_storage()

    # Check if project exists and belongs to user
    project = await storage.get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在",
        )

    # Prevent deleting favorites project
    if project.type == "favorites":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除收藏项目",
        )

    session_storage = SessionStorage()

    if delete_sessions:
        # Delete all sessions in this project
        await session_storage.delete_by_project(project_id, user.sub)
    else:
        # Clear project_id for all sessions in this project
        await session_storage.clear_project_id(project_id, user.sub)

    # Clear project_id on all revealed files belonging to this project
    try:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        revealed_storage = get_revealed_file_storage()
        await revealed_storage.clear_project_id(project_id)
    except Exception as e:
        from src.infra.logging import get_logger

        get_logger(__name__).warning(f"Failed to clear revealed file project_id: {e}")

    # Delete the project
    success = await storage.delete(project_id, user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败",
        )

    return {"status": "deleted"}

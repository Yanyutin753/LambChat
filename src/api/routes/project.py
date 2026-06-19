"""
项目路由

所有项目操作都需要认证，用户只能访问自己的项目。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.api.deps import get_current_user_required
from src.infra.extensions import get_plugin_settings_service
from src.infra.extensions.scoped_options import (
    plugin_options_with_settings,
    scoped_option_definition,
    scoped_option_manifest,
    scoped_plugin_is_executable,
    validate_scoped_plugin_option_value,
)
from src.infra.folder.storage import get_project_storage
from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage
from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS
from src.kernel.extensions.plugin_options import (
    filter_declared_plugin_options,
    plugin_options_from_metadata,
    with_plugin_option,
)
from src.kernel.extensions.runtime import PluginRuntime
from src.kernel.schemas.project import Project, ProjectCreate, ProjectUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


class ProjectPluginOptionUpdatePayload(BaseModel):
    value: Any = None


def _get_plugin_runtime(request: Request) -> PluginRuntime:
    runtime = getattr(request.app.state, "plugin_runtime", None)
    if isinstance(runtime, PluginRuntime):
        return runtime
    return PluginRuntime(BUILTIN_PLUGIN_MANIFESTS, core_dependencies=("skill_core",))


def _get_plugin_settings_service(request: Request):
    return getattr(request.app.state, "plugin_settings_service", None) or get_plugin_settings_service()


def _project_option_definition(runtime: PluginRuntime, plugin_id: str, key: str):
    try:
        return scoped_option_definition(
            runtime,
            scope="project",
            plugin_id=plugin_id,
            key=key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _plugin_manifest(runtime: PluginRuntime, plugin_id: str):
    try:
        return scoped_option_manifest(runtime, plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _validate_project_plugin_option_value(option, value: Any) -> Any:
    try:
        return validate_scoped_plugin_option_value(option, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _plugin_is_executable(runtime: PluginRuntime, plugin_id: str) -> bool:
    return scoped_plugin_is_executable(runtime, plugin_id)


async def _delete_session_with_related_records(
    session_manager: SessionManager,
    session_id: str,
) -> bool:
    deleted = await session_manager.delete_session(session_id)
    if not deleted:
        return False

    try:
        from src.infra.tool.deferred_manager import clear_discovered_tools

        await clear_discovered_tools(session_id)
    except Exception:
        pass

    return True


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


@router.get("/{project_id}/plugin-options")
async def get_project_plugin_options(
    project_id: str,
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Return plugin-scoped project options stored on this project."""
    storage = get_project_storage()
    project = await storage.get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    runtime = _get_plugin_runtime(request)
    declared_plugin_options = filter_declared_plugin_options(
        runtime,
        project.metadata,
        scope="project",
    )
    plugin_options = await plugin_options_with_settings(
        runtime=runtime,
        service=_get_plugin_settings_service(request),
        scope="project",
        subject_id=project_id,
        plugin_options=declared_plugin_options,
    )
    return {
        "project_id": project_id,
        "plugin_options": plugin_options,
    }


@router.put("/{project_id}/plugin-options/{plugin_id}/{key}")
async def update_project_plugin_option(
    project_id: str,
    plugin_id: str,
    key: str,
    payload: ProjectPluginOptionUpdatePayload,
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Update one manifest-declared plugin project option without enabling the plugin."""
    runtime = _get_plugin_runtime(request)
    option = _project_option_definition(runtime, plugin_id, key)
    manifest = _plugin_manifest(runtime, plugin_id)
    value = _validate_project_plugin_option_value(option, payload.value)
    storage = get_project_storage()
    project = await storage.get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        await _get_plugin_settings_service(request).set_setting(
            manifest,
            key=key,
            value=value,
            updated_by=user.sub,
            scope="project",
            subject_id=project_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    declared_plugin_options = filter_declared_plugin_options(
        runtime,
        project.metadata,
        scope="project",
    )
    metadata = with_plugin_option(
        {"plugin_options": declared_plugin_options},
        plugin_id=plugin_id,
        key=key,
        value=value,
    )
    updated_project = await storage.update(
        project_id,
        user.sub,
        ProjectUpdate(metadata={"plugin_options": metadata.get("plugin_options", {})}),
    )
    if not updated_project:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to update plugin project option",
        )
    plugin_enabled = _plugin_is_executable(runtime, plugin_id)
    return {
        "project_id": project_id,
        "plugin_id": plugin_id,
        "key": key,
        "qualified_key": f"{plugin_id}.{key}",
        "value": value,
        "plugin_enabled": plugin_enabled,
        "effective": plugin_enabled,
        "plugin_options": filter_declared_plugin_options(
            runtime,
            updated_project.metadata,
            scope="project",
        ),
    }


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
        # Use the same path as single-session deletion so traces, files,
        # checkpoints, and related session data are cleaned up too.
        session_ids = await session_storage.list_ids_by_project(project_id, user.sub)
        session_manager = SessionManager()
        for session_id in session_ids:
            deleted = await _delete_session_with_related_records(session_manager, session_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="删除项目内会话失败",
                )
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

    # Clear project_id on channel configs so future channel-created sessions
    # cannot resurrect a deleted project reference.
    try:
        from src.infra.channel.channel_storage import ChannelStorage

        channel_storage = ChannelStorage()
        await channel_storage.clear_project_id(project_id, user.sub)
    except Exception as e:
        from src.infra.logging import get_logger

        get_logger(__name__).warning(f"Failed to clear channel config project_id: {e}")

    # Delete the project
    success = await storage.delete(project_id, user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败",
        )

    return {"status": "deleted"}

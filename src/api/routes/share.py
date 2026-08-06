"""
会话分享路由

支持两种分享维度：
- 会话维度（scope=session）：分享单个会话，full=全量事件 / partial=按 run_ids
- 项目维度（scope=project）：分享整个项目，full=实时全部会话 / partial=快照选中会话

公开访问支持 public（任何人）与 authenticated（需登录）两种可见性。
"""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.agents.core.base import get_agent_class
from src.api.deps import get_current_user_optional, get_current_user_required
from src.infra.folder.storage import get_project_storage
from src.infra.logging import get_logger
from src.infra.session.dual_writer import get_dual_writer
from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage
from src.infra.share.storage import ShareStorage
from src.infra.team.storage import TeamStorage
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import to_iso
from src.kernel.schemas.share import (
    ProjectSnapshot,
    ShareCreate,
    SharedContentOwner,
    SharedContentResponse,
    SharedProjectContentResponse,
    SharedProjectSessionItem,
    SharedSessionListItem,
    SharedSessionResponse,
    ShareListResponse,
    ShareScope,
    ShareType,
    ShareUpdate,
    ShareVisibility,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = get_logger(__name__)

SHARE_PARTIAL_RUN_IDS_LIMIT = 100
SHARE_PROJECT_SESSIONS_LIMIT = 50
SHARE_PROJECT_MANIFEST_DEFAULT = 50


def _check_permission(user: TokenPayload, permission: str) -> bool:
    """检查用户是否拥有指定权限"""
    return permission in user.permissions


def _require_share_permission(user: TokenPayload) -> None:
    """要求用户拥有分享权限"""
    if not _check_permission(user, Permission.SESSION_SHARE.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有分享会话的权限",
        )


def _validate_share_run_ids(share_data: ShareCreate | ShareUpdate) -> None:
    if share_data.share_type != ShareType.PARTIAL:
        return
    if not share_data.run_ids:
        raise HTTPException(
            status_code=400,
            detail="部分分享需要指定 run_ids",
        )
    if len(share_data.run_ids) > SHARE_PARTIAL_RUN_IDS_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"run_ids 数量不能超过 {SHARE_PARTIAL_RUN_IDS_LIMIT}",
        )


def _validate_share_payload(share_data: ShareCreate) -> None:
    """结构化校验：按 share_scope 检查必填字段与上限。"""
    if share_data.share_scope == ShareScope.SESSION:
        if not share_data.session_id:
            raise HTTPException(status_code=400, detail="会话分享需要 session_id")
        if share_data.share_type == ShareType.PARTIAL:
            _validate_share_run_ids(share_data)
        return

    # scope == PROJECT
    if not share_data.project_id:
        raise HTTPException(status_code=400, detail="项目分享需要 project_id")
    if share_data.share_type == ShareType.PARTIAL:
        if not share_data.session_ids:
            raise HTTPException(
                status_code=400,
                detail="部分项目分享需要 session_ids",
            )
        if len(share_data.session_ids) > SHARE_PROJECT_SESSIONS_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"session_ids 数量不能超过 {SHARE_PROJECT_SESSIONS_LIMIT}",
            )


async def _validate_project_share(
    share_data: ShareCreate,
    user: TokenPayload,
) -> ProjectSnapshot:
    """校验项目分享的所有权与会话归属，返回冻结的项目快照。"""
    project_id = share_data.project_id
    if not project_id:
        raise HTTPException(status_code=400, detail="项目分享需要 project_id")

    project = await get_project_storage().get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    if share_data.share_type == ShareType.PARTIAL:
        actual_ids = set(await SessionStorage().list_ids_by_project(project_id, user.sub))
        requested = set(share_data.session_ids or [])
        if not requested:
            raise HTTPException(
                status_code=400,
                detail="部分项目分享需要 session_ids",
            )
        if not requested <= actual_ids:
            raise HTTPException(
                status_code=400,
                detail="部分会话不属于该项目",
            )

    return ProjectSnapshot(id=project.id, name=project.name, icon=project.icon)


def _bounded_partial_run_ids(run_ids: list[str] | None) -> list[str] | None:
    if not run_ids:
        return None
    return run_ids[:SHARE_PARTIAL_RUN_IDS_LIMIT]


def _resolve_shared_team_avatar(team) -> str | None:
    if team.avatar:
        return team.avatar

    default_member = next(
        (member for member in team.members if member.member_id == team.default_member_id),
        None,
    )
    fallback_member = (
        default_member
        or next((member for member in team.members if member.enabled), None)
        or (team.members[0] if team.members else None)
    )
    return fallback_member.role_avatar if fallback_member else None


async def _attach_shared_team_metadata(
    session_info: dict,
    session,
    share,
) -> None:
    """Attach safe team display metadata for shared team sessions."""
    metadata = session.metadata or {}
    team_id = metadata.get("team_id") if session.agent_id == "team" else None
    if not team_id:
        return

    session_info["team_id"] = team_id
    try:
        team = await TeamStorage().get_team(
            str(team_id),
            owner_user_id=session.user_id or share.owner_id,
        )
        if team:
            session_info["team_name"] = team.name
            team_avatar = _resolve_shared_team_avatar(team)
            if team_avatar:
                session_info["team_avatar"] = team_avatar
    except Exception:
        logger.warning("Failed to load shared team metadata", exc_info=True)


def _build_safe_session_info(session) -> dict:
    """构建公开可见的会话信息（仅安全字段）。"""
    agent_name = session.agent_id
    try:
        agent_cls = get_agent_class(session.agent_id)
        agent_name = agent_cls._agent_name
    except (ValueError, AttributeError):
        pass

    metadata = session.metadata or {}
    model = metadata.get("agent_options", {}).get("model")

    persona_preset_id = metadata.get("persona_preset_id")
    persona_preset_name = metadata.get("persona_preset_name")
    persona_avatar = metadata.get("persona_avatar")

    session_info = {
        "id": session.id,
        "name": session.name,
        "agent_id": session.agent_id,
        "agent_name": agent_name,
        "model": model,
        "created_at": to_iso(session.created_at),
        "updated_at": to_iso(session.updated_at),
        "task_status": session.task_status,
        "task_error": session.task_error,
        "completed_at": to_iso(session.completed_at),
    }

    if persona_preset_id:
        session_info["persona_preset_id"] = persona_preset_id
    if persona_preset_name:
        session_info["persona_preset_name"] = persona_preset_name
    if persona_avatar:
        session_info["persona_avatar"] = persona_avatar

    return session_info


def _build_project_session_item(session) -> SharedProjectSessionItem:
    """构建项目 manifest 中的子会话摘要。"""
    agent_name = session.agent_id
    try:
        agent_cls = get_agent_class(session.agent_id)
        agent_name = agent_cls._agent_name
    except (ValueError, AttributeError):
        pass

    model = (session.metadata or {}).get("agent_options", {}).get("model")

    return SharedProjectSessionItem(
        id=session.id,
        name=session.name,
        agent_name=agent_name,
        model=model,
        updated_at=session.updated_at,
    )


async def _build_session_content(
    share,
    event_limit: int | None = None,
    session=None,
) -> SharedContentResponse:
    """构建单会话分享内容（scope=session，或项目分享的子会话事件）。

    读取该会话的 completed 事件并裁剪为安全字段。``session`` 可由调用方
    传入（项目子会话），否则按 ``share.session_id`` 取。
    """
    if session is None:
        if not share.session_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原会话已不存在")
        session = await SessionManager().get_session(share.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原会话已不存在")

    dual_writer = get_dual_writer()

    partial_run_ids = (
        _bounded_partial_run_ids(share.run_ids) if share.share_type == ShareType.PARTIAL else None
    )
    read_events_kwargs: dict[str, Any] = {"completed_only": True}
    if event_limit is not None:
        read_events_kwargs["max_events"] = event_limit + 1

    if partial_run_ids:
        events = await dual_writer.read_session_events(
            session.id, run_ids=partial_run_ids, **read_events_kwargs
        )
    else:
        events = await dual_writer.read_session_events(session.id, **read_events_kwargs)
    events_limited = event_limit is not None and len(events) > event_limit
    if events_limited and event_limit is not None:
        events = events[:event_limit]

    owner = await UserStorage().get_by_id(share.owner_id)
    owner_info = SharedContentOwner(
        username=owner.username if owner else "Unknown",
        avatar_url=owner.avatar_url if owner else None,
    )

    session_info = _build_safe_session_info(session)
    await _attach_shared_team_metadata(session_info, session, share)

    return SharedContentResponse(
        session=session_info,
        events=events,
        owner=owner_info,
        share_type=share.share_type,
        run_ids=partial_run_ids if share.share_type == ShareType.PARTIAL else share.run_ids,
        events_limited=events_limited,
        events_limit=event_limit,
    )


async def _build_project_manifest(
    share,
    session_skip: int,
    session_limit: int,
) -> SharedProjectContentResponse:
    """构建项目分享的 manifest（项目信息 + 子会话摘要，不含完整事件）。"""
    if not share.project_snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在或已过期")

    session_limit = min(max(int(session_limit), 1), SHARE_PROJECT_SESSIONS_LIMIT)
    session_skip = max(int(session_skip), 0)

    if share.share_type == ShareType.PARTIAL:
        member_ids = list(share.session_ids or [])
    else:  # FULL 实时
        member_ids = await SessionStorage().list_ids_by_project(share.project_id, share.owner_id)
    sessions_total = len(member_ids)

    page_ids = member_ids[session_skip : session_skip + session_limit]
    session_map = await SessionManager().get_sessions(page_ids) if page_ids else {}

    items: list[SharedProjectSessionItem] = []
    for sid in page_ids:
        session = session_map.get(sid)
        if not session:
            continue
        items.append(_build_project_session_item(session))

    owner = await UserStorage().get_by_id(share.owner_id)
    owner_info = SharedContentOwner(
        username=owner.username if owner else "Unknown",
        avatar_url=owner.avatar_url if owner else None,
    )

    has_more = session_skip + len(page_ids) < sessions_total

    return SharedProjectContentResponse(
        share_type=share.share_type,
        project=share.project_snapshot,
        sessions=items,
        owner=owner_info,
        visibility=share.visibility,
        sessions_total=sessions_total,
        has_more=has_more,
    )


async def _resolve_project_member_ids(share) -> set[str]:
    """项目分享可见的会话集合（partial=快照 / full=实时成员）。"""
    if share.share_type == ShareType.PARTIAL:
        return set(share.session_ids or [])
    return set(await SessionStorage().list_ids_by_project(share.project_id, share.owner_id))


def _build_share_response(shared_session) -> SharedSessionResponse:
    return SharedSessionResponse(
        id=shared_session.id,
        share_id=shared_session.share_id,
        url=f"/shared/{shared_session.share_id}",
        session_id=shared_session.session_id,
        share_scope=shared_session.share_scope,
        project_id=shared_session.project_id,
        share_type=shared_session.share_type,
        visibility=shared_session.visibility,
        run_ids=shared_session.run_ids,
        session_ids=shared_session.session_ids,
        created_at=shared_session.created_at,
    )


@router.post("", response_model=SharedSessionResponse)
async def create_share(
    share_data: ShareCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建分享

    需要 session:share 权限。支持会话维度与项目维度。
    """
    _require_share_permission(user)
    _validate_share_payload(share_data)

    project_snapshot: ProjectSnapshot | None = None
    if share_data.share_scope == ShareScope.PROJECT:
        project_snapshot = await _validate_project_share(share_data, user)
    else:
        # 验证会话所有权
        session_id = share_data.session_id
        if not session_id:
            raise HTTPException(status_code=400, detail="会话分享需要 session_id")
        manager = SessionManager()
        session = await manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
        if session.user_id != user.sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能分享自己的会话",
            )

    storage = ShareStorage()
    shared_session = await storage.create(
        share_data, owner_id=user.sub, project_snapshot=project_snapshot
    )

    return _build_share_response(shared_session)


@router.get("", response_model=ShareListResponse)
async def list_shares(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出我创建的分享

    返回当前用户创建的所有分享记录。
    """
    storage = ShareStorage()
    shares, total = await storage.list_by_owner(user.sub, skip=skip, limit=limit)

    # 获取会话名称（批量查询）
    session_ids = list({share.session_id for share in shares if share.session_id})
    session_map = await SessionManager().get_sessions(session_ids) if session_ids else {}

    for share in shares:
        session = session_map.get(share.session_id) if share.session_id else None
        share.session_name = session.name if session else None

    return ShareListResponse(shares=shares, total=total)


@router.patch("/{share_id}", response_model=SharedSessionResponse)
async def update_share(
    share_id: str,
    share_data: ShareUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新已有分享

    保持公开链接不变，只更新分享范围与访问权限。
    session 分享可调 share_type/run_ids/visibility；
    project 分享可调 share_type/session_ids/visibility（partial 刷新快照）。
    """
    _require_share_permission(user)

    storage = ShareStorage()
    share = await storage.get_by_id(share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    if share.owner_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能编辑自己创建的分享",
        )

    next_share_type = share_data.share_type or share.share_type
    next_visibility = share_data.visibility or share.visibility

    if share.share_scope == ShareScope.PROJECT:
        if not share.project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")
        next_session_ids = (
            share_data.session_ids if share_data.session_ids is not None else share.session_ids
        )
        if next_share_type == ShareType.PARTIAL:
            if not next_session_ids:
                raise HTTPException(
                    status_code=400,
                    detail="部分项目分享需要 session_ids",
                )
            if len(next_session_ids) > SHARE_PROJECT_SESSIONS_LIMIT:
                raise HTTPException(
                    status_code=400,
                    detail=f"session_ids 数量不能超过 {SHARE_PROJECT_SESSIONS_LIMIT}",
                )
            # 校验会话归属与项目所有权
            await _validate_project_share(
                ShareCreate(
                    share_scope=ShareScope.PROJECT,
                    project_id=share.project_id,
                    share_type=ShareType.PARTIAL,
                    session_ids=next_session_ids,
                    visibility=next_visibility,
                ),
                user,
            )
        else:
            next_session_ids = None
        next_run_ids = None
    else:
        # session 分享
        if not share.session_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
        manager = SessionManager()
        session = await manager.get_session(share.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

        if session.user_id != user.sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能分享自己的会话",
            )

        next_run_ids = share_data.run_ids if share_data.run_ids is not None else share.run_ids
        normalized_update = ShareUpdate(
            share_type=next_share_type,
            run_ids=next_run_ids,
            visibility=next_visibility,
        )
        _validate_share_run_ids(normalized_update)
        if next_share_type != ShareType.PARTIAL:
            next_run_ids = None
        next_session_ids = None

    updated_share = await storage.update(
        share_id,
        owner_id=user.sub,
        share_type=next_share_type,
        run_ids=next_run_ids,
        visibility=next_visibility,
        session_ids=next_session_ids,
    )
    if not updated_share:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新失败")

    return _build_share_response(updated_share)


@router.get("/session/{session_id}", response_model=list[SharedSessionListItem])
async def list_session_shares(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出指定会话的所有分享

    只有会话所有者可以查看。
    """
    # 验证会话所有权
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    if session.user_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己会话的分享",
        )

    storage = ShareStorage()
    shares = await storage.list_by_session(session_id)

    for share in shares:
        share.session_name = session.name

    return shares


@router.get("/project/{project_id}", response_model=list[SharedSessionListItem])
async def list_project_shares(
    project_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出指定项目的所有分享

    只有项目所有者可以查看。
    """
    project = await get_project_storage().get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    storage = ShareStorage()
    shares = await storage.list_by_project(project_id, user.sub)

    # 管理列表展示当前项目名（而非冻结快照名）
    for share in shares:
        share.project_name = project.name

    return shares


@router.delete("/{share_id}")
async def delete_share(
    share_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除分享

    只有分享所有者可以删除。
    """
    storage = ShareStorage()

    # 获取分享记录验证所有权
    share = await storage.get_by_id(share_id)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    if share.owner_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己创建的分享",
        )

    success = await storage.delete(share_id, user.sub)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除失败")

    return {"status": "deleted"}


# ========================================
# 公开访问路由（无需认证或可选认证）
# ========================================


@router.get("/public/{share_id}", response_model=None)
async def get_shared_content(
    share_id: str,
    session_skip: Annotated[int, Query(ge=0)] = 0,
    session_limit: Annotated[
        int, Query(ge=1, le=SHARE_PROJECT_SESSIONS_LIMIT)
    ] = SHARE_PROJECT_MANIFEST_DEFAULT,
    event_limit: Annotated[int | None, Query(ge=1)] = None,
    user: Optional[TokenPayload] = Depends(get_current_user_optional),
):
    """
    查看分享内容

    根据 visibility 决定是否需要登录：
    - public: 任何人都可以查看
    - authenticated: 需要登录才能查看

    按 share_scope 返回不同形态：
    - session: 单会话内容（session + events）
    - project: 项目 manifest（project + sessions 摘要）
    """
    storage = ShareStorage()
    share = await storage.get_by_share_id(share_id)

    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在或已过期")

    # 检查访问权限
    if share.visibility == ShareVisibility.AUTHENTICATED:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能查看此分享",
            )

    if share.share_scope == ShareScope.PROJECT:
        return await _build_project_manifest(share, session_skip, session_limit)

    return await _build_session_content(share, event_limit=event_limit)


@router.get("/public/{share_id}/sessions/{session_id}", response_model=None)
async def get_shared_session_in_project(
    share_id: str,
    session_id: str,
    event_limit: Annotated[int | None, Query(ge=1)] = None,
    user: Optional[TokenPayload] = Depends(get_current_user_optional),
):
    """
    查看项目分享中的某个子会话事件

    必须校验 session_id 属于该分享（partial=快照 / full=实时成员）。
    """
    storage = ShareStorage()
    share = await storage.get_by_share_id(share_id)

    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在或已过期")

    if share.visibility == ShareVisibility.AUTHENTICATED:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能查看此分享",
            )

    if share.share_scope != ShareScope.PROJECT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在或已过期")

    allowed_ids = await _resolve_project_member_ids(share)
    if session_id not in allowed_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不在此分享中")

    session = await SessionManager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原会话已不存在")

    return await _build_session_content(share, event_limit=event_limit, session=session)

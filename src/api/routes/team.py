"""Agent Team plugin-owned CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_current_user_required
from src.api.routes.plugin_guard import plugin_route_guard
from src.infra.team.manager import TeamManager
from src.kernel.exceptions import NotFoundError
from src.kernel.extensions.plugin_options import AGENT_TEAM_PLUGIN_ID
from src.kernel.schemas.team import (
    TeamCreate,
    TeamListResponse,
    TeamPreferenceUpdate,
    TeamResponse,
    TeamUpdate,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter(
    redirect_slashes=False,
    dependencies=[Depends(plugin_route_guard(AGENT_TEAM_PLUGIN_ID))],
)


def _get_manager() -> TeamManager:
    return TeamManager()


@router.get("", response_model=TeamListResponse)
@router.get("/", response_model=TeamListResponse)
async def list_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    favorite: bool | None = None,
    pinned: bool | None = None,
    q: str | None = Query(None, max_length=100),
    tag: str | None = Query(None, max_length=80),
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    return await manager.list_teams(
        owner_user_id=user.sub,
        skip=skip,
        limit=limit,
        favorite=favorite,
        pinned=pinned,
        q=q,
        tag=tag,
    )


@router.post("", response_model=TeamResponse, status_code=201)
@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        return await manager.create_team(body, owner_user_id=user.sub, user=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        return await manager.get_team(team_id, owner_user_id=user.sub)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="team_not_found")


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        return await manager.update_team(team_id, body, owner_user_id=user.sub, user=user)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="team_not_found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{team_id}/preference", response_model=TeamResponse)
async def update_team_preference(
    team_id: str,
    preference: TeamPreferenceUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        return await manager.update_preference(
            team_id,
            preference,
            owner_user_id=user.sub,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="team_not_found")


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        await manager.delete_team(team_id, owner_user_id=user.sub)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="team_not_found")


@router.post("/{team_id}/clone", response_model=TeamResponse, status_code=201)
async def clone_team(
    team_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: TeamManager = Depends(_get_manager),
):
    try:
        return await manager.clone_team(team_id, owner_user_id=user.sub)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="team_not_found")

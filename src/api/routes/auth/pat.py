"""PAT 个人访问令牌管理路由。"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required
from src.infra.auth.pat import PATStorage
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

router = APIRouter()

_ALLOWED_SCOPES = {"sandbox:execute"}


def get_pat_storage() -> PATStorage:
    return PATStorage()


class PATCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class PATCreateResponse(BaseModel):
    token: str
    pat_id: str


class PATItem(BaseModel):
    pat_id: str
    name: str
    scopes: list[str]
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class PATListResponse(BaseModel):
    pats: list[PATItem]


@router.post("", response_model=PATCreateResponse)
async def create_pat(
    body: PATCreateRequest,
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    for scope in body.scopes:
        if scope not in _ALLOWED_SCOPES:
            raise AppError(ErrorCode.VALIDATION_ERROR, args={"detail": f"unknown scope: {scope}"})
    token, record = await storage.create(
        user_id=user.sub, name=body.name, scopes=body.scopes, expires_at=body.expires_at
    )
    return PATCreateResponse(token=token, pat_id=record.pat_id)


@router.get("", response_model=PATListResponse)
async def list_pats(
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    records = await storage.list_for_user(user.sub)
    return PATListResponse(
        pats=[
            PATItem(
                pat_id=r.pat_id,
                name=r.name,
                scopes=r.scopes,
                prefix=r.prefix,
                created_at=r.created_at,
                expires_at=r.expires_at,
                last_used_at=r.last_used_at,
            )
            for r in records
        ]
    )


@router.delete("/{pat_id}")
async def revoke_pat(
    pat_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    storage: PATStorage = Depends(get_pat_storage),
):
    ok = await storage.revoke(user_id=user.sub, pat_id=pat_id)
    if not ok:
        raise AppError(ErrorCode.PAT_NOT_FOUND)
    return {"status": "ok"}

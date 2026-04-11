# src/api/routes/revealed_file.py
"""API routes for the revealed file library."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_current_user_required
from src.infra.revealed_file.storage import get_revealed_file_storage
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/revealed")
async def list_revealed_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    file_type: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    favorites_only: bool = Query(False),
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = get_revealed_file_storage()
    result = await storage.list_files(
        user.sub,
        file_type=file_type,
        session_id=session_id,
        project_id=project_id,
        search=search,
        favorites_only=favorites_only,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "items": result["items"],
        "total": result["total"],
        "page": page,
        "page_size": page_size,
    }


@router.get("/revealed/stats")
async def get_revealed_file_stats(
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = get_revealed_file_storage()
    stats = await storage.get_stats(user.sub)
    return stats


@router.get("/revealed/sessions")
async def list_revealed_file_sessions(
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = get_revealed_file_storage()
    sessions = await storage.get_user_sessions(user.sub)
    return sessions


@router.get("/revealed/grouped")
async def list_revealed_files_grouped(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    file_type: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    favorites_only: bool = Query(False),
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = get_revealed_file_storage()
    result = await storage.list_files_grouped_by_session(
        user.sub,
        file_type=file_type,
        project_id=project_id,
        search=search,
        favorites_only=favorites_only,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return {
        "sessions": result["sessions"],
        "total_sessions": result["total_sessions"],
        "page": page,
        "page_size": page_size,
    }


@router.patch("/revealed/{file_id}/favorite")
async def toggle_revealed_file_favorite(
    file_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = get_revealed_file_storage()
    try:
        new_val = await storage.toggle_favorite(user.sub, file_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Catch InvalidId and other BSON errors for malformed file_id
        if "InvalidId" in type(e).__name__ or "bson" in type(e).__module__:
            raise HTTPException(status_code=400, detail="Invalid file ID format")
        raise
    return {"is_favorite": new_val}

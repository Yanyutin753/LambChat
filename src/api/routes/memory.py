"""
Memory API router - list and manage stored memories
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.deps import get_current_user_required
from src.infra.memory.client.types import MemoryType
from src.kernel.schemas.user import TokenPayload

router = APIRouter()

_VALID_MEMORY_TYPES = {mt.value for mt in MemoryType}


async def _get_backend():
    """Reuse the singleton memory backend from memory tools."""
    from src.infra.memory.tools import _get_backend

    return await _get_backend()


@router.get("/")
async def list_memories(
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    search: Optional[str] = Query(None, description="Search query (matches title, summary, tags)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(get_current_user_required),
):
    """List stored memories for the current user."""
    backend = await _get_backend()
    if not backend:
        return {"memories": [], "total": 0}

    if memory_type and memory_type not in _VALID_MEMORY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid memory_type. Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}",
        )

    query_filter: dict = {"user_id": user.sub}
    if memory_type:
        query_filter["memory_type"] = memory_type

    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query_filter["$or"] = [
            {"title": search_regex},
            {"summary": search_regex},
            {"tags": search_regex},
        ]

    collection = backend._collection
    total = await collection.count_documents(query_filter)

    cursor = (
        collection.find(
            query_filter,
            {
                "memory_id": 1,
                "title": 1,
                "summary": 1,
                "memory_type": 1,
                "tags": 1,
                "content": 1,
                "content_storage_mode": 1,
                "content_store_key": 1,
                "source": 1,
                "created_at": 1,
                "updated_at": 1,
                "access_count": 1,
            },
        )
        .sort("updated_at", -1)
        .skip(offset)
        .limit(limit)
    )

    memories = []
    async for doc in cursor:
        memory = {
            "memory_id": doc["memory_id"],
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "memory_type": doc.get("memory_type", ""),
            "tags": doc.get("tags", []),
            "content": doc.get("content", ""),
            "source": doc.get("source", ""),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "access_count": doc.get("access_count", 0),
            "has_full_content": doc.get("content_storage_mode") == "store",
        }
        memories.append(memory)

    return {"memories": memories, "total": total}


@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Get full content of a specific memory."""
    from src.infra.memory.client.native.content import hydrate_memory_text

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    doc = await backend._collection.find_one(
        {"user_id": user.sub, "memory_id": memory_id},
        {
            "memory_id": 1,
            "title": 1,
            "summary": 1,
            "memory_type": 1,
            "tags": 1,
            "content": 1,
            "content_storage_mode": 1,
            "content_store_key": 1,
            "context": 1,
            "source": 1,
            "created_at": 1,
            "updated_at": 1,
            "access_count": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Memory not found")

    full_content = await hydrate_memory_text(backend, doc)

    return {
        "memory_id": doc["memory_id"],
        "title": doc.get("title", ""),
        "summary": doc.get("summary", ""),
        "memory_type": doc.get("memory_type", ""),
        "tags": doc.get("tags", []),
        "content": full_content,
        "context": doc.get("context", ""),
        "source": doc.get("source", ""),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "access_count": doc.get("access_count", 0),
    }


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Delete a specific memory."""
    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    result = await backend.delete(user.sub, memory_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="Memory not found")

    return result


@router.post("/batch-delete")
async def batch_delete_memories(
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Delete multiple memories at once."""
    body = await request.json()
    memory_ids = body.get("memory_ids", [])
    if not memory_ids or not isinstance(memory_ids, list):
        raise HTTPException(status_code=400, detail="memory_ids must be a non-empty list")

    if len(memory_ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot delete more than 100 memories at once")

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    deleted = 0
    for mid in memory_ids:
        result = await backend.delete(user.sub, mid)
        if result.get("success"):
            deleted += 1

    return {"success": True, "deleted": deleted}

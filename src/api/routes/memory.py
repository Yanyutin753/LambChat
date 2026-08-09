"""
Memory API router - list and manage stored memories
"""

import json
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.api.deps import get_current_user_required
from src.infra.async_utils.blocking import run_blocking_io
from src.infra.logging import get_logger
from src.infra.memory.client.types import MemoryType
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.session.conversation_history_index import merge_source_refs
from src.infra.utils.datetime import parse_iso, to_iso, utc_now, utc_now_iso
from src.kernel.config import settings
from src.kernel.schemas.conversation_history import ConversationSourceRef
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

_VALID_MEMORY_TYPES = {mt.value for mt in MemoryType}
_VALID_SOURCES = {"manual", "auto_retained", "imported", "consolidated"}
_MEMORY_EXPORT_VERSION = 1
_DEFAULT_MEMORY_IMPORT_CONTENT_MAX_CHARS = 64_000
_DEFAULT_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS = 2_000_000
_DEFAULT_MEMORY_EXPORT_CONTENT_MAX_CHARS = 64_000


async def _get_backend():
    """Reuse the singleton memory backend from memory tools."""
    from src.infra.memory.tools import _get_backend

    return await _get_backend()


def _clean_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for tag in value:
        text = str(tag).strip()
        if text:
            tags.append(text[:40])
        if len(tags) >= 20:
            break
    return tags


def _clean_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or "").strip()
    if max_length is not None:
        return text[:max_length]
    return text


def _get_memory_import_content_max_chars() -> int:
    value = getattr(
        settings,
        "NATIVE_MEMORY_IMPORT_CONTENT_MAX_CHARS",
        _DEFAULT_MEMORY_IMPORT_CONTENT_MAX_CHARS,
    )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _DEFAULT_MEMORY_IMPORT_CONTENT_MAX_CHARS


def _get_memory_import_total_content_max_chars() -> int:
    value = getattr(
        settings,
        "NATIVE_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS",
        _DEFAULT_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS,
    )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _DEFAULT_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS


def _get_memory_export_content_max_chars() -> int:
    value = getattr(
        settings,
        "NATIVE_MEMORY_EXPORT_CONTENT_MAX_CHARS",
        _DEFAULT_MEMORY_EXPORT_CONTENT_MAX_CHARS,
    )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _DEFAULT_MEMORY_EXPORT_CONTENT_MAX_CHARS


def _validate_memory_content_size(content: str) -> None:
    max_chars = _get_memory_import_content_max_chars()
    if len(content) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Memory content too large (max {max_chars} characters)",
        )


def _validate_memory_import_total_content_size(raw_memories: list[Any]) -> None:
    max_chars = _get_memory_import_total_content_max_chars()
    total_chars = 0
    for raw in raw_memories:
        if not isinstance(raw, dict):
            continue
        total_chars += len(str(raw.get("content") or "").strip())
        if total_chars > max_chars:
            raise HTTPException(
                status_code=400,
                detail=f"Memory import content too large (max {max_chars} total characters)",
            )


def _memory_projection() -> dict[str, int]:
    return {
        "memory_id": 1,
        "user_id": 1,
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
        "accessed_at": 1,
        "access_count": 1,
        "source_refs": 1,
    }


async def _validated_source_ref_docs(user_id: str, raw_refs: Any) -> list[dict[str, str]]:
    normalized: list[ConversationSourceRef] = []
    if isinstance(raw_refs, list):
        for raw_ref in raw_refs:
            try:
                normalized.append(
                    raw_ref
                    if isinstance(raw_ref, ConversationSourceRef)
                    else ConversationSourceRef.model_validate(raw_ref)
                )
            except Exception:
                continue
    normalized = merge_source_refs([], normalized)
    if not normalized:
        return []
    try:
        allowed = await ConversationHistoryService().validate_source_refs(user_id, normalized)
    except Exception as exc:
        logger.warning(
            "Memory API source reference validation failed: error_type=%s",
            type(exc).__name__,
        )
        return []
    return [ref.model_dump() for ref in allowed]


def _json_iterencode_chunks(encoder: json.JSONEncoder, value: Any) -> list[str]:
    return list(encoder.iterencode(value))


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
        search_regex = {"$regex": re.escape(search), "$options": "i"}
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
                "source_refs": 1,
            },
        )
        .sort("updated_at", -1)
        .skip(offset)
        .limit(limit)
    )

    memories = []
    async for doc in cursor:
        source_refs = await _validated_source_ref_docs(user.sub, doc.get("source_refs"))
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
            "source_refs": source_refs,
        }
        memories.append(memory)

    return {"memories": memories, "total": total}


@router.post("/")
async def create_memory(
    payload: dict[str, Any] = Body(...),
    user: TokenPayload = Depends(get_current_user_required),
):
    """Create a new memory."""
    from src.infra.memory.client.native.content import build_content_fields
    from src.infra.memory.client.native.summaries import build_index_label

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    memory_type = _clean_text(payload.get("memory_type") or MemoryType.USER.value)
    if memory_type not in _VALID_MEMORY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid memory_type. Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}",
        )

    content = _clean_text(payload.get("content"))
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="Memory content must be at least 5 characters")
    _validate_memory_content_size(content)

    memory_id = uuid.uuid4().hex
    title = _clean_text(payload.get("title") or "New memory", 80)
    summary = _clean_text(payload.get("summary") or content, 300)
    tags = _clean_tags(payload.get("tags"))
    now = utc_now()
    source_refs = await _validated_source_ref_docs(user.sub, payload.get("source_refs"))

    content_fields = await build_content_fields(backend, user.sub, memory_id, content)
    embedding = None
    if hasattr(backend, "_maybe_embed"):
        embedding = await backend._maybe_embed(content)

    doc = {
        "memory_id": memory_id,
        "user_id": user.sub,
        "title": title,
        "summary": summary,
        "index_label": build_index_label(title, summary, content),
        "memory_type": memory_type,
        "context": _clean_text(payload.get("context")),
        "tags": tags,
        "source": "manual",
        "embedding": embedding,
        "created_at": now,
        "updated_at": now,
        "accessed_at": now,
        "access_count": 0,
        "source_refs": source_refs,
        **content_fields,
    }

    await backend._collection.insert_one(doc)
    if hasattr(backend, "_invalidate_cache"):
        await backend._invalidate_cache(user.sub)

    return {
        "success": True,
        "memory_id": memory_id,
        "title": title,
        "summary": summary,
        "memory_type": memory_type,
        "tags": tags,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    payload: dict[str, Any] = Body(...),
    user: TokenPayload = Depends(get_current_user_required),
):
    """Update an existing memory."""
    from src.infra.memory.client.native.content import (
        build_content_fields,
        delete_memory_content,
    )
    from src.infra.memory.client.native.summaries import build_index_label

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    existing = await backend._collection.find_one(
        {"user_id": user.sub, "memory_id": memory_id},
        {
            "content_storage_mode": 1,
            "content_store_key": 1,
            "source_refs": 1,
        },
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    update: dict[str, Any] = {"updated_at": utc_now()}

    if "title" in payload:
        update["title"] = _clean_text(payload["title"], 80)
    if "memory_type" in payload:
        mt = _clean_text(payload["memory_type"])
        if mt not in _VALID_MEMORY_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid memory_type. Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}",
            )
        update["memory_type"] = mt
    if "tags" in payload:
        update["tags"] = _clean_tags(payload["tags"])
    if "source" in payload:
        src = _clean_text(payload["source"])
        if src not in _VALID_SOURCES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid source. Must be one of: {', '.join(sorted(_VALID_SOURCES))}",
            )
        update["source"] = src
    if "source_refs" in payload:
        update["source_refs"] = await _validated_source_ref_docs(
            user.sub, payload.get("source_refs")
        )

    content = payload.get("content")
    if content is not None:
        content = _clean_text(content)
        if len(content) < 5:
            raise HTTPException(
                status_code=400, detail="Memory content must be at least 5 characters"
            )
        _validate_memory_content_size(content)

        content_fields = await build_content_fields(backend, user.sub, memory_id, content)
        update["content"] = content_fields.get("content", content)
        update["content_storage_mode"] = content_fields["content_storage_mode"]
        if "content_store_key" in content_fields:
            update["content_store_key"] = content_fields["content_store_key"]

        if hasattr(backend, "_maybe_embed"):
            embedding = await backend._maybe_embed(content)
            if embedding is not None:
                update["embedding"] = embedding

    if "summary" in payload:
        update["summary"] = _clean_text(payload["summary"], 300)
    elif content is not None:
        update["summary"] = _clean_text(content, 300)

    title = update.get("title") or existing.get("title", "")
    summary = update.get("summary") or existing.get("summary", "")
    full_content = content if content is not None else existing.get("content", "")
    update["index_label"] = build_index_label(title, summary, full_content)

    await backend._collection.update_one(
        {"user_id": user.sub, "memory_id": memory_id},
        {"$set": update},
    )

    old_key = (
        existing.get("content_store_key")
        if existing.get("content_storage_mode") == "store"
        else None
    )
    new_key = update.get("content_store_key")
    if old_key and new_key and old_key != new_key:
        await delete_memory_content(backend, user.sub, old_key)

    if hasattr(backend, "_invalidate_cache"):
        await backend._invalidate_cache(user.sub)

    return {"success": True, "memory_id": memory_id}


@router.get("/export")
async def export_memories(
    user: TokenPayload = Depends(get_current_user_required),
):
    """Export all stored memories for the current user."""
    from src.infra.memory.client.native.content import hydrate_memory_text

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    cursor = backend._collection.find({"user_id": user.sub}, _memory_projection())
    if hasattr(cursor, "sort"):
        cursor = cursor.sort("updated_at", -1)

    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    exported_at = utc_now_iso()

    async def stream_export():
        yield f'{{"version":{_MEMORY_EXPORT_VERSION},"exported_at":'
        for chunk in encoder.iterencode(exported_at):
            yield chunk
        yield ',"memories":['

        first = True
        async for doc in cursor:
            content = await hydrate_memory_text(backend, doc)
            source_refs = await _validated_source_ref_docs(user.sub, doc.get("source_refs"))
            content_original_chars = len(content)
            max_content_chars = _get_memory_export_content_max_chars()
            content_truncated = content_original_chars > max_content_chars
            if content_truncated:
                content = content[:max_content_chars]
            item = {
                "memory_id": doc["memory_id"],
                "title": doc.get("title", ""),
                "summary": doc.get("summary", ""),
                "memory_type": doc.get("memory_type", ""),
                "tags": doc.get("tags", []),
                "content": content,
                "context": doc.get("context", ""),
                "source": doc.get("source", ""),
                "created_at": to_iso(doc.get("created_at")),
                "updated_at": to_iso(doc.get("updated_at")),
                "accessed_at": to_iso(doc.get("accessed_at")),
                "access_count": doc.get("access_count", 0),
                "source_refs": source_refs,
            }
            if content_truncated:
                item["content_truncated"] = True
                item["content_original_chars"] = content_original_chars
            if first:
                first = False
            else:
                yield ","
            for chunk in await run_blocking_io(_json_iterencode_chunks, encoder, item):
                yield chunk

        yield "]}"

    return StreamingResponse(
        stream_export(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="lambchat-memory-export.json"'},
    )


@router.post("/import")
async def import_memories(
    payload: dict[str, Any] = Body(...),
    user: TokenPayload = Depends(get_current_user_required),
):
    """Import memories for the current user, overwriting matching memory IDs."""
    from src.infra.memory.client.native.content import build_content_fields, delete_memory_content
    from src.infra.memory.client.native.summaries import build_index_label

    backend = await _get_backend()
    if not backend:
        raise HTTPException(status_code=404, detail="Memory backend not available")

    raw_memories = payload.get("memories")
    if not isinstance(raw_memories, list):
        raise HTTPException(status_code=400, detail="memories must be a list")
    if len(raw_memories) > 1000:
        raise HTTPException(status_code=400, detail="Cannot import more than 1000 memories at once")
    _validate_memory_import_total_content_size(raw_memories)

    created = 0
    overwritten = 0
    now = utc_now()

    for raw in raw_memories:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Each memory must be an object")

        memory_type = _clean_text(raw.get("memory_type") or MemoryType.USER.value)
        if memory_type not in _VALID_MEMORY_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid memory_type. Must be one of: {', '.join(sorted(_VALID_MEMORY_TYPES))}",
            )

        content = _clean_text(raw.get("content"))
        if len(content) < 5:
            raise HTTPException(
                status_code=400, detail="Memory content must be at least 5 characters"
            )
        _validate_memory_content_size(content)

        memory_id = _clean_text(raw.get("memory_id")) or uuid.uuid4().hex
        title = _clean_text(raw.get("title") or "Imported memory", 80)
        summary = _clean_text(raw.get("summary") or content, 300)
        tags = _clean_tags(raw.get("tags"))
        source_refs = await _validated_source_ref_docs(user.sub, raw.get("source_refs"))

        existing_doc = await backend._collection.find_one(
            {"user_id": user.sub, "memory_id": memory_id},
            {"content_storage_mode": 1, "content_store_key": 1},
        )

        content_fields = await build_content_fields(backend, user.sub, memory_id, content)
        embedding = None
        if hasattr(backend, "_maybe_embed"):
            embedding = await backend._maybe_embed(content)

        created_at = (
            parse_iso(raw["created_at"])
            if isinstance(raw.get("created_at"), str) and raw["created_at"].strip()
            else now
        )
        updated_at = (
            parse_iso(raw["updated_at"])
            if isinstance(raw.get("updated_at"), str) and raw["updated_at"].strip()
            else now
        )
        accessed_at = (
            parse_iso(raw["accessed_at"])
            if isinstance(raw.get("accessed_at"), str) and raw["accessed_at"].strip()
            else updated_at
        )

        try:
            access_count = max(0, int(raw.get("access_count") or 0))
        except (TypeError, ValueError):
            access_count = 0

        doc = {
            "memory_id": memory_id,
            "user_id": user.sub,
            "title": title,
            "summary": summary,
            "index_label": build_index_label(title, summary, content),
            "memory_type": memory_type,
            "context": _clean_text(raw.get("context")),
            "tags": tags,
            "source": _clean_text(raw.get("source") or "imported"),
            "embedding": embedding,
            "created_at": created_at,
            "updated_at": updated_at,
            "accessed_at": accessed_at,
            "access_count": access_count,
            "source_refs": source_refs,
            **content_fields,
        }

        result = await backend._collection.replace_one(
            {"user_id": user.sub, "memory_id": memory_id},
            doc,
            upsert=True,
        )
        if getattr(result, "matched_count", 0):
            overwritten += 1
        else:
            created += 1

        old_key = existing_doc.get("content_store_key") if existing_doc else None
        new_key = content_fields.get("content_store_key")
        if (
            existing_doc
            and existing_doc.get("content_storage_mode") == "store"
            and old_key
            and old_key != new_key
        ):
            await delete_memory_content(backend, user.sub, old_key)

    imported = created + overwritten
    if imported and hasattr(backend, "_invalidate_cache"):
        await backend._invalidate_cache(user.sub)

    return {
        "success": True,
        "imported": imported,
        "created": created,
        "overwritten": overwritten,
    }


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
            "source_refs": 1,
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Memory not found")

    full_content = await hydrate_memory_text(backend, doc)
    source_refs = await _validated_source_ref_docs(user.sub, doc.get("source_refs"))

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
        "source_refs": source_refs,
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

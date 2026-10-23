"""
Memory API router - list and manage stored memories
"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument

from src.api.deps import get_current_user_required
from src.infra.async_utils.blocking import run_blocking_io
from src.infra.logging import get_logger
from src.infra.memory.cleanup import vector_pending_fields
from src.infra.memory.client.types import MemoryType
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.session.conversation_history_index import merge_source_refs
from src.infra.utils.datetime import parse_iso, to_iso, utc_now, utc_now_iso
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
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
_SOURCE_REF_BATCH_SIZE = 50
_MAX_IMPORT_ORIGIN_SESSIONS = 50_000


async def _get_backend():
    """Reuse the singleton memory backend from memory tools."""
    from src.infra.memory.tools import _get_backend

    return await _get_backend()


async def _write_vector_index(
    backend: Any, user_id: str, memory_id: str, doc: dict[str, Any]
) -> None:
    from src.infra.memory.cleanup import write_memory_vector

    await write_memory_vector(
        backend,
        user_id=user_id,
        memory_id=memory_id,
        embedding=doc.get("embedding"),
        memory_type=doc.get("memory_type") or MemoryType.USER.value,
        context=doc.get("context"),
        updated_at_ts=int(doc["updated_at"].timestamp()),
        scope=doc.get("scope") or "user",
        project_id=doc.get("project_id"),
    )


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
        raise AppError(ErrorCode.MEMORY_CONTENT_TOO_LARGE, args={"max": max_chars})


def _validate_memory_import_total_content_size(raw_memories: list[Any]) -> None:
    max_chars = _get_memory_import_total_content_max_chars()
    total_chars = 0
    for raw in raw_memories:
        if not isinstance(raw, dict):
            continue
        if raw.get("content_truncated") is True:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Truncated memory content cannot be imported as a complete memory.",
            )
        total_chars += len(str(raw.get("content") or "").strip())
        if total_chars > max_chars:
            raise AppError(ErrorCode.MEMORY_IMPORT_TOO_LARGE, args={"max": max_chars})


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
        "origin_session_ids": 1,
        "scope": 1,
        "project_id": 1,
    }


def _normalized_source_refs(raw_refs: Any) -> list[ConversationSourceRef]:
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
    return merge_source_refs([], normalized)


async def _validated_source_ref_docs_batch(
    user_id: str, raw_groups: list[Any]
) -> list[list[dict[str, str]]]:
    results: list[list[dict[str, str]]] = []
    for index in range(0, len(raw_groups), _SOURCE_REF_BATCH_SIZE):
        groups = [
            _normalized_source_refs(raw)
            for raw in raw_groups[index : index + _SOURCE_REF_BATCH_SIZE]
        ]
        refs = [ref for group in groups for ref in group]
        allowed_pairs: set[tuple[str, str]] = set()
        if refs:
            try:
                allowed = await ConversationHistoryService().validate_source_refs(
                    user_id, refs, limit=len(refs)
                )
                allowed_pairs = {(ref.session_id, ref.run_id) for ref in allowed}
            except Exception as exc:
                logger.warning(
                    "Memory API source reference validation failed: error_type=%s",
                    type(exc).__name__,
                )
        results.extend(
            [ref.model_dump() for ref in group if (ref.session_id, ref.run_id) in allowed_pairs]
            for group in groups
        )
    return results


async def _validated_source_ref_docs(user_id: str, raw_refs: Any) -> list[dict[str, str]]:
    return (await _validated_source_ref_docs_batch(user_id, [raw_refs]))[0]


async def _iter_memory_batches_with_source_refs(
    user_id: str, cursor: AsyncIterable[dict[str, Any]]
) -> AsyncIterator[list[tuple[dict[str, Any], list[dict[str, str]]]]]:
    batch: list[dict[str, Any]] = []
    async for doc in cursor:
        batch.append(doc)
        if len(batch) == _SOURCE_REF_BATCH_SIZE:
            validated = await _validated_source_ref_docs_batch(
                user_id, [item.get("source_refs") for item in batch]
            )
            yield list(zip(batch, validated, strict=True))
            batch = []
    if batch:
        validated = await _validated_source_ref_docs_batch(
            user_id, [item.get("source_refs") for item in batch]
        )
        yield list(zip(batch, validated, strict=True))


async def _iter_memories_with_source_refs(
    user_id: str, cursor: AsyncIterable[dict[str, Any]]
) -> AsyncIterator[tuple[dict[str, Any], list[dict[str, str]]]]:
    async for batch in _iter_memory_batches_with_source_refs(user_id, cursor):
        for item in batch:
            yield item


def _json_iterencode_chunks(encoder: json.JSONEncoder, value: Any) -> list[str]:
    return list(encoder.iterencode(value))


@router.get("/")
async def list_memories(
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    search: Optional[str] = Query(
        None, description="Search query (matches title, summary, tags, context)"
    ),
    context: Optional[str] = Query(None, description="Filter by exact context label"),
    source: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(get_current_user_required),
):
    """List stored memories for the current user."""
    backend = await _get_backend()
    if not backend:
        return {"memories": [], "total": 0}

    if memory_type and memory_type not in _VALID_MEMORY_TYPES:
        raise AppError(
            ErrorCode.INVALID_MEMORY_TYPE, args={"allowed": ", ".join(sorted(_VALID_MEMORY_TYPES))}
        )

    query_filter: dict = {"user_id": user.sub}
    if memory_type:
        query_filter["memory_type"] = memory_type
    if context:
        query_filter["context"] = context
    if source:
        query_filter["source"] = source

    if search:
        search_regex = {"$regex": re.escape(search), "$options": "i"}
        query_filter["$or"] = [
            {"title": search_regex},
            {"summary": search_regex},
            {"tags": search_regex},
            {"context": search_regex},
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
    async for doc, source_refs in _iter_memories_with_source_refs(user.sub, cursor):
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

    result: dict[str, Any] = {"memories": memories, "total": total}
    if search_status := getattr(backend, "search_status", None):
        result["search_status"] = search_status
    return result


@router.post("/")
async def create_memory(
    payload: dict[str, Any] = Body(...),
    user: TokenPayload = Depends(get_current_user_required),
):
    """Create a new memory."""
    from src.infra.memory.client.native.content import build_content_fields
    from src.infra.memory.client.native.summaries import build_index_label
    from src.infra.memory.staging import insert_content_memory

    backend = await _get_backend()
    if not backend:
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    memory_type = _clean_text(payload.get("memory_type") or MemoryType.USER.value)
    if memory_type not in _VALID_MEMORY_TYPES:
        raise AppError(
            ErrorCode.INVALID_MEMORY_TYPE, args={"allowed": ", ".join(sorted(_VALID_MEMORY_TYPES))}
        )

    content = _clean_text(payload.get("content"))
    if len(content) < 5:
        raise AppError(ErrorCode.MEMORY_CONTENT_TOO_SHORT)
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
        "revision_id": uuid.uuid4().hex,
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

    doc.update(vector_pending_fields(doc["revision_id"]))
    try:
        await insert_content_memory(backend, doc)
        await _write_vector_index(backend, user.sub, memory_id, doc)
    finally:
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
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    existing = await backend._collection.find_one(
        {"user_id": user.sub, "memory_id": memory_id},
        {
            "title": 1,
            "summary": 1,
            "content": 1,
            "index_label": 1,
            "embedding": 1,
            "memory_type": 1,
            "context": 1,
            "scope": 1,
            "project_id": 1,
            "content_storage_mode": 1,
            "content_store_key": 1,
            "source_refs": 1,
        },
    )
    if not existing:
        raise AppError(ErrorCode.MEMORY_NOT_FOUND)

    update: dict[str, Any] = {"updated_at": utc_now(), "revision_id": uuid.uuid4().hex}

    if "title" in payload:
        update["title"] = _clean_text(payload["title"], 80)
    if "memory_type" in payload:
        mt = _clean_text(payload["memory_type"])
        if mt not in _VALID_MEMORY_TYPES:
            raise AppError(
                ErrorCode.INVALID_MEMORY_TYPE,
                args={"allowed": ", ".join(sorted(_VALID_MEMORY_TYPES))},
            )
        update["memory_type"] = mt
    if "tags" in payload:
        update["tags"] = _clean_tags(payload["tags"])
    if "source" in payload:
        src = _clean_text(payload["source"])
        if src not in _VALID_SOURCES:
            raise AppError(
                ErrorCode.INVALID_MEMORY_SOURCE, args={"allowed": ", ".join(sorted(_VALID_SOURCES))}
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
            raise AppError(ErrorCode.MEMORY_CONTENT_TOO_SHORT)
        _validate_memory_content_size(content)

        content_fields = await build_content_fields(
            backend,
            user.sub,
            memory_id,
            content,
            store_key=f"memory:{memory_id}:{uuid.uuid4().hex}",
        )
        update.update(content_fields)

        update["embedding"] = (
            await backend._maybe_embed(content) if hasattr(backend, "_maybe_embed") else None
        )

    if "summary" in payload:
        update["summary"] = _clean_text(payload["summary"], 300)
    elif content is not None:
        update["summary"] = _clean_text(content, 300)

    title = update.get("title") or existing.get("title", "")
    summary = update.get("summary") or existing.get("summary", "")
    full_content = content if content is not None else existing.get("content", "")
    if any(field in payload for field in ("title", "summary", "content")):
        update["index_label"] = build_index_label(title, summary, full_content)

    from src.infra.memory.cleanup import content_update
    from src.infra.memory.staging import content_commit_query

    update.update(vector_pending_fields(update["revision_id"]))
    try:
        write_result = await backend._collection.update_one(
            {**content_commit_query(user.sub, memory_id, update), "user_id": user.sub},
            content_update(user.sub, update) if content is not None else {"$set": update},
        )
    except (Exception, asyncio.CancelledError):
        if hasattr(backend, "_invalidate_cache"):
            await backend._invalidate_cache(user.sub)
        raise
    if not int(getattr(write_result, "matched_count", 1) or 0):
        if content is not None:
            await delete_memory_content(backend, user.sub, update.get("content_store_key"))
        raise AppError(ErrorCode.MEMORY_NOT_FOUND)
    try:
        await _write_vector_index(backend, user.sub, memory_id, {**existing, **update})
        old_key = (
            existing.get("content_store_key")
            if existing.get("content_storage_mode") == "store"
            else None
        )
        new_key = update.get("content_store_key")
        if content is not None and old_key and old_key != new_key:
            await delete_memory_content(backend, user.sub, old_key)
    finally:
        if hasattr(backend, "_invalidate_cache"):
            await backend._invalidate_cache(user.sub)

    return {"success": True, "memory_id": memory_id}


@router.get("/export")
async def export_memories(
    user: TokenPayload = Depends(get_current_user_required),
):
    """Export all stored memories for the current user."""
    from src.infra.memory.client.native.content import hydrate_memory_texts

    backend = await _get_backend()
    if not backend:
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

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
        async for batch in _iter_memory_batches_with_source_refs(user.sub, cursor):
            contents = await hydrate_memory_texts(backend, [doc for doc, _ in batch])
            for (doc, source_refs), content in zip(batch, contents, strict=True):
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
                    "origin_session_ids": doc.get("origin_session_ids") or [],
                    "scope": doc.get("scope") or "user",
                    "project_id": doc.get("project_id") if doc.get("scope") == "project" else None,
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
    validate_only: bool = False,
):
    """Import memories for the current user, overwriting matching memory IDs."""
    from src.infra.memory.cleanup import replacement_cleanup_expression
    from src.infra.memory.client.native.content import (
        build_content_fields,
        delete_memory_content,
        hydrate_memory_text_status,
    )
    from src.infra.memory.client.native.summaries import build_index_label
    from src.infra.memory.staging import (
        content_commit_query,
        owned_content_query,
        remaining_content_stages,
    )

    backend = await _get_backend()
    if not backend:
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    raw_memories = payload.get("memories")
    if not isinstance(raw_memories, list):
        raise AppError(ErrorCode.MEMORIES_MUST_BE_LIST)
    if len(raw_memories) > 1000:
        raise AppError(ErrorCode.MEMORY_IMPORT_LIMIT)
    _validate_memory_import_total_content_size(raw_memories)

    from src.infra.folder.storage import get_project_storage
    from src.infra.memory.scope import ScopeResolutionError, resolve_retain_scope

    prepared: list[dict[str, Any]] = []
    now = utc_now()
    authorized_projects: set[str] = set()
    origin_count = 0
    for raw in raw_memories:
        if not isinstance(raw, dict):
            raise AppError(ErrorCode.MEMORY_MUST_BE_OBJECT)
        origins = raw.get("origin_session_ids", [])
        if not isinstance(origins, list) or any(
            not isinstance(sid, str) or not sid.strip() or len(sid) > 1024 for sid in origins
        ):
            raise AppError(ErrorCode.VALIDATION_ERROR, message="Invalid memory source sessions.")
        origin_count += len(origins)
        if origin_count > _MAX_IMPORT_ORIGIN_SESSIONS:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, message="Too many memory source sessions in one batch."
            )
        try:
            scope, project_id = resolve_retain_scope(
                scope=raw.get("scope"),
                project_id=_clean_text(raw.get("project_id")) or None,
            )
        except ScopeResolutionError as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, message=str(exc)) from exc
        if scope == "project" and project_id and project_id not in authorized_projects:
            if not await get_project_storage().get_by_id(project_id, user.sub):
                raise AppError(ErrorCode.PROJECT_NOT_FOUND)
            authorized_projects.add(project_id)
        memory_type = _clean_text(raw.get("memory_type") or MemoryType.USER.value)
        if memory_type not in _VALID_MEMORY_TYPES:
            raise AppError(
                ErrorCode.INVALID_MEMORY_TYPE,
                args={"allowed": ", ".join(sorted(_VALID_MEMORY_TYPES))},
            )

        content = _clean_text(raw.get("content"))
        if len(content) < 5:
            raise AppError(ErrorCode.MEMORY_CONTENT_TOO_SHORT)
        _validate_memory_content_size(content)

        memory_id = _clean_text(raw.get("memory_id")) or uuid.uuid4().hex
        title = _clean_text(raw.get("title") or "Imported memory", 80)
        summary = _clean_text(raw.get("summary") or content, 300)
        tags = _clean_tags(raw.get("tags"))

        try:
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
        except (ValueError, TypeError) as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="Invalid memory timestamp.") from exc

        try:
            access_count = max(0, int(raw.get("access_count") or 0))
        except (TypeError, ValueError, OverflowError):
            access_count = 0

        doc: dict[str, Any] = {
            "memory_id": memory_id,
            "user_id": user.sub,
            "revision_id": uuid.uuid4().hex,
            "title": title,
            "summary": summary,
            "index_label": build_index_label(title, summary, content),
            "memory_type": memory_type,
            "context": _clean_text(raw.get("context")),
            "tags": tags,
            "source": _clean_text(raw.get("source") or "imported"),
            "created_at": created_at,
            "updated_at": updated_at,
            "accessed_at": accessed_at,
            "access_count": access_count,
            "scope": scope,
            "project_id": project_id,
            "content": content,
            "origin_session_ids": list(dict.fromkeys(origins)),
        }

        prepared.append(doc)

    if validate_only:
        return {
            "success": True,
            "validated": len(prepared),
            "limits": {
                "max_records": 1000,
                "max_origin_sessions": _MAX_IMPORT_ORIGIN_SESSIONS,
                "max_content_chars": _get_memory_import_content_max_chars(),
                "max_total_content_chars": _get_memory_import_total_content_max_chars(),
            },
        }

    created = 0
    overwritten = 0
    validated_sources = await _validated_source_ref_docs_batch(
        user.sub,
        [raw.get("source_refs") for raw in raw_memories],
    )
    supplied_ids = list(dict.fromkeys(_clean_text(raw.get("memory_id")) for raw in raw_memories))
    supplied_ids = [memory_id for memory_id in supplied_ids if memory_id]
    previous_by_id = {}
    if supplied_ids:
        async for previous in backend._collection.find(
            {"user_id": user.sub, "memory_id": {"$in": supplied_ids}},
            {
                "memory_id": 1,
                "user_id": 1,
                "content": 1,
                "content_storage_mode": 1,
                "content_store_key": 1,
                "embedding": 1,
            },
        ):
            previous_by_id[previous["memory_id"]] = previous
    write_attempted = False
    try:
        for doc, source_refs in zip(prepared, validated_sources, strict=True):
            memory_id = doc["memory_id"]
            content = doc["content"]
            content_fields = await build_content_fields(
                backend,
                user.sub,
                memory_id,
                content,
                store_key=f"memory:{memory_id}:{uuid.uuid4().hex}",
            )
            doc.update(content_fields)
            doc["source_refs"] = source_refs
            previous = previous_by_id.get(memory_id)
            embedding = previous.get("embedding") if previous else None
            previous_text, complete = (
                await hydrate_memory_text_status(backend, previous)
                if previous and isinstance(embedding, list) and embedding
                else ("", False)
            )
            doc["embedding"] = (
                embedding
                if complete and previous_text == content
                else (
                    await backend._maybe_embed(content)
                    if hasattr(backend, "_maybe_embed")
                    else None
                )
            )
            doc.update(vector_pending_fields(doc["revision_id"]))
            write_attempted = True
            staged = "_content_stage" in content_fields
            query = content_commit_query(user.sub, memory_id, content_fields)
            if not staged and getattr(backend._collection, "database", None) is not None:
                query = owned_content_query(user.sub, memory_id)
            existing_doc = await backend._collection.find_one_and_update(
                query,
                [
                    {
                        "$replaceWith": {
                            "$mergeObjects": [
                                {
                                    "$literal": {
                                        key: value
                                        for key, value in doc.items()
                                        if key != "_content_stage"
                                    }
                                },
                                {
                                    "_id": "$_id",
                                    "_content_stages": remaining_content_stages(content_fields),
                                    "_content_cleanup": replacement_cleanup_expression(
                                        user.sub, content_fields.get("content_store_key")
                                    ),
                                    "origin_session_ids": {
                                        "$setUnion": [
                                            {"$ifNull": ["$origin_session_ids", []]},
                                            {"$literal": doc["origin_session_ids"]},
                                        ]
                                    },
                                },
                            ]
                        }
                    }
                ],
                upsert=not staged,
                return_document=ReturnDocument.BEFORE,
                projection={"user_id": 1, "content_storage_mode": 1, "content_store_key": 1},
            )
            if staged and existing_doc is None:
                raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)
            await _write_vector_index(backend, user.sub, memory_id, doc)
            if existing_doc is not None and existing_doc.get("user_id") == user.sub:
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
    finally:
        if write_attempted and hasattr(backend, "_invalidate_cache"):
            await backend._invalidate_cache(user.sub)

    imported = created + overwritten
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
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    doc = await backend._collection.find_one(
        {"user_id": user.sub, "memory_id": memory_id},
        _memory_projection(),
    )
    if not doc:
        raise AppError(ErrorCode.MEMORY_NOT_FOUND)

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
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    result = await backend.delete(user.sub, memory_id)
    if not result.get("success"):
        raise AppError(ErrorCode.MEMORY_NOT_FOUND)

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
        raise AppError(ErrorCode.MEMORY_IDS_REQUIRED)

    if len(memory_ids) > 100:
        raise AppError(ErrorCode.MEMORY_DELETE_LIMIT)

    backend = await _get_backend()
    if not backend:
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)

    deleted = 0
    for mid in memory_ids:
        result = await backend.delete(user.sub, mid)
        if result.get("success"):
            deleted += 1

    return {"success": True, "deleted": deleted}

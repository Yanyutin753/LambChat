"""Content storage helpers for the native memory backend."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, cast

from langgraph.store.base import GetOp

from src.kernel.config import settings

_NOT_LOADED = object()


def sanitize_memory_text(value: Any) -> str:
    """Escape internal control frames before memory text reaches a model."""
    from src.infra.memory.control_frames import escape_control_frame_tags

    return escape_control_frame_tags(value)


async def maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


def memory_store_namespace(user_id: str) -> tuple[str, ...]:
    base = str(getattr(settings, "NATIVE_MEMORY_STORE_NAMESPACE", "memories") or "memories")
    return (base, user_id, "content")


async def get_store(backend) -> Any:
    if backend._store is None:
        from src.infra.storage.mongodb_store import acreate_store

        backend._store = await acreate_store()
    return backend._store


async def store_put(backend, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
    store = await get_store(backend)
    if store is None:
        return
    if hasattr(store, "aput"):
        await store.aput(namespace, key, value)
        return
    if hasattr(store, "put"):
        await maybe_await(store.put(namespace, key, value))


async def store_get(backend, namespace: tuple[str, ...], key: str) -> Any:
    store = await get_store(backend)
    if store is None:
        return None
    if hasattr(store, "aget"):
        return await store.aget(namespace, key)
    if hasattr(store, "get"):
        return await maybe_await(store.get(namespace, key))
    return None


async def batch_get_memory_contents(backend, docs: list[dict[str, Any]]) -> list[Any] | None:
    """Return aligned stored items; None keeps the existing per-item fallback."""
    indexed_ops = [
        (
            index,
            GetOp(
                memory_store_namespace(cast(str, doc.get("user_id"))), str(doc["content_store_key"])
            ),
        )
        for index, doc in enumerate(docs)
        if doc.get("content_storage_mode", doc.get("storage_mode")) == "store"
        and doc.get("content_store_key")
    ]
    if not indexed_ops:
        return None
    try:
        store = await get_store(backend)
        batch = getattr(store, "abatch", None)
        if not callable(batch):
            return None
        ttl_config = getattr(store, "ttl_config", None) or {}
        refresh_ttl = ttl_config.get("refresh_on_read", True)
        loaded = await maybe_await(
            batch([op._replace(refresh_ttl=refresh_ttl) for _, op in indexed_ops])
        )
        if len(loaded) != len(indexed_ops):
            return None
    except Exception:
        return None
    items: list[Any] = [None] * len(docs)
    for (index, _), item in zip(indexed_ops, loaded, strict=True):
        items[index] = item
    return items


async def hydrate_memory_texts(backend, docs: list[dict[str, Any]]) -> list[str]:
    items = await batch_get_memory_contents(backend, docs)
    texts = []
    for index, doc in enumerate(docs):
        text, _complete = await hydrate_memory_text_status(
            backend, doc, item=items[index] if items is not None else _NOT_LOADED
        )
        texts.append(text)
    return texts


async def store_delete(backend, namespace: tuple[str, ...], key: str) -> None:
    store = await get_store(backend)
    if store is None:
        return
    if hasattr(store, "adelete"):
        await store.adelete(namespace, key)
        return
    if hasattr(store, "delete"):
        await maybe_await(store.delete(namespace, key))
        return
    if hasattr(store, "aput"):
        await store.aput(namespace, key, None)
        return
    if hasattr(store, "put"):
        await maybe_await(store.put(namespace, key, None))
        return
    import logging

    logging.getLogger(__name__).warning(
        "[NativeMemory] store_delete: no compatible delete method found on store"
    )


async def delete_memory_content(backend, user_id: str, content_store_key: str | None) -> None:
    if not content_store_key:
        return
    await store_delete(backend, memory_store_namespace(user_id), content_store_key)


def inline_preview(content: str) -> str:
    max_chars = int(getattr(settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 1200))
    if len(content) <= max_chars:
        return content
    if max_chars <= 3:
        return content[:max_chars]
    return content[: max_chars - 3].rstrip() + "..."


async def build_content_fields(
    backend, user_id: str, memory_id: str, content: str
) -> dict[str, Any]:
    preview = inline_preview(content)
    max_chars = int(getattr(settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 1200))
    if len(content) <= max_chars:
        return {
            "content": preview,
            "content_storage_mode": "inline",
            "content_store_key": None,
        }

    store_key = f"memory:{memory_id}"
    await store_put(
        backend,
        memory_store_namespace(user_id),
        store_key,
        {"text": content, "memory_id": memory_id},
    )
    return {
        "content": preview,
        "content_storage_mode": "store",
        "content_store_key": store_key,
    }


async def hydrate_memory_text(backend, doc: dict[str, Any]) -> str:
    text, _complete = await hydrate_memory_text_status(backend, doc)
    return text


async def hydrate_memory_text_status(
    backend, doc: dict[str, Any], *, item: Any = _NOT_LOADED
) -> tuple[str, bool]:
    preview = sanitize_memory_text(doc.get("content", ""))
    if doc.get("content_storage_mode") != "store" or not doc.get("content_store_key"):
        return preview, True

    if item is _NOT_LOADED:
        try:
            item = await store_get(
                backend,
                memory_store_namespace(doc["user_id"]),
                doc["content_store_key"],
            )
        except Exception:
            # The preview remains useful while the optional content store is unavailable.
            return preview, False
    if item is None:
        return preview, False
    value = getattr(item, "value", item)
    if isinstance(value, dict) and value.get("text") is not None:
        return sanitize_memory_text(value["text"]), True
    return preview, False


async def hydrate_formatted_memory(
    backend, memory: dict[str, Any], *, item: Any = _NOT_LOADED
) -> dict[str, Any]:
    if memory.get("storage_mode") != "store":
        memory.setdefault("preview", memory.get("text", ""))
        memory.setdefault("storage_mode", "inline")
        memory["text_complete"] = True
        return memory

    doc = {
        "user_id": memory.get("user_id"),
        "content": memory.get("text", ""),
        "content_storage_mode": memory.get("storage_mode"),
        "content_store_key": memory.get("content_store_key"),
    }
    full_text, complete = await hydrate_memory_text_status(backend, doc, item=item)
    memory["preview"] = memory.get("text", "")
    memory["text"] = full_text
    memory["text_complete"] = complete
    if not complete:
        memory["text_incomplete_reason"] = "content_store_unavailable"
    return memory

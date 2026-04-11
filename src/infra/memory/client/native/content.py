"""Content storage helpers for the native memory backend."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from src.kernel.config import settings


async def maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable):
        return await value
    return value


def memory_store_namespace(user_id: str) -> tuple[str, ...]:
    base = str(getattr(settings, "NATIVE_MEMORY_STORE_NAMESPACE", "memories") or "memories")
    return (base, user_id, "content")


def get_store(backend) -> Any:
    if backend._store is None:
        from src.infra.storage.mongodb_store import create_store

        backend._store = create_store()
    return backend._store


async def store_put(backend, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
    store = get_store(backend)
    if store is None:
        return
    if hasattr(store, "aput"):
        await store.aput(namespace, key, value)
        return
    if hasattr(store, "put"):
        await maybe_await(store.put(namespace, key, value))


async def store_get(backend, namespace: tuple[str, ...], key: str) -> Any:
    store = get_store(backend)
    if store is None:
        return None
    if hasattr(store, "aget"):
        return await store.aget(namespace, key)
    if hasattr(store, "get"):
        return await maybe_await(store.get(namespace, key))
    return None


async def store_delete(backend, namespace: tuple[str, ...], key: str) -> None:
    store = get_store(backend)
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


async def delete_memory_content(backend, user_id: str, content_store_key: str | None) -> None:
    if not content_store_key:
        return
    await store_delete(backend, memory_store_namespace(user_id), content_store_key)


def inline_preview(content: str) -> str:
    max_chars = int(getattr(settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 1200))
    if len(content) <= max_chars:
        return content[:5000]
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
    if doc.get("content_storage_mode") != "store" or not doc.get("content_store_key"):
        return str(doc.get("content", ""))

    item = await store_get(
        backend,
        memory_store_namespace(doc["user_id"]),
        doc["content_store_key"],
    )
    if item is None:
        return str(doc.get("content", ""))
    value = getattr(item, "value", item)
    if isinstance(value, dict):
        return str(value.get("text") or doc.get("content", ""))
    return str(doc.get("content", ""))


async def hydrate_formatted_memory(backend, memory: dict[str, Any]) -> dict[str, Any]:
    if memory.get("storage_mode") != "store":
        memory.setdefault("preview", memory.get("text", ""))
        memory.setdefault("storage_mode", "inline")
        return memory

    doc = {
        "user_id": memory.get("user_id"),
        "content": memory.get("text", ""),
        "content_storage_mode": memory.get("storage_mode"),
        "content_store_key": memory.get("content_store_key"),
    }
    full_text = await hydrate_memory_text(backend, doc)
    memory["preview"] = memory.get("text", "")
    memory["text"] = full_text
    return memory

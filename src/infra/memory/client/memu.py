"""
memU Cloud API Client - Cross-session Long-term Memory

Provides integration with memU cloud API (api.memu.so) for persistent,
cross-session memory storage and retrieval.

Documentation: https://github.com/NevaMind-AI/memU
"""

import asyncio
import json
import os
import tempfile
from typing import Any, Optional

import httpx

from src.infra.logging import get_logger
from src.infra.memory.client.base import (
    MemoryBackend,
    clear_loop_locals,
    get_client_lock,
    get_request_semaphore,
    with_retry,
)
from src.kernel.config import settings

logger = get_logger(__name__)


# ============================================================================
# AsyncMemU - Cloud API Client
# ============================================================================


class AsyncMemU:
    """
    Async client for memU cloud API.

    Wraps the memU REST API (api.memu.so) with retry logic and concurrency control.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )

    async def memorize(
        self,
        resource_url: str,
        modality: str = "conversation",
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Submit a memorize task to memU cloud.

        Args:
            resource_url: URL or content to memorize
            modality: Resource type - conversation, document, image, video, audio
            user: User scope dict, e.g. {"user_id": "123"}

        Returns:
            API response with task_id for status tracking
        """
        body: dict[str, Any] = {
            "resource_url": resource_url,
            "modality": modality,
        }
        if user:
            body["user"] = user

        resp = await self._client.post("/api/v3/memory/memorize", json=body)
        resp.raise_for_status()
        return resp.json()

    async def memorize_status(self, task_id: str) -> dict[str, Any]:
        """Check status of an async memorize task."""
        resp = await self._client.get(f"/api/v3/memory/memorize/status/{task_id}")
        resp.raise_for_status()
        return resp.json()

    async def retrieve(
        self,
        queries: list[dict[str, str]],
        where: dict[str, Any] | None = None,
        method: str = "rag",
    ) -> dict[str, Any]:
        """
        Retrieve relevant memories.

        Args:
            queries: List of message dicts, e.g. [{"role": "user", "content": "..."}]
            where: Scope filter, e.g. {"user_id": "123"}
            method: Retrieval method - "rag" or "llm"

        Returns:
            Retrieved categories, items, and resources
        """
        body: dict[str, Any] = {
            "queries": queries,
            "method": method,
        }
        if where:
            body["where"] = where

        resp = await self._client.post("/api/v3/memory/retrieve", json=body)
        resp.raise_for_status()
        return resp.json()

    async def categories(
        self,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List memory categories."""
        body: dict[str, Any] = {}
        if where:
            body["where"] = where

        resp = await self._client.post("/api/v3/memory/categories", json=body)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# ============================================================================
# MemuBackend - MemoryBackend Implementation
# ============================================================================


class MemuBackend(MemoryBackend):
    """memU implementation of MemoryBackend."""

    def __init__(self):
        self.client: Optional[AsyncMemU] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def name(self) -> str:
        return "memu"

    async def initialize(self) -> None:
        """Initialize the memU client."""
        api_key = getattr(settings, "MEMU_API_KEY", "")
        if not api_key:
            logger.warning("[memU] MEMU_API_KEY not configured")
            return

        async with await get_client_lock("memu"):
            if self.client is not None:
                return

            try:
                self.client = AsyncMemU(
                    base_url=getattr(settings, "MEMU_BASE_URL", ""),
                    api_key=api_key,
                )
                self._semaphore = await get_request_semaphore("memu", 64)
                logger.info(
                    f"[memU] Created async client for: {getattr(settings, 'MEMU_BASE_URL', '')}"
                )
            except Exception as e:
                logger.error(f"[memU] Failed to create client: {e}")

    def _do_retry(self, func) -> Any:
        """Execute with retry using shared utilities."""
        assert self._semaphore is not None, "memU semaphore not initialized"
        return with_retry(func, semaphore=self._semaphore, namespace="memU")

    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[list[str]] = None,
        existing_memory_id: Optional[str] = None,
    ) -> dict[str, Any]:
        del title, summary, tags, existing_memory_id

        conversation_data = [{"role": "user", "content": content}]
        if context:
            conversation_data.insert(0, {"role": "system", "content": f"Context: {context}"})

        if not self.client:
            raise RuntimeError("memU client not initialized")

        fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="memu_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(conversation_data, f, ensure_ascii=False)
            result = await self._do_retry(
                lambda: self.client.memorize(
                    resource_url=f"file://{temp_path}",
                    modality="conversation",
                    user={"user_id": user_id},
                )
            )
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

        task_id = result.get("task_id", "")
        logger.info(f"[memU] Retained memory for user {user_id}, task_id: {task_id}")
        return {
            "success": True,
            "message": "Memory stored successfully",
            "content_preview": content,
            "task_id": task_id,
        }

    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        queries = [{"role": "user", "content": query}]
        where: dict[str, Any] = {"user_id": user_id}

        if memory_types:
            valid_types = {"profile", "event", "knowledge", "behavior", "skill", "tool"}
            filtered = [t for t in memory_types if t in valid_types]
            if filtered:
                where["memory_type"] = filtered[0] if len(filtered) == 1 else filtered

        if not self.client:
            raise RuntimeError("memU client not initialized")
        result = await self._do_retry(
            lambda: self.client.retrieve(queries=queries, where=where, method="rag")
        )

        memories = []
        items = result.get("items", [])
        for item in items[:max_results]:
            memory_item = {
                "text": item.get("summary", item.get("content", "")),
                "type": item.get("memory_type", "unknown"),
            }
            if item.get("happened_at"):
                memory_item["happened_at"] = item["happened_at"]
            memories.append(memory_item)

        categories = result.get("categories", [])
        category_summaries = []
        for cat in categories:
            cat_summary = {"name": cat.get("name", ""), "description": cat.get("description", "")}
            if cat.get("summary"):
                cat_summary["summary"] = cat["summary"]
            category_summaries.append(cat_summary)

        logger.info(f"[memU] Recalled {len(memories)} memories for user {user_id}")

        response: dict[str, Any] = {
            "success": True,
            "query": query,
            "memories": memories,
        }
        if category_summaries:
            response["categories"] = category_summaries
        if len(items) > max_results:
            response["total_found"] = len(items)

        return response

    async def delete(
        self,
        user_id: str,
        memory_id: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Delete operation not supported by memU cloud API",
            "hint": "Use the self-hosted memU version for full CRUD operations.",
        }

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.close()
                self.client = None
                logger.info("[memU] Closed client")
            except Exception as e:
                logger.warning(f"[memU] Error closing client: {e}")
        clear_loop_locals("memu")


# ============================================================================
# Singleton (kept for backward compatibility)
# ============================================================================

_shared_backend: Optional[MemuBackend] = None


async def get_memu_client() -> Optional[AsyncMemU]:
    """Get the underlying AsyncMemU client (backward compat)."""
    global _shared_backend
    if _shared_backend is None:
        _shared_backend = MemuBackend()
    if _shared_backend.client is None:
        await _shared_backend.initialize()
    return _shared_backend.client


def get_memu_client_sync() -> Optional[AsyncMemU]:
    """Get the cached memU client synchronously (backward compat)."""
    return _shared_backend.client if _shared_backend else None


async def close_memu_client() -> None:
    """Close and cleanup the shared memU client (backward compat)."""
    global _shared_backend
    if _shared_backend is not None:
        await _shared_backend.close()
        _shared_backend = None

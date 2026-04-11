"""
Hindsight Memory Service - Cross-session Long-term Memory

Provides integration with Hindsight API for persistent, cross-session memory storage.
Uses a shared Hindsight server with bank_id isolation for multi-tenancy.

Documentation: https://docs.hindsight.ai
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Literal, Optional

from langchain.tools import ToolRuntime

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
# AsyncHindsight - Native Async Client
# ============================================================================


class AsyncHindsight:
    """
    Native async client for Hindsight API.

    Directly uses hindsight_client_api's async methods.
    """

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 180.0):
        import hindsight_client_api
        from hindsight_client_api.api import banks_api, memory_api

        config = hindsight_client_api.Configuration(host=base_url, access_token=api_key)
        self._api_client = hindsight_client_api.ApiClient(config)
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

        if api_key:
            self._api_client.set_default_header("Authorization", f"Bearer {api_key}")

        self._memory_api = memory_api.MemoryApi(self._api_client)
        self._banks_api = banks_api.BanksApi(self._api_client)

    async def retain(
        self,
        bank_id: str,
        content: str,
        timestamp: datetime | None = None,
        context: str | None = None,
        metadata: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """Store a single memory."""
        from hindsight_client_api.models import memory_item, retain_request
        from hindsight_client_api.models.timestamp import Timestamp

        ts = Timestamp(actual_instance=timestamp) if timestamp else None
        item = memory_item.MemoryItem(
            content=content,
            timestamp=ts,
            context=context,
            metadata=metadata,
            tags=tags,
        )
        request_obj = retain_request.RetainRequest(items=[item], async_=False)
        return await self._memory_api.retain_memories(
            bank_id, request_obj, _request_timeout=self._timeout
        )

    async def recall(
        self,
        bank_id: str,
        query: str,
        types: list[str] | None = None,
        max_tokens: int = 4096,
        budget: str = "mid",
        tags: list[str] | None = None,
        tags_match: Literal["any", "all", "any_strict", "all_strict"] = "any",
    ) -> Any:
        """Recall memories using semantic similarity."""
        from hindsight_client_api.models import recall_request

        request_obj = recall_request.RecallRequest(
            query=query,
            types=types,
            budget=budget,
            max_tokens=max_tokens,
            tags=tags,
            tags_match=tags_match,
        )
        return await self._memory_api.recall_memories(
            bank_id, request_obj, _request_timeout=self._timeout
        )

    async def reflect(
        self,
        bank_id: str,
        query: str,
        budget: str = "low",
        context: str | None = None,
        max_tokens: int | None = None,
        tags: list[str] | None = None,
        tags_match: Literal["any", "all", "any_strict", "all_strict"] = "any",
    ) -> Any:
        """Generate a contextual answer based on memories."""
        from hindsight_client_api.models import reflect_request

        request_obj = reflect_request.ReflectRequest(
            query=query,
            budget=budget,
            context=context,
            max_tokens=max_tokens,
            tags=tags,
            tags_match=tags_match,
        )
        return await self._memory_api.reflect(bank_id, request_obj, _request_timeout=self._timeout)

    async def list_memories(
        self,
        bank_id: str,
        type: str | None = None,
        search_query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        """List memory units with pagination."""
        return await self._memory_api.list_memories(
            bank_id=bank_id,
            type=type,
            q=search_query,
            limit=limit,
            offset=offset,
            _request_timeout=self._timeout,
        )

    async def create_bank(
        self,
        bank_id: str,
        name: str | None = None,
        mission: str | None = None,
    ) -> Any:
        """Create or update a memory bank."""
        import aiohttp

        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if mission is not None:
            body["mission"] = mission

        url = f"{self._base_url}/v1/default/banks/{bank_id}"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.put(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def delete_memory(self, bank_id: str, memory_id: str) -> Any:
        """Delete a specific memory by ID."""
        return await self._memory_api.delete_memory(
            bank_id=bank_id,
            memory_id=memory_id,
            _request_timeout=self._timeout,
        )

    async def close(self) -> None:
        """Close the API client."""
        if self._api_client:
            await self._api_client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ============================================================================
# HindsightBackend - MemoryBackend Implementation
# ============================================================================


class HindsightBackend(MemoryBackend):
    """Hindsight implementation of MemoryBackend."""

    def __init__(self):
        self.client: Optional[AsyncHindsight] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def name(self) -> str:
        return "hindsight"

    async def initialize(self) -> None:
        """Initialize the Hindsight client."""
        if not settings.HINDSIGHT_BASE_URL:
            logger.warning("[Hindsight] HINDSIGHT_BASE_URL not configured")
            return

        async with await get_client_lock("hindsight"):
            if self.client is not None:
                return

            try:
                self.client = AsyncHindsight(
                    base_url=settings.HINDSIGHT_BASE_URL,
                    api_key=settings.HINDSIGHT_API_KEY or None,
                    timeout=180.0,
                )
                try:
                    max_concurrent = int(settings.HINDSIGHT_MAX_CONCURRENT)
                except (AttributeError, TypeError, ValueError):
                    max_concurrent = int(os.getenv("HINDSIGHT_MAX_CONCURRENT", "64"))
                self._semaphore = await get_request_semaphore("hindsight", max_concurrent)
                logger.info(f"[Hindsight] Created async client for: {settings.HINDSIGHT_BASE_URL}")
            except Exception as e:
                logger.error(f"[Hindsight] Failed to create client: {e}")

    def _do_retry(self, func) -> Any:
        """Execute with retry using shared utilities."""
        assert self._semaphore is not None, "Hindsight semaphore not initialized"
        return with_retry(func, semaphore=self._semaphore, namespace="Hindsight")

    @staticmethod
    def _get_bank_id(user_id: str) -> str:
        """Generate bank ID for user isolation."""
        return f"user-{user_id}"

    async def _ensure_bank_exists(self, bank_id: str) -> bool:
        """Ensure a memory bank exists, creating it if necessary."""
        if not self.client:
            return False
        try:
            await self.client.create_bank(
                bank_id=bank_id,
                name="Default Memory Bank",
                mission="Store and retrieve user memories for cross-session persistence",
            )
            return True
        except Exception:
            return True

    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        existing_memory_id: Optional[str] = None,
    ) -> dict[str, Any]:
        del title, summary, existing_memory_id
        if not self.client:
            return {"success": False, "error": "Hindsight client not initialized"}
        bank_id = self._get_bank_id(user_id)
        await self._ensure_bank_exists(bank_id)
        await self._do_retry(
            lambda: self.client.retain(bank_id=bank_id, content=content, context=context)
        )
        logger.info(f"[Hindsight] Retained memory for user {user_id}: {content}...")
        return {
            "success": True,
            "message": "Memory stored successfully",
            "content_preview": content,
        }

    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        if not self.client:
            return {"success": False, "error": "Hindsight client not initialized"}
        bank_id = self._get_bank_id(user_id)
        results = await self._do_retry(
            lambda: self.client.recall(
                bank_id=bank_id,
                query=query,
                types=memory_types,
                max_tokens=4096,
                budget="mid",
            )
        )

        memories = []
        for r in results.results[:max_results]:
            memory_item = {
                "text": r.text,
                "type": getattr(r, "type", "unknown"),
            }
            if hasattr(r, "chunks") and r.chunks:
                memory_item["source"] = r.chunks[0].text if r.chunks[0].text else None
            memories.append(memory_item)

        logger.info(f"[Hindsight] Recalled {len(memories)} memories for user {user_id}")
        return {
            "success": True,
            "query": query,
            "memories": memories,
            "total_found": len(results.results),
        }

    async def delete(
        self,
        user_id: str,
        memory_id: str,
    ) -> dict[str, Any]:
        if not self.client:
            return {"success": False, "error": "Hindsight client not initialized"}
        bank_id = self._get_bank_id(user_id)
        if hasattr(self.client, "delete_memory"):
            await self._do_retry(
                lambda: self.client.delete_memory(bank_id=bank_id, memory_id=memory_id)
            )
            logger.info(f"[Hindsight] Deleted memory {memory_id} for user {user_id}")
            return {"success": True, "message": f"Memory {memory_id} deleted successfully"}
        return {"success": False, "error": "Delete operation not supported by the memory service"}

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.close()
                self.client = None
                logger.info("[Hindsight] Closed client")
            except Exception as e:
                logger.warning(f"[Hindsight] Error closing client: {e}")
        clear_loop_locals("hindsight")


# ============================================================================
# Singleton & Helpers (kept for backward compatibility)
# ============================================================================

_shared_backend: Optional[HindsightBackend] = None


async def get_hindsight_client() -> Optional[AsyncHindsight]:
    """Get the underlying AsyncHindsight client (backward compat)."""
    global _shared_backend
    if _shared_backend is None:
        _shared_backend = HindsightBackend()
    if _shared_backend.client is None:
        await _shared_backend.initialize()
    return _shared_backend.client


def get_hindsight_client_sync() -> Optional[AsyncHindsight]:
    """Get the cached Hindsight client synchronously (backward compat)."""
    return _shared_backend.client if _shared_backend else None


def get_user_id_from_runtime(runtime: Optional[ToolRuntime]) -> Optional[str]:
    """Extract user_id from ToolRuntime context."""
    if not runtime:
        return None
    try:
        if hasattr(runtime, "config"):
            config = runtime.config
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                context = configurable.get("context")
                if context and hasattr(context, "user_id"):
                    return context.user_id
    except Exception as e:
        logger.debug(f"[Hindsight] Failed to get user_id from runtime: {e}")
    return None


async def close_hindsight_client() -> None:
    """Close and cleanup the shared Hindsight client (backward compat)."""
    global _shared_backend
    if _shared_backend is not None:
        await _shared_backend.close()
        _shared_backend = None


close_all_hindsight_clients = close_hindsight_client

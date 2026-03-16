"""
Hindsight Memory Service - Cross-session Long-term Memory

Provides integration with Hindsight API for persistent, cross-session memory storage.
Uses a shared Hindsight server with bank_id isolation for multi-tenancy.

Optimized for multi-user high-concurrency scenarios with native async support.

Documentation: https://docs.hindsight.ai
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from typing import Annotated, Any, Callable, Literal, Optional

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Concurrency Configuration
# ============================================================================


def _get_max_concurrent() -> int:
    """Get max concurrent requests from settings (dynamic)."""
    try:
        return int(settings.HINDSIGHT_MAX_CONCURRENT)
    except (AttributeError, TypeError, ValueError):
        return int(os.getenv("HINDSIGHT_MAX_CONCURRENT", "64"))


# Event loop local storage for concurrency primitives
_loop_locals: dict[int, dict[str, Any]] = {}
_loop_locals_lock = threading.Lock()


def _get_loop_id() -> int:
    """Get unique identifier for current event loop."""
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


def _get_loop_local(name: str, factory: Callable[[], Any]) -> Any:
    """Get or create a loop-local resource."""
    loop_id = _get_loop_id()
    with _loop_locals_lock:
        if loop_id not in _loop_locals:
            _loop_locals[loop_id] = {}
        if name not in _loop_locals[loop_id]:
            _loop_locals[loop_id][name] = factory()
        return _loop_locals[loop_id][name]


def _get_request_semaphore() -> asyncio.Semaphore:
    """Get or create the request semaphore for current event loop."""
    return _get_loop_local(
        "semaphore", lambda: asyncio.Semaphore(_get_max_concurrent())
    )


def _get_client_lock() -> asyncio.Lock:
    """Get or create the client lock for current event loop."""
    return _get_loop_local("client_lock", lambda: asyncio.Lock())


# ============================================================================
# AsyncHindsight - Native Async Client
# ============================================================================


class AsyncHindsight:
    """
    Native async client for Hindsight API.

    Directly uses hindsight_client_api's async methods, bypassing the sync wrapper
    that causes issues with running event loops.
    """

    def __init__(
        self, base_url: str, api_key: str | None = None, timeout: float = 180.0
    ):
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
        return await self._memory_api.reflect(
            bank_id, request_obj, _request_timeout=self._timeout
        )

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

        async with aiohttp.ClientSession() as session:
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


# Global shared client
_shared_client: Optional[AsyncHindsight] = None


async def get_hindsight_client() -> Optional[AsyncHindsight]:
    """
    Get or create the shared AsyncHindsight client.

    Returns:
        AsyncHindsight instance or None if not configured
    """
    global _shared_client

    if _shared_client is not None:
        return _shared_client

    if not settings.HINDSIGHT_ENABLED:
        logger.debug("[Hindsight] Hindsight is disabled")
        return None

    if not settings.HINDSIGHT_BASE_URL:
        logger.warning("[Hindsight] HINDSIGHT_BASE_URL not configured")
        return None

    async with _get_client_lock():
        if _shared_client is not None:
            return _shared_client

        try:
            _shared_client = AsyncHindsight(
                base_url=settings.HINDSIGHT_BASE_URL,
                api_key=settings.HINDSIGHT_API_KEY or None,
                timeout=180.0,
            )
            logger.info(
                f"[Hindsight] Created async client for server: {settings.HINDSIGHT_BASE_URL}"
            )
            return _shared_client

        except Exception as e:
            logger.error(f"[Hindsight] Failed to create client: {e}")
            return None


def get_hindsight_client_sync() -> Optional[AsyncHindsight]:
    """Get the cached Hindsight client synchronously (for non-async contexts)."""
    return _shared_client


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


def _get_bank_id(user_id: str) -> str:
    """Generate bank ID for user isolation."""
    return f"user-{user_id}"


async def _ensure_bank_exists(client: AsyncHindsight, bank_id: str) -> bool:
    """Ensure a memory bank exists, creating it if necessary."""
    try:
        await client.create_bank(
            bank_id=bank_id,
            name="Default Memory Bank",
            mission="Store and retrieve user memories for cross-session persistence",
        )
        return True
    except Exception:
        return True


async def _with_retry(
    func: Callable[[], Any],
    *,
    max_retries: int = 3,
    retry_delay: float = 0.5,
) -> Any:
    """
    Execute an async operation with retry logic.

    Args:
        func: A callable that returns an awaitable (e.g., lambda: client.retain(...))
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (exponential backoff)
    """
    import random

    last_error: BaseException | None = None
    for attempt in range(max_retries):
        try:
            async with _get_request_semaphore():
                return await func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"[Hindsight] Retry {attempt + 1}/{max_retries} after error: {e}. Waiting {delay:.2f}s"
                )
                await asyncio.sleep(delay)

    if last_error is None:
        raise RuntimeError("Unexpected state: no error captured after retry loop")
    raise last_error


# ============================================================================
# Memory Tools
# ============================================================================


@tool
async def memory_retain(
    content: Annotated[
        str, "The memory content to store (facts, observations, experiences)"
    ],
    context: Annotated[
        Optional[str],
        "Optional context or category for this memory (e.g., 'user_preferences', 'project_info')",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Store a memory for cross-session persistence.

    Use this tool to remember important information that should persist across
    different conversation sessions. Examples: user preferences, important facts,
    project details, user background, etc.

    The memory will be intelligently processed and categorized by Hindsight.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps(
            {"success": False, "error": "User not authenticated"}, ensure_ascii=False
        )

    client = await get_hindsight_client()
    if not client:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        bank_id = _get_bank_id(user_id)

        # Ensure bank exists
        await _ensure_bank_exists(client, bank_id)

        # Retain the memory
        await _with_retry(
            lambda: client.retain(bank_id=bank_id, content=content, context=context)
        )

        logger.info(f"[Hindsight] Retained memory for user {user_id}: {content}...")

        return json.dumps(
            {
                "success": True,
                "message": "Memory stored successfully",
                "content_preview": content,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[Hindsight] Failed to retain memory: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
async def memory_recall(
    query: Annotated[str, "The search query to find relevant memories"],
    max_results: Annotated[
        int, "Maximum number of memories to return (default: 5)"
    ] = 5,
    memory_types: Annotated[
        Optional[list[str]],
        "Filter by memory types: ['world'] (facts), ['observation'] (events), ['experience'] (interactions), or None for all types",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Search and retrieve relevant memories from cross-session storage.

    Use this tool to recall previously stored information. The search is
    semantic and will find memories that are conceptually related to the query,
    even if they don't contain exact keyword matches.

    You can filter by memory types:
    - 'world': Factual knowledge about the world/user
    - 'observation': Specific events or observations
    - 'experience': Past interactions and experiences

    Returns a list of relevant memories with their content and types.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps(
            {"success": False, "error": "User not authenticated"}, ensure_ascii=False
        )

    client = await get_hindsight_client()
    if not client:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        bank_id = _get_bank_id(user_id)

        # Recall memories
        results = await _with_retry(
            lambda: client.recall(
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
            # Include chunks if available
            if hasattr(r, "chunks") and r.chunks:
                memory_item["source"] = r.chunks[0].text if r.chunks[0].text else None
            memories.append(memory_item)

        logger.info(f"[Hindsight] Recalled {len(memories)} memories for user {user_id}")

        return json.dumps(
            {
                "success": True,
                "query": query,
                "memories": memories,
                "total_found": len(results.results),
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[Hindsight] Failed to recall memories: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
async def memory_reflect(
    query: Annotated[str, "The question or topic to reflect on using stored memories"],
    context: Annotated[
        Optional[str],
        "Optional context to guide the reflection (e.g., 'preparing for a meeting')",
    ] = None,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Generate a response by reflecting on stored memories.

    Use this tool when you need to synthesize information from memories to
    answer a question or provide insights. This combines memory retrieval
    with intelligent response generation.

    Unlike recall (which returns raw memories), reflect generates a thoughtful
    response based on the user's memory history.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps(
            {"success": False, "error": "User not authenticated"}, ensure_ascii=False
        )

    client = await get_hindsight_client()
    if not client:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        bank_id = _get_bank_id(user_id)

        # Reflect on memories
        answer = await _with_retry(
            lambda: client.reflect(
                bank_id=bank_id, query=query, context=context, budget="mid"
            )
        )

        logger.info(f"[Hindsight] Reflected on query for user {user_id}: {query}...")

        return json.dumps(
            {
                "success": True,
                "response": answer.text,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[Hindsight] Failed to reflect: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
async def memory_list(
    memory_type: Annotated[
        Optional[str],
        "Filter by memory type: 'world' (facts), 'observation' (events), 'experience' (interactions), or None for all",
    ] = None,
    limit: Annotated[int, "Maximum number of memories to return (default: 20)"] = 20,
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    List stored memories with optional filtering.

    Use this tool to browse through stored memories. You can filter by
    memory type to see specific categories:
    - 'world': Factual knowledge about the world/user
    - 'observation': Specific events or observations
    - 'experience': Past interactions and experiences
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps(
            {"success": False, "error": "User not authenticated"}, ensure_ascii=False
        )

    client = await get_hindsight_client()
    if not client:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        bank_id = _get_bank_id(user_id)

        # List memories
        result = await _with_retry(
            lambda: client.list_memories(bank_id=bank_id, type=memory_type, limit=limit)
        )

        memories = []
        # result is ListMemoryUnitsResponse with items attribute
        items = result.items if hasattr(result, "items") else result
        for m in items:
            # Each item is a dict with id, text, type, etc.
            if isinstance(m, dict):
                memory_item = {
                    "id": m.get("id", str(hash(str(m)))),
                    "text": m.get("text", str(m)),
                    "type": m.get("type", "unknown"),
                }
            else:
                memory_item = {
                    "id": getattr(m, "id", str(hash(str(m)))),
                    "text": getattr(m, "text", str(m)),
                    "type": getattr(m, "type", "unknown"),
                }
            memories.append(memory_item)

        logger.info(f"[Hindsight] Listed {len(memories)} memories for user {user_id}")

        return json.dumps(
            {
                "success": True,
                "memories": memories,
                "count": len(memories),
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[Hindsight] Failed to list memories: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
async def memory_delete(
    memory_id: Annotated[str, "The ID of the memory to delete"],
    runtime: ToolRuntime = None,  # type: ignore[assignment]
) -> str:
    """
    Delete a specific memory by ID.

    Use this tool when a user wants to remove a specific memory.
    Get the memory ID from the memory_list tool output.
    """
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return json.dumps(
            {"success": False, "error": "User not authenticated"}, ensure_ascii=False
        )

    client = await get_hindsight_client()
    if not client:
        return json.dumps(
            {"success": False, "error": "Memory service not available"},
            ensure_ascii=False,
        )

    try:
        bank_id = _get_bank_id(user_id)

        # Delete memory
        if hasattr(client, "delete_memory"):
            await _with_retry(
                lambda: client.delete_memory(bank_id=bank_id, memory_id=memory_id)
            )
            logger.info(f"[Hindsight] Deleted memory {memory_id} for user {user_id}")
        else:
            # Delete operation not supported by current client version
            # The Hindsight client may not expose memory deletion at the individual level
            return json.dumps(
                {
                    "success": False,
                    "error": "Delete operation not supported by the memory service",
                    "hint": "Individual memory deletion may not be available. Consider using bank-level operations.",
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "success": True,
                "message": f"Memory {memory_id} deleted successfully",
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[Hindsight] Failed to delete memory: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============================================================================
# Tool Factory Functions
# ============================================================================


def get_memory_retain_tool() -> BaseTool:
    """Get memory_retain tool instance."""
    return memory_retain


def get_memory_recall_tool() -> BaseTool:
    """Get memory_recall tool instance."""
    return memory_recall


def get_memory_reflect_tool() -> BaseTool:
    """Get memory_reflect tool instance."""
    return memory_reflect


def get_memory_list_tool() -> BaseTool:
    """Get memory_list tool instance."""
    return memory_list


def get_memory_delete_tool() -> BaseTool:
    """Get memory_delete tool instance."""
    return memory_delete


def get_all_memory_tools() -> list[BaseTool]:
    """Get all memory tools."""
    return [
        memory_retain,
        memory_recall,
        # memory_reflect,
        # memory_list,
        memory_delete,
    ]


# ============================================================================
# Auto-Retention (Background Task)
# ============================================================================


async def auto_retain_conversation(
    user_id: str,
    conversation_summary: str,
    context: Optional[str] = None,
    bank_name: Optional[str] = None,
) -> None:
    """
    Automatically store conversation summary as memory (fire-and-forget).

    This function is designed to be called at the end of conversations
    to automatically store important information. It runs asynchronously
    and does not block the main response.

    Args:
        user_id: User identifier for multi-tenant isolation
        conversation_summary: Summary of important information from the conversation
        context: Optional context/category for this memory
        bank_name: Optional bank name for organizing memories
    """
    if not user_id or not conversation_summary:
        return

    try:
        client = await get_hindsight_client()
        if not client:
            logger.debug("[Hindsight] Client not available, skipping auto-retain")
            return

        bank_id = _get_bank_id(user_id)

        # Ensure bank exists
        await _ensure_bank_exists(client, bank_id)

        # Retain the memory
        await _with_retry(
            lambda: client.retain(
                bank_id=bank_id,
                content=conversation_summary,
                context=context or "auto_retained",
            )
        )

        logger.info(
            f"[Hindsight] Auto-retained conversation memory for user {user_id}: "
            f"{conversation_summary}..."
        )

    except Exception as e:
        # Log warning but don't raise - this is a background task
        logger.warning(f"[Hindsight] Auto-retain failed (non-critical): {e}")


def schedule_auto_retain(
    user_id: str,
    conversation_summary: str,
    context: Optional[str] = None,
    bank_name: Optional[str] = None,
) -> None:
    """
    Schedule auto-retention as a background task (fire-and-forget).

    Use this to store conversation memories without blocking the response.
    The task runs in the background and any errors are logged but not raised.

    Args:
        user_id: User identifier for multi-tenant isolation
        conversation_summary: Summary of important information from the conversation
        context: Optional context/category for this memory
        bank_name: Optional bank name for organizing memories
    """
    if not settings.HINDSIGHT_ENABLED:
        return

    if not user_id or not conversation_summary:
        return

    # Try to get the running event loop; if none exists, we can't schedule
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop - this shouldn't happen in our async agents
        logger.debug("[Hindsight] No running event loop, skipping auto-retain")
        return

    # Create background task using the running loop
    task = loop.create_task(
        auto_retain_conversation(
            user_id=user_id,
            conversation_summary=conversation_summary,
            context=context,
            bank_name=bank_name,
        )
    )
    # Add callback to handle any exceptions (prevents "Task exception was never retrieved")
    task.add_done_callback(_handle_background_task_error)


def _handle_background_task_error(task: asyncio.Task) -> None:
    """Handle any exceptions from background tasks."""
    try:
        exc = task.exception()
        if exc:
            logger.warning(f"[Hindsight] Background auto-retain task failed: {exc}")
    except asyncio.CancelledError:
        pass  # Task was cancelled, that's fine


# ============================================================================
# Client Management
# ============================================================================


async def close_hindsight_client() -> None:
    """Close and cleanup the shared Hindsight client."""
    global _shared_client
    if _shared_client is not None:
        try:
            if hasattr(_shared_client, "close"):
                await _shared_client.close()
            _shared_client = None
            logger.info("[Hindsight] Closed shared client")
        except Exception as e:
            logger.warning(f"[Hindsight] Error closing client: {e}")

    # Clear loop-local storage
    with _loop_locals_lock:
        _loop_locals.clear()
    logger.info("[Hindsight] Cleared loop-local resources")


def get_concurrency_stats() -> dict[str, Any]:
    """
    Get current concurrency statistics.

    Returns:
        Dictionary with concurrency stats for monitoring
    """
    loop_id = _get_loop_id()
    max_concurrent = _get_max_concurrent()
    sem_value = max_concurrent

    with _loop_locals_lock:
        if loop_id in _loop_locals and "semaphore" in _loop_locals[loop_id]:
            sem = _loop_locals[loop_id]["semaphore"]
            sem_value = sem._value  # type: ignore[attr-defined]

    return {
        "max_concurrent_requests": max_concurrent,
        "semaphore_available": sem_value,
        "client_initialized": _shared_client is not None,
        "active_event_loops": len(_loop_locals),
    }


# Alias for compatibility
close_all_hindsight_clients = close_hindsight_client

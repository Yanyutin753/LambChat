"""Shared httpx connection pools for cached LLM model instances.

模型缓存按全参数组合键控（temperature/thinking/profile…），同一 provider 的
多个参数组合会各占一个槽位并各自重建 httpx 连接池。只有连接相关字段
（api_key/api_base）决定底层 HTTP 连接，因此 OpenAI 协议模型在连接字段相同时
共享一个池化 httpx.AsyncClient；参数差异留在轻量的模型实例上（二级缓存）。
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from src.infra.logging import get_logger

logger = get_logger(__name__)

_close_tasks: set[asyncio.Future[None]] = set()


def _safe_close_client(model_instance: BaseChatModel) -> None:
    """Safely close HTTP client with error logging.

    Pooled httpx clients (shared across model instances by connection key)
    are never closed here — the pool owns their lifecycle.
    """
    try:
        _client = getattr(model_instance, "async_client", None) or getattr(
            model_instance, "client", None
        )
        if _client and hasattr(_client, "aclose"):
            underlying = getattr(_client, "_client", None) or _client
            if id(underlying) in _pooled_client_ids():
                return

            def _on_close_done(t: asyncio.Future[None]) -> None:
                _close_tasks.discard(t)
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.debug(f"Failed to close LLM client connections: {exc}")

            task = asyncio.ensure_future(_client.aclose())
            _close_tasks.add(task)
            task.add_done_callback(_on_close_done)
    except Exception as e:
        logger.debug(f"Failed to close LLM client connections: {e}")


# ── Shared httpx connection pools ──
# The model cache is keyed by the full parameter set (temperature, thinking,
# profile…), so one provider with several parameter combinations occupies
# several slots — each with its own httpx pool rebuilt on LRU churn. Only
# connection-relevant fields (api_key/api_base) determine the underlying HTTP
# connection, so OpenAI-protocol models with identical connection fields share
# one pooled httpx.AsyncClient; parameter differences stay on the model
# instances (二級缓存), which remain cheap to rebuild.
_httpx_pool_cache: "OrderedDict[tuple[Optional[str], Optional[str]], httpx.AsyncClient]" = (
    OrderedDict()
)
_httpx_pool_refs: dict[tuple[Optional[str], Optional[str]], int] = {}
# id(cached model instance) -> pool key it acquired a reference for
_model_pool_keys: dict[int, tuple[Optional[str], Optional[str]]] = {}


def _pool_key(
    api_key: Optional[str], api_base: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Connection-relevant cache key: only fields that determine the HTTP
    connection (credentials + endpoint) participate — per-request parameters
    like temperature/thinking/profile do not."""
    return (api_key, api_base)


def _pooled_client_ids() -> set[int]:
    return {id(client) for client in _httpx_pool_cache.values()}


def _acquire_pooled_http_async_client(
    api_key: Optional[str], api_base: Optional[str]
) -> httpx.AsyncClient:
    """Get (or create) the shared async httpx client for this connection key.

    Mirrors the OpenAI SDK's default client: 600s total timeout (per-request
    timeouts are applied by the SDK on top of it) with generous pool limits.
    Refcounted against cached model instances; released on their eviction.
    """
    key = _pool_key(api_key, api_base)
    client = _httpx_pool_cache.get(key)
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=600.0, connect=5.0),
            limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        )
        _httpx_pool_cache[key] = client
    else:
        _httpx_pool_cache.move_to_end(key)
    _httpx_pool_refs[key] = _httpx_pool_refs.get(key, 0) + 1
    return client


def _release_pool_client(
    key: tuple[Optional[str], Optional[str]], model_instance: Optional[Any] = None
) -> None:
    """Drop one reference; close the pooled client when the last one is gone."""
    if model_instance is not None:
        _model_pool_keys.pop(id(model_instance), None)
    refs = _httpx_pool_refs.get(key)
    if refs is None:
        return
    if refs > 1:
        _httpx_pool_refs[key] = refs - 1
        return
    _httpx_pool_refs.pop(key, None)
    client = _httpx_pool_cache.pop(key, None)
    if client is not None:
        try:
            task = asyncio.ensure_future(client.aclose())
            _close_tasks.add(task)
            task.add_done_callback(lambda t: _close_tasks.discard(t))
        except Exception as e:
            logger.debug(f"Failed to close pooled LLM httpx client: {e}")


def _evict_model_instance(model_instance: BaseChatModel) -> None:
    """Eviction bookkeeping shared by LRU eviction and explicit cache clears."""
    pool_key = _model_pool_keys.pop(id(model_instance), None)
    if pool_key is not None:
        _release_pool_client(pool_key)
    _safe_close_client(model_instance)


def release_all_pooled_clients() -> None:
    """Drop every pool reference (full shutdown); closes shared clients."""
    for key in list(_httpx_pool_cache):
        _release_pool_client(key)

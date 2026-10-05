"""Shared httpx connection pools for cached LLM model instances.

模型缓存按全参数组合键控（temperature/thinking/profile…），同一 provider 的
多个参数组合会各占一个槽位并各自重建 httpx 连接池。只有连接相关字段
（api_key/api_base）决定底层 HTTP 连接，因此 OpenAI 协议模型在连接字段相同时
共享一个池化 httpx.AsyncClient；参数差异留在轻量的模型实例上（二级缓存）。

关闭语义：引用计数只挂在缓存槽位上，而一次 agent run 会在缓存外长期持有
被逐出的模型实例（deep agent 单节点内多次工具回环复用同一实例）。因此引用
归零时不立即 aclose——先进入「退役宽限期」，宽限期内重新 acquire 会复活同一
客户端；期满仍无新引用才真正关闭。只有停机 flush
（release_all_pooled_clients）会取消全部宽限并立即关闭，保证重启/滚动更新
路径行为不变。
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from src.infra.logging import get_logger

logger = get_logger(__name__)

_close_tasks: set[asyncio.Future[None]] = set()


def _close_grace_seconds() -> float:
    """退役客户端真正关闭前的宽限期（秒）。

    覆盖「配置变更触发清缓存时恰有长 run 在途」的窗口；期间连接只是闲置，
    不会产生额外开销。
    """
    from src.kernel.config import settings

    return float(getattr(settings, "LLM_POOL_CLOSE_GRACE_SECONDS", 1800.0))


@dataclass
class _RetiredClient:
    """已无缓存引用、等待宽限期结束后关闭的客户端。"""

    client: Any
    timer: Optional[asyncio.TimerHandle] = None


def _spawn_close_task(target: Any) -> None:
    """异步执行 target.aclose()，任务纳入 _close_tasks 供停机 drain。"""

    def _on_close_done(t: asyncio.Future[None]) -> None:
        _close_tasks.discard(t)
        if not t.cancelled():
            exc = t.exception()
            if exc:
                logger.debug(f"Failed to close LLM client connections: {exc}")

    try:
        task = asyncio.ensure_future(target.aclose())
        _close_tasks.add(task)
        task.add_done_callback(_on_close_done)
    except Exception as e:
        logger.debug(f"Failed to close LLM client connections: {e}")


def _schedule_graceful_close(registry: dict[Any, _RetiredClient], key: Any, target: Any) -> None:
    """把 target 放入退役注册表，宽限期后仍无人认领才关闭。"""
    existing = registry.get(key)
    if existing is not None and existing.timer is not None:
        existing.timer.cancel()

    def _fire() -> None:
        registry.pop(key, None)
        _spawn_close_task(target)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # 无事件循环（不应发生）：立即关闭兜底
        _spawn_close_task(target)
        return
    grace = _close_grace_seconds()
    timer = loop.call_later(grace, _fire)
    registry[key] = _RetiredClient(client=target, timer=timer)


def _safe_close_client(model_instance: BaseChatModel) -> None:
    """Safely close HTTP client with error logging.

    Pooled httpx clients (shared across model instances by connection key)
    are never closed here — the pool owns their lifecycle. 非池化的 SDK
    wrapper（anthropic/google 协议等）同样不立即关闭：在途 run 可能仍在
    使用该实例，走与池子一致的退役宽限。
    """
    try:
        _client = getattr(model_instance, "async_client", None) or getattr(
            model_instance, "client", None
        )
        if _client and hasattr(_client, "aclose"):
            underlying = getattr(_client, "_client", None) or _client
            if id(underlying) in _pooled_client_ids():
                return
            _schedule_graceful_close(_retired_sdk_clients, id(_client), _client)
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
# 引用归零但仍在宽限期的池化客户端（可复活）
_retired_pools: dict[tuple[Optional[str], Optional[str]], _RetiredClient] = {}
# 被逐出模型实例的非池化 SDK wrapper，同样延迟关闭；以 id(_client) 为键
# （注册表持强引用，键不会被复用）
_retired_sdk_clients: dict[int, _RetiredClient] = {}


def _pool_key(
    api_key: Optional[str], api_base: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Connection-relevant cache key: only fields that determine the HTTP
    connection (credentials + endpoint) participate — per-request parameters
    like temperature/thinking/profile do not."""
    return (api_key, api_base)


def _pooled_client_ids() -> set[int]:
    """活跃与退役中的池化客户端 id 集合——这些的生命周期归池子管。"""
    ids = {id(client) for client in _httpx_pool_cache.values()}
    ids.update(id(entry.client) for entry in _retired_pools.values())
    return ids


def _acquire_pooled_http_async_client(
    api_key: Optional[str], api_base: Optional[str]
) -> httpx.AsyncClient:
    """Get (or create) the shared async httpx client for this connection key.

    Mirrors the OpenAI SDK's default client: 600s total timeout (per-request
    timeouts are applied by the SDK on top of it) with generous pool limits.
    Refcounted against cached model instances; released on their eviction.
    宽限期内退役的客户端在此被复活复用（同一物理连接池）。
    """
    key = _pool_key(api_key, api_base)
    client = _httpx_pool_cache.get(key)
    if client is None:
        retired = _retired_pools.pop(key, None)
        if retired is not None:
            if retired.timer is not None:
                retired.timer.cancel()
            client = retired.client
            _httpx_pool_cache[key] = client
        else:
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
    """Drop one reference; retire the pooled client when the last one is gone.

    归零不立即关闭：在途 run 可能仍持有被逐出实例（缓存外），退役进入
    宽限期，期间可被 _acquire_pooled_http_async_client 复活。
    """
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
        _schedule_graceful_close(_retired_pools, key, client)


def _evict_model_instance(model_instance: BaseChatModel) -> None:
    """Eviction bookkeeping shared by LRU eviction and explicit cache clears."""
    pool_key = _model_pool_keys.pop(id(model_instance), None)
    if pool_key is not None:
        _release_pool_client(pool_key)
    _safe_close_client(model_instance)


def release_all_pooled_clients() -> None:
    """Full shutdown: cancel grace periods and close every client now.

    停机/重启专用（close_cached_models 末尾调用）：取消全部退役计时器，
    活跃池、退役池与待关 SDK wrapper 一律立即异步关闭，随后由
    drain_close_tasks 收尾——与旧语义一致，保证优雅停机不被宽限期拖慢。
    """
    pending: list[Any] = []

    for entry in _retired_pools.values():
        if entry.timer is not None:
            entry.timer.cancel()
        pending.append(entry.client)
    _retired_pools.clear()

    _httpx_pool_refs.clear()
    pending.extend(_httpx_pool_cache.values())
    _httpx_pool_cache.clear()

    for entry in _retired_sdk_clients.values():
        if entry.timer is not None:
            entry.timer.cancel()
        pending.append(entry.client)
    _retired_sdk_clients.clear()

    for target in pending:
        _spawn_close_task(target)

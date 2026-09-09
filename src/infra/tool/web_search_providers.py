"""Web search providers: multi-provider clients with multi-key rotation.

供应商层约定：
- 归一化输出统一为 ``{"success", "query", "provider", "results", "images", "answer"?}``；
- key 池按 round-robin 轮询，429/432/401 等错误按语义冷却后跳过（比开源项目
  的纯轮询更进一步：单 key 额度耗尽或限速时自动换下一个 key）；
- auto 模式按 tavily → brave → searxng 顺序回退，钉死某供应商时不回退。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# 归一化 time_range（Tavily/SearXNG 原生支持，Brave 映射为 freshness）
_TIME_RANGE_ALIASES = {"d": "day", "w": "week", "m": "month", "y": "year"}
_VALID_TIME_RANGES = {"day", "week", "month", "year"}
# Brave freshness: pd=过去一天 pw=过去一周 pm=过去一月 py=过去一年
_BRAVE_FRESHNESS = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}

# key 冷却时长（秒）：429 限速 / 432 或 402 额度耗尽 / 401、403 无效 key / 其他错误
COOLDOWN_RATE_LIMIT_SECONDS = 60.0
COOLDOWN_QUOTA_EXHAUSTED_SECONDS = 6 * 3600.0
COOLDOWN_INVALID_KEY_SECONDS = 12 * 3600.0
COOLDOWN_DEFAULT_SECONDS = 30.0
RETRY_AFTER_MAX_SECONDS = 600.0  # 防异常 Retry-After 把 key 长时间挂起

_MAX_IMAGES = 10

_PROVIDER_KEY_SETTINGS = {"tavily": "TAVILY_API_KEYS", "brave": "BRAVE_API_KEYS"}
_PROVIDER_ORDER = ("tavily", "brave", "searxng")


def normalize_time_range(value: str | None) -> str | None:
    """归一化 time_range 入参（day/week/month/year，支持首字母缩写），非法值返回 None。"""
    if not value:
        return None
    normalized = str(value).strip().lower()
    normalized = _TIME_RANGE_ALIASES.get(normalized, normalized)
    return normalized if normalized in _VALID_TIME_RANGES else None


class ApiKeyPool:
    """round-robin key 池：跳过冷却中的 key，全部不可用时返回 None。"""

    def __init__(
        self,
        keys: list[str] | tuple[str, ...] | str,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        if isinstance(keys, str):
            keys = keys.split(",")
        self._keys = [k.strip() for k in keys if k and k.strip()]
        self._cursor = 0
        self._cooldown_until: dict[int, float] = {}
        self._now_fn = now_fn or time.monotonic

    def __len__(self) -> int:
        return len(self._keys)

    def next_key(self) -> tuple[int, str] | None:
        total = len(self._keys)
        if total == 0:
            return None
        now = self._now_fn()
        for offset in range(total):
            index = (self._cursor + offset) % total
            until = self._cooldown_until.get(index)
            if until is not None and until > now:
                continue
            self._cursor = (index + 1) % total
            return index, self._keys[index]
        return None

    def mark_cooldown(self, index: int, seconds: float) -> None:
        self._cooldown_until[index] = self._now_fn() + max(0.0, float(seconds))


class ProviderRequestError(Exception):
    """供应商 HTTP 请求失败（带状态码，供冷却决策）。"""

    def __init__(
        self,
        status_code: int,
        message: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    retry_after: float | None = None
    headers = getattr(response, "headers", None)
    raw_retry_after = headers.get("retry-after") if headers else None
    if raw_retry_after:
        try:
            retry_after = min(float(raw_retry_after), RETRY_AFTER_MAX_SECONDS)
        except ValueError:
            retry_after = None
    detail = ""
    try:
        body = response.json()
        detail = str(body.get("detail", "")) if isinstance(body, dict) else ""
    except Exception:
        pass
    raise ProviderRequestError(response.status_code, detail, retry_after)


def _result(
    *,
    query: str,
    provider: str,
    results: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    answer: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "query": query,
        "provider": provider,
        "results": results,
        "images": images or [],
    }
    if answer:
        payload["answer"] = answer
    return payload


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


async def tavily_search(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    max_results: int,
    time_range: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "query": query,
        "max_results": max(1, min(int(max_results), 10)),
        "search_depth": "basic",
        "include_answer": True,
        "include_images": True,
        "include_image_descriptions": True,
        "include_favicon": True,
    }
    if time_range:
        body["time_range"] = time_range

    response = await client.post(
        TAVILY_SEARCH_URL,
        json=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    _raise_for_status(response)
    data = response.json()

    results = [
        {
            "title": _clean(item.get("title")) or "",
            "url": _clean(item.get("url")) or "",
            "snippet": _clean(item.get("content")) or "",
            "score": _normalize_score(item.get("score")),
            "favicon_url": _clean(item.get("favicon")),
            "published_date": _clean(item.get("published_date")),
        }
        for item in (data.get("results") or [])
        if isinstance(item, dict) and _clean(item.get("url"))
    ]
    images: list[dict[str, Any]] = []
    for image in (data.get("images") or [])[:_MAX_IMAGES]:
        if isinstance(image, str) and image.strip():
            images.append({"url": image.strip()})
        elif isinstance(image, dict) and _clean(image.get("url")):
            images.append(
                {"url": _clean(image.get("url")), "description": _clean(image.get("description"))}
            )

    return _result(
        query=query,
        provider="tavily",
        results=results,
        images=images,
        answer=_clean(data.get("answer")),
    )


# ---------------------------------------------------------------------------
# Brave Search
# ---------------------------------------------------------------------------


async def brave_search(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    max_results: int,
    time_range: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": query,
        "count": max(1, min(int(max_results), 20)),
    }
    if time_range:
        params["freshness"] = _BRAVE_FRESHNESS[time_range]

    response = await client.get(
        BRAVE_SEARCH_URL,
        params=params,
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    _raise_for_status(response)
    data = response.json()

    web = data.get("web") or {}
    results = [
        {
            "title": _clean(item.get("title")) or "",
            "url": _clean(item.get("url")) or "",
            "snippet": _clean(item.get("description")) or "",
            "score": None,
            "favicon_url": None,
            "published_date": None,
        }
        for item in (web.get("results") or [])
        if isinstance(item, dict) and _clean(item.get("url"))
    ]

    return _result(query=query, provider="brave", results=results)


# ---------------------------------------------------------------------------
# SearXNG
# ---------------------------------------------------------------------------


async def searxng_search(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    query: str,
    max_results: int,
    time_range: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "safesearch": 1,
    }
    if time_range:
        params["time_range"] = time_range
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    response = await client.get(f"{base_url.rstrip('/')}/search", params=params, headers=headers)
    _raise_for_status(response)
    data = response.json()

    results = [
        {
            "title": _clean(item.get("title")) or "",
            "url": _clean(item.get("url")) or "",
            "snippet": _clean(item.get("content")) or "",
            "score": _normalize_score(item.get("score")),
            "favicon_url": None,
            "published_date": _clean(item.get("published_date")),
        }
        for item in (data.get("results") or [])
        if isinstance(item, dict)
        and (_clean(item.get("url")) or "").startswith(("http://", "https://"))
    ][: max(1, int(max_results))]

    answers = data.get("answers") or []
    answer = _clean(answers[0]) if answers and isinstance(answers[0], str) else None

    return _result(query=query, provider="searxng", results=results, answer=answer)


PROVIDER_FUNCS: dict[str, Callable[..., Any]] = {
    "tavily": tavily_search,
    "brave": brave_search,
    "searxng": searxng_search,
}


# ---------------------------------------------------------------------------
# httpx client 复用
# ---------------------------------------------------------------------------

_web_search_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _web_search_client
    if _web_search_client is None or getattr(_web_search_client, "is_closed", False):
        _web_search_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=4),
            follow_redirects=True,
        )
    return _web_search_client


async def close_web_search_client() -> None:
    """关闭复用的 httpx client（应用关闭时调用）。"""
    global _web_search_client
    if _web_search_client is not None and not getattr(_web_search_client, "is_closed", False):
        try:
            await _web_search_client.aclose()
        except Exception as e:
            logger.warning("关闭 web search httpx client 失败: %s", e)
    _web_search_client = None


# ---------------------------------------------------------------------------
# 编排：key 池 + 供应商链
# ---------------------------------------------------------------------------

# provider -> (配置时的原始 keys 串, ApiKeyPool)；配置变化时重建池
_pools: dict[str, tuple[str, ApiKeyPool]] = {}


def _get_pool(provider: str) -> ApiKeyPool | None:
    setting_key = _PROVIDER_KEY_SETTINGS[provider]
    raw = str(getattr(settings, setting_key, "") or "")
    entry = _pools.get(provider)
    if entry is not None and entry[0] == raw:
        return entry[1] if len(entry[1]) else None
    pool = ApiKeyPool(raw)
    _pools[provider] = (raw, pool)
    return pool if len(pool) else None


def _provider_available(provider: str) -> bool:
    if provider in _PROVIDER_KEY_SETTINGS:
        return _get_pool(provider) is not None
    if provider == "searxng":
        return bool(str(getattr(settings, "SEARXNG_BASE_URL", "") or "").strip())
    return False


def resolve_provider_chain() -> list[str]:
    """auto = 按 tavily → brave → searxng 顺序取已配置项；钉死供应商时只返回它。"""
    choice = str(getattr(settings, "WEB_SEARCH_PROVIDER", "auto") or "auto").strip().lower()
    if choice in PROVIDER_FUNCS:
        return [choice]
    return [provider for provider in _PROVIDER_ORDER if _provider_available(provider)]


def _cooldown_seconds(error: ProviderRequestError) -> float:
    if error.status_code == 429:
        return error.retry_after or COOLDOWN_RATE_LIMIT_SECONDS
    if error.status_code in (432, 402):
        return COOLDOWN_QUOTA_EXHAUSTED_SECONDS
    if error.status_code in (401, 403):
        return COOLDOWN_INVALID_KEY_SECONDS
    return COOLDOWN_DEFAULT_SECONDS


async def _search_with_pool(
    provider: str, query: str, max_results: int, time_range: str | None
) -> dict[str, Any]:
    errors: list[str] = []
    pool = _get_pool(provider)
    if pool is None:
        return {"success": False, "error": f"web_search_{provider}_not_configured"}

    func = PROVIDER_FUNCS[provider]
    client = _get_client()
    while True:
        nxt = pool.next_key()
        if nxt is None:
            errors.append(f"{provider}: all keys unavailable")
            break
        index, key = nxt
        try:
            return await func(client, key, query, max_results, time_range)
        except ProviderRequestError as e:
            cooldown = _cooldown_seconds(e)
            pool.mark_cooldown(index, cooldown)
            logger.warning(
                "[WebSearch] %s key#%d failed (HTTP %s), cooling %.0fs: %s",
                provider,
                index + 1,
                e.status_code,
                cooldown,
                e,
            )
            errors.append(f"{provider} key#{index + 1}: HTTP {e.status_code}")
        except Exception as e:
            pool.mark_cooldown(index, COOLDOWN_DEFAULT_SECONDS)
            logger.warning(
                "[WebSearch] %s key#%d error, cooling %.0fs: %s",
                provider,
                index + 1,
                COOLDOWN_DEFAULT_SECONDS,
                e,
            )
            errors.append(f"{provider} key#{index + 1}: {e}")
    return {"success": False, "error": "web_search_provider_failed", "details": errors}


async def execute_web_search(
    query: str, max_results: int, time_range: str | None = None
) -> dict[str, Any]:
    """执行网页搜索：供应商内多 key 轮询，auto 模式下跨供应商回退。永不抛异常。"""
    chain = resolve_provider_chain()
    if not chain:
        return {"success": False, "error": "web_search_no_provider_configured"}

    errors: list[str] = []
    for provider in chain:
        if provider == "searxng":
            base_url = str(getattr(settings, "SEARXNG_BASE_URL", "") or "").strip()
            if not base_url:
                errors.append("searxng: not configured")
                continue
            try:
                return await searxng_search(
                    _get_client(),
                    base_url,
                    str(getattr(settings, "SEARXNG_API_KEY", "") or ""),
                    query,
                    max_results,
                    time_range,
                )
            except Exception as e:
                logger.warning("[WebSearch] searxng failed: %s", e)
                errors.append(f"searxng: {e}")
                continue

        outcome = await _search_with_pool(provider, query, max_results, time_range)
        if outcome.get("success"):
            return outcome
        errors.extend(outcome.get("details") or [str(outcome.get("error"))])

    return {"success": False, "error": "web_search_all_providers_failed", "details": errors}


def _reset_web_search_state() -> None:
    """清空模块级状态（测试用）。"""
    global _web_search_client
    _pools.clear()
    _web_search_client = None

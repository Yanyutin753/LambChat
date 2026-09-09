"""Web fetch providers: SSRF-guarded direct fetch + Jina Reader fallback.

供应商层约定（对齐 web_search_providers 的结构）：
- 归一化输出统一为 ``{"success", "url", "final_url", "provider", "title",
  "content", "content_chars", "truncated", "content_type"}``；
- ``direct``：本机 httpx 抓取（浏览器 UA + ``Accept: text/markdown``），HTML 经
  trafilatura 提取正文并转 Markdown（开源基准长期第一），纯文本原样透传；
- ``jina``：r.jina.ai URL 前缀协议，返回 LLM 友好 Markdown——SPA/JS 渲染页
  direct 拿到空正文时的兜底；多 key 复用 ApiKeyPool 轮询 + 错误冷却；
- ``auto``（默认）：direct → jina（配置了 key 才启用）；钉死供应商不回退。

SSRF 防护（安全底线，与 sandbox 确认门同级敏感）：
- 仅 http/https scheme；DNS 解析后逐 IP 校验，拒绝环回/内网/链路本地/
  保留/组播地址（域名解析到内网同样拒绝，覆盖 DNS 重绑定面）；
- 重定向不自动跟随，逐跳校验（跳向内网即断），上限 5 跳；
- 体积上限（下载增量读取截断）+ 读超时。
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.web_search_providers import (
    COOLDOWN_RATE_LIMIT_SECONDS,
    ApiKeyPool,
    ProviderRequestError,
    _raise_for_status,
)
from src.kernel.config import settings

logger = get_logger(__name__)

JINA_READER_PREFIX = "https://r.jina.ai/"

# 直连抓取限制：读超时 30s；下载体积上限 5MB（Markdown 提取前的原始 body 上限，
# 超出即截断读取——超大页面提取出的正文也必然远小于该值）
DIRECT_FETCH_TIMEOUT_S = 30.0
DIRECT_MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5

# Jina Reader 免 key 20 RPM；带 key 200 RPM。冷却对齐 web_search 的限速语义
_COOLDOWN_429_S = COOLDOWN_RATE_LIMIT_SECONDS

# 浏览器形态 UA：不少站点对非浏览器 UA 直接 403；Accept 带 text/markdown
# 对齐 Claude Code WebFetch 的做法（docs 站点会直接回 Markdown）
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_FETCH_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 正文提取结果为空时的判定下限（字符）：trafilatura 对 SPA 页面常返回空串
_EMPTY_CONTENT_THRESHOLD = 24

Resolver = Callable[[str], list[str]]


# ---------------------------------------------------------------------------
# SSRF 防护
# ---------------------------------------------------------------------------


def _resolve_sync(host: str) -> list[str]:
    """同步解析 host 的全部 A/AAAA 地址（字符串形式，供校验）。"""
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return list({str(info[4][0]) for info in infos})


def _is_public_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def validate_public_http_url(
    url: str, *, resolve: Resolver | None = None
) -> tuple[bool, str | None]:
    """校验 URL 是否指向公网 http(s) 目标。

    resolve 供测试注入假解析器；默认真实 DNS。返回 ``(ok, error)``。
    """
    raw = (url or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        return False, "web_fetch_ssrf_blocked: only http/https URLs are allowed"
    host = parts.hostname
    if not host:
        return False, "web_fetch_ssrf_blocked: missing host"
    # IP 字面量直接判定（不经解析器——解析器结果与字面量无关，送进去反而
    # 给测试注入口留下绕过面）
    try:
        ipaddress.ip_address(host.strip("[]"))
        if not _is_public_ip(host.strip("[]")):
            return False, f"web_fetch_ssrf_blocked: non-public address {host}"
        return True, None
    except ValueError:
        pass
    try:
        if resolve is not None:
            addrs = [str(a) for a in resolve(host)]
        else:
            addrs = await run_blocking_io(_resolve_sync, host)
    except (socket.gaierror, OSError) as exc:
        return False, f"web_fetch_ssrf_blocked: DNS resolution failed ({exc})"
    if not addrs:
        return False, "web_fetch_ssrf_blocked: host resolved to no addresses"
    for addr in addrs:
        if not _is_public_ip(addr):
            return False, f"web_fetch_ssrf_blocked: {host} resolves to non-public address {addr}"
    return True, None


# ---------------------------------------------------------------------------
# httpx client 复用（重定向手动跟随以便逐跳校验）
# ---------------------------------------------------------------------------

_web_fetch_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _web_fetch_client
    if _web_fetch_client is None or getattr(_web_fetch_client, "is_closed", False):
        _web_fetch_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=DIRECT_FETCH_TIMEOUT_S, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=4),
            follow_redirects=False,
        )
    return _web_fetch_client


async def close_web_fetch_client() -> None:
    """关闭复用的 httpx client（应用关闭时调用）。"""
    global _web_fetch_client
    if _web_fetch_client is not None and not getattr(_web_fetch_client, "is_closed", False):
        await _web_fetch_client.aclose()
    _web_fetch_client = None


async def _request_no_redirect(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """单跳请求（不跟随重定向），带体积上限的增量下载。"""

    async with client.stream(method, url, headers=_FETCH_HEADERS, **kwargs) as response:
        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            chunks.append(chunk)
            if received >= DIRECT_MAX_BODY_BYTES:
                break
        body = b"".join(chunks[: (DIRECT_MAX_BODY_BYTES // 4096) + 1])[:DIRECT_MAX_BODY_BYTES]
        # 重新构造为普通 Response（调用方只读 status/headers/body）
        return httpx.Response(
            response.status_code,
            headers=dict(response.headers),
            content=body,
            request=httpx.Request(method, url),
        )


# ---------------------------------------------------------------------------
# 正文提取：HTML → Markdown（trafilatura）
# ---------------------------------------------------------------------------


def _extract_markdown(html: str) -> tuple[str | None, str]:
    """HTML → (title, markdown 正文)；提取失败返回 (None, "")。"""
    import trafilatura

    try:
        metadata = trafilatura.extract_metadata(html)
        title = (metadata.title or "").strip() if metadata else None
        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_images=False,  # 内嵌图 markdown 对 LLM 是噪声，图片走 web_search
            with_metadata=False,
            url=None,
        )
    except Exception as exc:  # noqa: BLE001 - 提取器对畸形 HTML 可能抛出
        logger.warning("[WebFetch] trafilatura extract failed: %s", exc)
        return None, ""
    return title, (extracted or "").strip()


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "…", True


def _fetch_result(
    *,
    url: str,
    final_url: str,
    provider: str,
    title: str | None,
    content: str,
    content_type: str | None,
    truncated: bool,
) -> dict[str, Any]:
    return {
        "success": True,
        "url": url,
        "final_url": final_url,
        "provider": provider,
        "title": title,
        "content": content,
        "content_chars": len(content),
        "truncated": truncated,
        "content_type": content_type,
    }


# ---------------------------------------------------------------------------
# direct 供应商
# ---------------------------------------------------------------------------


async def direct_fetch(client: httpx.AsyncClient, url: str, max_chars: int) -> dict[str, Any]:
    """本机抓取：SSRF 校验 → 逐跳重定向 → 内容类型分发 → Markdown 提取/截断。"""
    ok, err = await validate_public_http_url(url)
    if not ok:
        return {"success": False, "error": err}

    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        response = await _request_no_redirect(client, "GET", current)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if not location:
                return {"success": False, "error": "web_fetch_redirect_missing_location"}
            current = urljoin(current, location)
            ok, err = await validate_public_http_url(current)
            if not ok:
                return {"success": False, "error": err}
            continue
        break
    else:
        return {"success": False, "error": "web_fetch_too_many_redirects"}

    if response.status_code >= 400:
        return {"success": False, "error": f"web_fetch_http_{response.status_code}"}

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type.startswith("text/html") or (
        content_type == "" and response.text.lstrip()[:1] == "<"
    ):
        html = response.text
        title, markdown = _extract_markdown(html)
        if len(markdown) < _EMPTY_CONTENT_THRESHOLD:
            # SPA/JS 渲染页：直连拿不到正文，交回供应商链走 Jina 兜底
            return {"success": False, "error": "web_fetch_empty_content"}
        content, truncated = _truncate(markdown, max_chars)
        return _fetch_result(
            url=url,
            final_url=str(response.request.url),
            provider="direct",
            title=title,
            content=content,
            content_type=content_type,
            truncated=truncated,
        )
    if content_type.startswith("text/") or content_type in (
        "application/json",
        "application/xml",
        "application/javascript",
        "text/markdown",
    ):
        content, truncated = _truncate(response.text.strip(), max_chars)
        return _fetch_result(
            url=url,
            final_url=str(response.request.url),
            provider="direct",
            title=None,
            content=content,
            content_type=content_type or "text/plain",
            truncated=truncated,
        )
    return {
        "success": False,
        "error": f"web_fetch_unsupported_content_type: {content_type or 'unknown'}",
    }


# ---------------------------------------------------------------------------
# jina 供应商（r.jina.ai URL 前缀协议）
# ---------------------------------------------------------------------------

_jina_pool: ApiKeyPool | None = None
_jina_pool_signature: str = ""


def _jina_keys() -> list[str]:
    raw = str(getattr(settings, "JINA_API_KEYS", "") or "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _get_jina_pool() -> ApiKeyPool | None:
    global _jina_pool, _jina_pool_signature
    keys = _jina_keys()
    signature = ",".join(keys)
    if _jina_pool is None or _jina_pool_signature != signature:
        if not keys:
            _jina_pool, _jina_pool_signature = None, signature
            return None
        _jina_pool = ApiKeyPool(keys)
        _jina_pool_signature = signature
    return _jina_pool


async def jina_fetch(
    client: httpx.AsyncClient, url: str, api_key: str, max_chars: int
) -> dict[str, Any]:
    """Jina Reader 兜底：GET r.jina.ai/<url>，响应即 Markdown。

    URL 先过同一套 SSRF 校验——Jina 在其基础设施侧抓取，内网探测不会真的
    发包，但错误消息/超时差仍是内网测绘信道，一律前置拒绝。
    """
    ok, err = await validate_public_http_url(url)
    if not ok:
        return {"success": False, "error": err}

    headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = await _request_no_redirect(
        client, "GET", f"{JINA_READER_PREFIX}{url}", headers=headers
    )
    _raise_for_status(response)
    title = (response.headers.get("title") or "").strip() or None
    # 响应首行常是 "Markdown Source:"，对 LLM 无信息量，剥掉
    text = response.text.strip()
    if text.lower().startswith("markdown source:"):
        text = text.split("\n", 1)[1].strip() if "\n" in text else ""
    if len(text) < _EMPTY_CONTENT_THRESHOLD:
        return {"success": False, "error": "web_fetch_empty_content"}
    content, truncated = _truncate(text, max_chars)
    return _fetch_result(
        url=url,
        final_url=url,
        provider="jina",
        title=title,
        content=content,
        content_type="text/markdown",
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# 供应商链与执行入口
# ---------------------------------------------------------------------------


def resolve_fetch_chain() -> list[str]:
    """供应商链：auto = direct → jina（有 key 才含）；钉死则单元素。"""
    provider = str(getattr(settings, "WEB_FETCH_PROVIDER", "auto") or "auto").strip().lower()
    if provider == "direct":
        return ["direct"]
    if provider == "jina":
        return ["jina"]
    chain = ["direct"]
    if _jina_keys():
        chain.append("jina")
    return chain


async def execute_web_fetch(
    url: str, max_chars: int, *, provider: str | None = None
) -> dict[str, Any]:
    """执行网页抓取：SSRF 前置校验 → 供应商链。永不抛异常。"""
    ok, err = await validate_public_http_url(url)
    if not ok:
        return {"success": False, "error": err}

    if provider in ("direct", "jina"):
        chain = [provider]
    else:
        chain = resolve_fetch_chain()

    client = _get_client()
    errors: list[str] = []
    for name in chain:
        if name == "direct":
            try:
                result = await direct_fetch(client, url, max_chars)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[WebFetch] direct failed: %s", exc)
                errors.append(f"direct: {exc}")
                continue
            if result.get("success"):
                return result
            errors.append(str(result.get("error")))
            continue

        pool = _get_jina_pool()
        if pool is None:
            errors.append("jina: no api keys configured")
            continue
        picked = pool.next_key()
        if picked is None:
            errors.append("jina: all keys cooling down")
            continue
        index, key = picked
        try:
            result = await jina_fetch(client, url, key, max_chars)
        except ProviderRequestError as exc:
            if exc.status_code in (429, 432, 402):
                pool.mark_cooldown(index, _COOLDOWN_429_S)
            elif exc.status_code in (401, 403):
                pool.mark_cooldown(index, 6 * 3600.0)
            else:
                pool.mark_cooldown(index, 30.0)
            errors.append(f"jina key#{index + 1}: HTTP {exc.status_code}")
            continue
        except Exception as exc:  # noqa: BLE001
            pool.mark_cooldown(index, 30.0)
            errors.append(f"jina key#{index + 1}: {exc}")
            continue
        if result.get("success"):
            return result
        errors.append(str(result.get("error")))

    return {"success": False, "error": "web_fetch_all_providers_failed", "details": errors}


def _reset_web_fetch_state() -> None:
    """测试钩子：重置模块级单例。"""
    global _web_fetch_client, _jina_pool, _jina_pool_signature
    _web_fetch_client = None
    _jina_pool = None
    _jina_pool_signature = ""

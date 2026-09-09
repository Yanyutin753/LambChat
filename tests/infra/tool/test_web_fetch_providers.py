"""web_fetch 供应商层：SSRF 防护、direct 抓取提取、Jina 兜底、供应商链。"""

from __future__ import annotations

import httpx
import pytest

import src.infra.tool.web_fetch_providers as wfp
import src.infra.tool.web_search_providers as wsp


@pytest.fixture(autouse=True)
def _reset_web_fetch_state():
    wfp._reset_web_fetch_state()
    yield
    wfp._reset_web_fetch_state()


def _public_dns(host: str) -> list[str]:
    """模拟公网解析：localhost 除外（对齐真实 getaddrinfo 的环回语义）。"""
    return ["127.0.0.1"] if host == "localhost" else ["93.184.216.34"]


# ---------------------------------------------------------------------------
# SSRF 防护：仅公网 http(s)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost/x",
        "https://localhost:8443/x",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://172.16.0.1/x",
        "http://169.254.169.254/latest/meta-data",  # 云元数据端点
        "http://[::1]/x",
        "http://[fd00::1]/x",
        "http://0.0.0.0/x",
        "ftp://example.com/x",
        "file:///etc/passwd",
        "not-a-url",
        "",
    ],
)
async def test_ssrf_rejects_private_and_non_http_targets(url: str) -> None:
    ok, err = await wfp.validate_public_http_url(url, resolve=_public_dns)
    assert not ok, url
    assert err


async def test_ssrf_rejects_public_name_resolving_to_private_ip() -> None:
    """DNS 重绑定面：域名解析到内网地址同样拒绝（按解析结果判定）。"""

    def rebinding_dns(host: str) -> list[str]:
        return ["10.0.0.7"]

    ok, err = await wfp.validate_public_http_url("http://evil.example/x", resolve=rebinding_dns)
    assert not ok
    assert err


async def test_ssrf_accepts_public_http_url() -> None:
    ok, err = await wfp.validate_public_http_url(
        "https://example.com/page?a=1", resolve=_public_dns
    )
    assert ok, err


# ---------------------------------------------------------------------------
# direct 抓取：HTML → Markdown、内容类型分发、截断
# ---------------------------------------------------------------------------


async def _allow_all(url, resolve=None):
    return True, None


def _html_response(body: str, content_type: str = "text/html; charset=utf-8") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"Content-Type": content_type},
        content=body.encode("utf-8"),
        request=httpx.Request("GET", "https://example.com/page"),
    )


async def test_direct_fetch_extracts_html_to_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    paragraph = "这是正文段落，包含足够长的内容以通过空正文阈值判定。" * 3
    html = (
        "<html><head><title>示例页</title></head><body>"
        f"<article><h1>标题一</h1><p>{paragraph}</p></article>"
        "</body></html>"
    )

    async def fake_request(client, method, url, **kwargs):
        return _html_response(html)

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://example.com/page", 32768)
    assert result["success"] is True
    assert result["provider"] == "direct"
    assert "标题一" in result["content"]
    assert "<html>" not in result["content"]
    assert result["title"]


async def test_direct_fetch_plain_text_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, **kwargs):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            content="plain body line",
            request=httpx.Request("GET", "https://example.com/robots.txt"),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://example.com/robots.txt", 32768)
    assert result["success"] is True
    assert "plain body line" in result["content"]


async def test_direct_fetch_truncates_to_max_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<html><body><article>" + ("<p>段落内容重复。</p>" * 2000) + "</article></body></html>"

    async def fake_request(client, method, url, **kwargs):
        return _html_response(html)

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://example.com/page", 1000)
    assert result["success"] is True
    assert result["truncated"] is True
    assert len(result["content"]) <= 1000 + 1  # 截断标记占用 1 字符
    assert result["content"].endswith("…")


async def test_direct_fetch_rejects_binary_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, **kwargs):
        return _html_response("%PDF-1.7 fake", "application/pdf")

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://example.com/doc.pdf", 32768)
    assert result["success"] is False
    assert "unsupported_content_type" in result["error"]


async def test_direct_fetch_follows_redirects_with_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重定向逐跳跟随且每一跳都过 SSRF 校验——跳向内网即拒绝。"""
    responses = [
        httpx.Response(
            301,
            headers={"Location": "http://192.168.0.9/inner"},
            request=httpx.Request("GET", "https://example.com/redirect"),
        ),
    ]

    async def fake_request(client, method, url, **kwargs):
        return responses.pop(0)

    async def selective_guard(url, resolve=None):
        if "192.168.0.9" in url:
            return False, "web_fetch_ssrf_blocked: non-public address"
        return True, None

    monkeypatch.setattr(wfp, "validate_public_http_url", selective_guard)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://example.com/redirect", 32768)
    assert result["success"] is False
    assert "ssrf" in result["error"] or "blocked" in result["error"]


# ---------------------------------------------------------------------------
# Jina 兜底
# ---------------------------------------------------------------------------


async def test_jina_fetch_returns_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, **kwargs):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain", "Title": "Jina Page Title"},
            content="Markdown Source:\n\n# 来自 Jina 的正文\n\n这一段是足够长的正文内容，用来通过空正文阈值判定。\n",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.jina_fetch(wfp._get_client(), "https://example.com/js-page", "key1", 32768)
    assert result["success"] is True
    assert result["provider"] == "jina"
    assert "Jina 的正文" in result["content"]
    assert result["title"] == "Jina Page Title"


# ---------------------------------------------------------------------------
# 供应商链与执行入口
# ---------------------------------------------------------------------------


async def test_execute_web_fetch_auto_falls_back_to_jina(monkeypatch: pytest.MonkeyPatch) -> None:
    """auto 链：direct 失败（SPA 空正文）→ Jina 兜底成功。"""
    calls: list[str] = []

    async def failing_direct(client, url, max_chars):
        calls.append("direct")
        return {"success": False, "error": "web_fetch_empty_content"}

    async def ok_jina(client, url, key, max_chars):
        calls.append("jina")
        return {
            "success": True,
            "provider": "jina",
            "url": url,
            "final_url": url,
            "title": "t",
            "content": "# ok",
            "content_chars": 4,
            "truncated": False,
        }

    monkeypatch.setattr(wfp, "direct_fetch", failing_direct)
    monkeypatch.setattr(wfp, "jina_fetch", ok_jina)
    monkeypatch.setattr(wfp, "_jina_keys", lambda: ["k1"])
    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)

    result = await wfp.execute_web_fetch("https://example.com/js", 32768, provider="auto")
    assert result["success"] is True
    assert calls == ["direct", "jina"]


async def test_execute_web_fetch_pinned_direct_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_direct(client, url, max_chars):
        return {"success": False, "error": "web_fetch_empty_content"}

    async def never_jina(client, url, key, max_chars):
        raise AssertionError("pinned direct must not call jina")

    monkeypatch.setattr(wfp, "direct_fetch", failing_direct)
    monkeypatch.setattr(wfp, "jina_fetch", never_jina)
    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)

    result = await wfp.execute_web_fetch("https://example.com/x", 32768, provider="direct")
    assert result["success"] is False


async def test_execute_web_fetch_ssrf_blocked_never_reaches_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never(client, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("blocked url must not reach providers")

    monkeypatch.setattr(wfp, "direct_fetch", never)
    monkeypatch.setattr(wfp, "jina_fetch", never)

    result = await wfp.execute_web_fetch("http://127.0.0.1:8000/api/auth/login", 32768)
    assert result["success"] is False
    assert "ssrf" in result["error"] or "blocked" in result["error"]


# ---------------------------------------------------------------------------
# 微信公众号专属提取 + Tavily Extract 兜底（2026-09-09 增强）
# ---------------------------------------------------------------------------

_WECHAT_HTML = (
    "<html><head><title>公众号文章</title>"
    '<meta property="og:title" content="深度：开源 Agent 的正文提取实践" /></head>'
    "<body><div id='js_content'><p>这是公众号正文第一段，足够长以通过阈值判定。</p>"
    "<p>第二段内容：<strong>关键结论</strong>与细节展开。</p>"
    "<script>evil()</script></div></body></html>"
)


async def test_direct_fetch_wechat_uses_js_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, **kwargs):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=_WECHAT_HTML.encode("utf-8"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://mp.weixin.qq.com/s/abc123", 32768)
    assert result["success"] is True
    assert result["title"] == "深度：开源 Agent 的正文提取实践"
    assert "公众号正文第一段" in result["content"]
    assert "关键结论" in result["content"]
    assert "evil()" not in result["content"]  # script 必须剥除


async def test_direct_fetch_generic_site_with_js_content_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非微信域但沿用 js_content 容器的站点：通用提取空正文时按同结构再试。"""

    async def fake_request(client, method, url, **kwargs):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=_WECHAT_HTML.encode("utf-8"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.direct_fetch(wfp._get_client(), "https://news.example.com/article/1", 32768)
    assert result["success"] is True
    assert "公众号正文第一段" in result["content"]


async def test_tavily_extract_normalizes_raw_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, *, json=None, headers=None):
        assert url == wfp.TAVILY_EXTRACT_URL
        assert method == "POST"
        assert json == {"urls": ["https://example.com/doc"]}
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=(
                '{"results": [{"url": "https://example.com/doc", '
                '"raw_content": "# 标题行\\n\\nTavily 抽取的正文内容，长度足以通过阈值判定。"}]}'
            ).encode(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.tavily_extract(
        wfp._get_client(), "https://example.com/doc", "tvly-key", 32768
    )
    assert result["success"] is True
    assert result["provider"] == "tavily"
    assert result["title"] == "标题行"  # raw 首行 "# 标题行" 提升为 title
    assert "Tavily 抽取的正文" in result["content"]
    assert not result["content"].startswith("# 标题行")


async def test_tavily_extract_reports_failed_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(client, method, url, *, json=None, headers=None):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=b'{"results": [], "failed_results": [{"url": "x", "error": "403"}]}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.tavily_extract(
        wfp._get_client(), "https://example.com/doc", "tvly-key", 32768
    )
    assert result["success"] is False
    assert "web_fetch_tavily_failed" in result["error"]


def test_resolve_fetch_chain_includes_tavily_when_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wfp, "_tavily_available", lambda: True)
    monkeypatch.setattr(wfp, "_jina_keys", lambda: ["jk1"])
    assert wfp.resolve_fetch_chain() == ["direct", "tavily", "jina"]

    monkeypatch.setattr(wfp, "_tavily_available", lambda: False)
    assert wfp.resolve_fetch_chain() == ["direct", "jina"]


async def test_execute_web_fetch_falls_back_to_tavily_on_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直连被拦（403 反爬）→ tavily extract 接住：auto 链的次序保证。"""
    calls: list[str] = []

    async def blocked_direct(client, url, max_chars):
        calls.append("direct")
        return {"success": False, "error": "web_fetch_http_403"}

    async def ok_tavily(client, url, key, max_chars):
        calls.append("tavily")
        return {
            "success": True,
            "provider": "tavily",
            "url": url,
            "final_url": url,
            "title": None,
            "content": "兜底正文内容，长度足以通过阈值判定。",
            "content_chars": 30,
            "truncated": False,
        }

    async def never_jina(client, url, key, max_chars):
        calls.append("jina")
        raise AssertionError("tavily 已成功，不应再落 jina")

    monkeypatch.setattr(wfp, "direct_fetch", blocked_direct)
    monkeypatch.setattr(wfp, "tavily_extract", ok_tavily)
    monkeypatch.setattr(wfp, "jina_fetch", never_jina)
    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_tavily_available", lambda: True)
    monkeypatch.setattr(wfp, "_jina_keys", lambda: ["jk1"])
    monkeypatch.setattr(wfp, "_get_pool", lambda provider: wsp.ApiKeyPool(["tk1"]))

    result = await wfp.execute_web_fetch(
        "https://mp.weixin.qq.com/s/blocked", 32768, provider="auto"
    )
    assert result["success"] is True
    assert result["provider"] == "tavily"
    assert calls == ["direct", "tavily"]


async def test_execute_web_fetch_pinned_jina_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    """钉死 jina 且未配 key：走官方免 key 模式（单空 key），不报「未配置」。"""
    seen_keys: list[str] = []

    async def ok_jina(client, url, key, max_chars):
        seen_keys.append(key)
        return {
            "success": True,
            "provider": "jina",
            "url": url,
            "final_url": url,
            "title": "t",
            "content": "免 key 模式取回的正文内容。",
            "content_chars": 30,
            "truncated": False,
        }

    monkeypatch.setattr(wfp, "jina_fetch", ok_jina)
    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)

    result = await wfp.execute_web_fetch("https://example.com/x", 32768, provider="jina")
    assert result["success"] is True
    assert seen_keys == [""]  # 空 key = 不带 Authorization 头


# ---------------------------------------------------------------------------
# Firecrawl / Exa 渠道（2026-09-09 二轮扩展）
# ---------------------------------------------------------------------------


async def test_firecrawl_fetch_saas_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_request(client, method, url, *, json=None, headers=None):
        seen.update(url=url, method=method, json=json, headers=headers)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=(
                '{"success": true, "data": {"markdown": "# Firecrawl 正文\\n\\n'
                '足够长的正文内容以通过阈值判定。", '
                '"metadata": {"title": "FC 标题", "url": "https://example.com/final"}}}'
            ).encode(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.firecrawl_fetch(
        wfp._get_client(), "https://example.com/page", "fc-key", 32768
    )
    assert seen["url"] == "https://api.firecrawl.dev/v1/scrape"
    assert seen["json"] == {"url": "https://example.com/page", "formats": ["markdown"]}
    assert seen["headers"]["Authorization"] == "Bearer fc-key"
    assert result["success"] is True
    assert result["provider"] == "firecrawl"
    assert result["title"] == "FC 标题"
    assert result["final_url"] == "https://example.com/final"
    assert "Firecrawl 正文" in result["content"]


async def test_firecrawl_fetch_selfhost_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    """自建实例（非默认 BASE_URL）：无 key 不带 Authorization 头。"""
    seen: dict = {}

    async def fake_request(client, method, url, *, json=None, headers=None):
        seen.update(url=url, headers=headers)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=('{"data": {"markdown": "自建实例正文，足够长以通过阈值判定。"}}').encode(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    monkeypatch.setattr(wfp, "_firecrawl_base", lambda: "http://fc.internal:3000")
    result = await wfp.firecrawl_fetch(wfp._get_client(), "https://example.com/page", "", 32768)
    assert seen["url"] == "http://fc.internal:3000/v1/scrape"
    assert "Authorization" not in seen["headers"]
    assert result["success"] is True


async def test_exa_fetch_normalizes_results(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_request(client, method, url, *, json=None, headers=None):
        seen.update(url=url, json=json, headers=headers)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=(
                '{"results": [{"url": "https://example.com/doc", "title": "Exa 标题", '
                '"text": "Exa 返回的正文内容，足够长以通过阈值判定。"}]}'
            ).encode(),
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_request_no_redirect", fake_request)
    result = await wfp.exa_fetch(wfp._get_client(), "https://example.com/doc", "exa-key", 32768)
    assert seen["url"] == wfp.EXA_CONTENTS_URL
    assert seen["json"] == {"urls": ["https://example.com/doc"]}
    assert seen["headers"]["x-api-key"] == "exa-key"
    assert result["success"] is True
    assert result["provider"] == "exa"
    assert result["title"] == "Exa 标题"
    assert "Exa 返回的正文" in result["content"]


def test_resolve_fetch_chain_full_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wfp, "_tavily_available", lambda: True)
    monkeypatch.setattr(wfp, "_firecrawl_keys", lambda: ["fk1"])
    monkeypatch.setattr(wfp, "_exa_keys", lambda: ["ek1"])
    monkeypatch.setattr(wfp, "_jina_keys", lambda: ["jk1"])
    assert wfp.resolve_fetch_chain() == ["direct", "tavily", "firecrawl", "exa", "jina"]


def test_resolve_fetch_chain_selfhost_firecrawl_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自建 Firecrawl（仅 BASE_URL 无 key）也纳入链路。"""
    monkeypatch.setattr(wfp, "_tavily_available", lambda: False)
    monkeypatch.setattr(wfp, "_firecrawl_keys", lambda: [])
    monkeypatch.setattr(wfp, "_exa_keys", lambda: [])
    monkeypatch.setattr(wfp, "_jina_keys", lambda: [])
    monkeypatch.setattr(
        wfp.settings, "FIRECRAWL_BASE_URL", "http://fc.internal:3000", raising=False
    )
    assert wfp.resolve_fetch_chain() == ["direct", "firecrawl"]


async def test_execute_web_fetch_skips_unkeyed_providers_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全链无 key（tavily/firecrawl/exa/jina 都没配）：逐层跳过并汇总错误，不崩。"""
    calls: list[str] = []

    async def empty_direct(client, url, max_chars):
        calls.append("direct")
        return {"success": False, "error": "web_fetch_http_403"}

    monkeypatch.setattr(wfp, "direct_fetch", empty_direct)
    monkeypatch.setattr(wfp, "validate_public_http_url", _allow_all)
    monkeypatch.setattr(wfp, "_tavily_available", lambda: True)
    monkeypatch.setattr(wfp, "_firecrawl_keys", lambda: [])
    monkeypatch.setattr(wfp, "_exa_keys", lambda: [])
    monkeypatch.setattr(wfp, "_jina_keys", lambda: [])
    # tavily 池真实存在（从 web_search 设置读）但本环境为空 → 链上跳过
    monkeypatch.setattr(wfp, "_get_pool", lambda provider: None)
    monkeypatch.setattr(wfp.settings, "FIRECRAWL_BASE_URL", "", raising=False)

    result = await wfp.execute_web_fetch("https://example.com/x", 32768, provider="auto")
    assert result["success"] is False
    assert calls == ["direct"]
    assert result["error"] == "web_fetch_all_providers_failed"

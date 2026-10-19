"""Official standalone DeepSeek web API contract and safety boundaries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import src.infra.tool.web_fetch_providers as fetch
import src.infra.tool.web_search_providers as search


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    search._reset_web_search_state()
    fetch._reset_web_fetch_state()
    config = SimpleNamespace(
        DEEPSEEK_API_KEYS="key-a,key-b",
        WEB_SEARCH_PROVIDER="deepseek",
        WEB_FETCH_PROVIDER="deepseek",
    )
    monkeypatch.setattr(search, "settings", config)
    monkeypatch.setattr(fetch, "settings", config)
    yield
    search._reset_web_search_state()
    fetch._reset_web_fetch_state()


def client_for(monkeypatch, responses):
    requests = []

    def handle(request):
        requests.append(request)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(search, "_get_client", lambda: client)
    monkeypatch.setattr(fetch, "_get_client", lambda: client)
    return client, requests


async def allow_public(url, **kwargs):
    return True, None


async def test_search_official_contract_and_rotation(monkeypatch):
    body = {
        "results": [
            {
                "title": "Python",
                "url": "https://python.org",
                "snippet": "short",
                "summary": "long",
                "rerank_score": 2.4,
                "site_icon": "https://python.org/icon",
                "date": "2026-10-01",
            },
            {"url": "javascript:bad"},
        ]
    }
    client, requests = client_for(
        monkeypatch, [httpx.Response(200, json=body), httpx.Response(200, json={"results": []})]
    )
    async with client:
        first = await search.execute_web_search("Python", 3, None)
        second = await search.execute_web_search("Python", 3, None)
    import json

    assert str(requests[0].url) == "https://api.deepseek.com/v1/tools/search"
    assert json.loads(requests[0].content) == {"query": "Python", "count": 3, "need_content": False}
    assert [r.headers["authorization"] for r in requests] == ["Bearer key-a", "Bearer key-b"]
    assert first["provider"] == "deepseek"
    assert first["results"] == [
        {
            "title": "Python",
            "url": "https://python.org",
            "snippet": "long",
            "score": pytest.approx(0.8),
            "favicon_url": "https://python.org/icon",
            "published_date": "2026-10-01",
        }
    ]
    assert second["success"] and second["results"] == []


async def test_search_time_range_uses_documented_after_operator(monkeypatch):
    client, requests = client_for(monkeypatch, [httpx.Response(200, json={"results": []})])
    before = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    async with client:
        result = await search.execute_web_search("Python site:python.org", 5, "week")
    import json

    assert result["success"]
    assert json.loads(requests[0].content)["query"] == f"Python site:python.org after:{before}"


@pytest.mark.parametrize(
    "body", [{}, {"results": None}, [], {"error": {"message": "secret-marker"}}]
)
async def test_search_rejects_malformed_response_without_body_leak(monkeypatch, body, caplog):
    client, _ = client_for(
        monkeypatch, [httpx.Response(200, json=body), httpx.Response(200, json=body)]
    )
    async with client:
        result = await search.execute_web_search("Python", 3, None)
    assert not result["success"]
    assert "secret-marker" not in str(result) + caplog.text


@pytest.mark.parametrize("query", [" " * 3, "x" * 129])
async def test_search_invalid_query_does_not_make_paid_request(monkeypatch, query):
    client, requests = client_for(monkeypatch, [])
    async with client:
        result = await search.execute_web_search(query, 3, None)
    assert not result["success"]
    assert requests == []


async def test_fetch_normalizes_markdown_and_rotates_keys(monkeypatch):
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)
    client, requests = client_for(
        monkeypatch,
        [
            httpx.Response(200, json={"title": "Python", "content": "abcdefghijklmnop"}),
            httpx.Response(200, json={"title": "", "content": "second page"}),
        ],
    )
    async with client:
        first = await fetch.execute_web_fetch("https://python.org", 8)
        second = await fetch.execute_web_fetch("https://python.org", 100)
    import json

    assert str(requests[0].url) == "https://api.deepseek.com/v1/tools/fetch"
    assert json.loads(requests[0].content) == {"url": "https://python.org"}
    assert [r.headers["authorization"] for r in requests] == ["Bearer key-a", "Bearer key-b"]
    assert first["success"] and first["provider"] == "deepseek"
    assert first["content"] == "abcdefgh…" and first["truncated"]
    assert second["success"] and second["content_type"] == "text/markdown"


@pytest.mark.parametrize("status", [401, 402, 429, 500])
async def test_fetch_failed_key_tries_next_and_persists_cooldown(monkeypatch, status, caplog):
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)
    client, requests = client_for(
        monkeypatch,
        [
            httpx.Response(status, json={"error": {"message": "secret-marker"}}),
            httpx.Response(200, json={"title": "ok", "content": "valid content"}),
            httpx.Response(200, json={"title": "ok", "content": "valid content"}),
        ],
    )
    async with client:
        first = await fetch.execute_web_fetch("https://python.org", 100)
        second = await fetch.execute_web_fetch("https://python.org", 100)
    assert first["success"] and second["success"]
    assert [r.headers["authorization"] for r in requests] == [
        "Bearer key-a",
        "Bearer key-b",
        "Bearer key-b",
    ]
    assert "secret-marker" not in str(first) + str(second) + caplog.text


@pytest.mark.parametrize(
    "body", [{}, [], {"title": "x", "content": 42}, {"title": "x", "content": ""}]
)
async def test_fetch_rejects_malformed_or_empty_content(monkeypatch, body):
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)
    client, _ = client_for(
        monkeypatch, [httpx.Response(200, json=body), httpx.Response(200, json=body)]
    )
    async with client:
        result = await fetch.execute_web_fetch("https://python.org", 100)
    assert not result["success"]


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1", "https://user:password@python.org", "https://python.org/" + ("a" * 8192)],
    ids=["private", "userinfo", "too-long"],
)
async def test_fetch_rejects_unsafe_urls_without_network(monkeypatch, url):
    client, requests = client_for(monkeypatch, [])
    async with client:
        result = await fetch.execute_web_fetch(url, 100)
    assert not result["success"] and requests == []


async def test_fetch_transport_error_never_exposes_credentials(monkeypatch, caplog):
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)
    client, _ = client_for(
        monkeypatch, [httpx.LocalProtocolError("Authorization: Bearer secret-marker")] * 2
    )
    async with client:
        result = await fetch.execute_web_fetch("https://python.org", 100)
    assert not result["success"]
    assert "secret-marker" not in str(result) + caplog.text


async def test_invalid_search_does_not_cool_valid_keys(monkeypatch):
    client, requests = client_for(monkeypatch, [httpx.Response(200, json={"results": []})])
    async with client:
        invalid = await search.execute_web_search("x" * 129, 3, None)
        valid = await search.execute_web_search("Python", 3, None)
    assert not invalid["success"] and valid["success"]
    assert len(requests) == 1


async def test_fetch_url_policy_failure_does_not_cool_account_keys(monkeypatch):
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)
    client, requests = client_for(
        monkeypatch,
        [
            httpx.Response(403, json={"error": {"message": "secret-marker"}}),
            httpx.Response(200, json={"title": "ok", "content": "page"}),
        ],
    )
    async with client:
        blocked = await fetch.execute_web_fetch("https://python.org/blocked", 100)
        valid = await fetch.execute_web_fetch("https://python.org", 100)
    assert not blocked["success"] and valid["success"]
    assert search._get_pool("deepseek")._cooldown_until == {}
    assert len(requests) == 2


async def test_auto_search_and_fetch_fall_back_after_deepseek_failure(monkeypatch):
    monkeypatch.setattr(search.settings, "WEB_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(search.settings, "WEB_FETCH_PROVIDER", "auto")
    monkeypatch.setattr(search.settings, "TAVILY_API_KEYS", "tavily", raising=False)
    monkeypatch.setattr(fetch, "validate_public_http_url", allow_public)

    async def failed_direct(*args):
        return {"success": False, "error": "blocked"}

    monkeypatch.setattr(fetch, "direct_fetch", failed_direct)
    client, requests = client_for(
        monkeypatch,
        [
            httpx.Response(401, json={}),
            httpx.Response(401, json={}),
            httpx.Response(
                200,
                json={
                    "results": [{"title": "ok", "url": "https://python.org", "content": "snippet"}]
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [{"url": "https://python.org", "raw_content": "valid page content"}]
                },
            ),
        ],
    )
    async with client:
        found = await search.execute_web_search("Python", 3, None)
        page = await fetch.execute_web_fetch("https://python.org", 100)
    assert found["provider"] == "tavily" and page["provider"] == "tavily"
    assert [str(r.url) for r in requests] == ["https://api.deepseek.com/v1/tools/search"] * 2 + [
        "https://api.tavily.com/search",
        "https://api.tavily.com/extract",
    ]


@pytest.mark.parametrize("score, expected", [(0, 0), (1.5, 0.5), (3, 1), (None, None)])
async def test_search_normalizes_deepseek_score_scale(monkeypatch, score, expected):
    client, _ = client_for(
        monkeypatch,
        [
            httpx.Response(
                200, json={"results": [{"url": "https://python.org", "rerank_score": score}]}
            )
        ],
    )
    async with client:
        result = await search.execute_web_search("Python", 3, None)
    assert result["results"][0]["score"] == expected

"""web_search 供应商层：多 key 轮询、错误感知冷却、供应商回退。"""

from __future__ import annotations

from typing import Any

import pytest

import src.infra.tool.web_search_providers as wsp


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._json


class _FakeHttpClient:
    """按调用顺序出队预设响应，并记录全部请求供断言。"""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        self.requests.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self._responses.pop(0)

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        self.requests.append({"method": "GET", "url": url, "params": params, "headers": headers})
        return self._responses.pop(0)


def _ok_tavily(title: str = "T") -> _FakeResponse:
    return _FakeResponse(
        json_data={"results": [{"title": title, "url": "https://t/1", "content": "c"}]}
    )


def _ok_brave(title: str = "B") -> _FakeResponse:
    return _FakeResponse(
        json_data={"web": {"results": [{"title": title, "url": "https://b/1", "description": "d"}]}}
    )


@pytest.fixture(autouse=True)
def _reset_web_search_state():
    wsp._reset_web_search_state()
    yield
    wsp._reset_web_search_state()


# ---------------------------------------------------------------------------
# ApiKeyPool 轮询 / 冷却
# ---------------------------------------------------------------------------


def test_api_key_pool_round_robin() -> None:
    pool = wsp.ApiKeyPool(["k1", "k2"])

    assert pool.next_key() == (0, "k1")
    assert pool.next_key() == (1, "k2")
    assert pool.next_key() == (0, "k1")


def test_api_key_pool_skips_cooldown_key() -> None:
    pool = wsp.ApiKeyPool(["k1", "k2"])
    pool.mark_cooldown(0, 60.0)

    assert pool.next_key() == (1, "k2")
    assert pool.next_key() == (1, "k2")


def test_api_key_pool_cooldown_expires() -> None:
    clock = {"now": 100.0}
    pool = wsp.ApiKeyPool(["k1", "k2"], now_fn=lambda: clock["now"])
    pool.mark_cooldown(0, 30.0)

    assert pool.next_key() == (1, "k2")

    clock["now"] = 131.0
    assert pool.next_key() == (0, "k1")


def test_api_key_pool_ignores_empty_entries() -> None:
    pool = wsp.ApiKeyPool(["", " k1 ", ""])

    assert len(pool) == 1
    assert pool.next_key() == (0, "k1")


def test_api_key_pool_empty_returns_none() -> None:
    assert wsp.ApiKeyPool([]).next_key() is None


# ---------------------------------------------------------------------------
# normalize_time_range
# ---------------------------------------------------------------------------


def test_normalize_time_range_accepts_aliases() -> None:
    assert wsp.normalize_time_range("day") == "day"
    assert wsp.normalize_time_range("d") == "day"
    assert wsp.normalize_time_range("WEEK") == "week"
    assert wsp.normalize_time_range(None) is None
    assert wsp.normalize_time_range("garbage") is None


# ---------------------------------------------------------------------------
# Tavily 供应商
# ---------------------------------------------------------------------------


async def test_tavily_search_normalizes_results_images_and_answer() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(
                json_data={
                    "query": "hello",
                    "answer": "42",
                    "results": [
                        {
                            "title": "R1",
                            "url": "https://a.com/1",
                            "content": "snippet-1",
                            "score": 0.9,
                            "favicon": "https://a.com/f.ico",
                        },
                        {
                            "title": "R2",
                            "url": "https://b.com/2",
                            "content": "snippet-2",
                            "published_date": "2026-09-01",
                        },
                    ],
                    "images": ["https://img/1", {"url": "https://img/2", "description": "d2"}],
                }
            )
        ]
    )

    out = await wsp.tavily_search(client, "tvly-k", "hello", 5, "week")

    req = client.requests[0]
    assert req["url"] == "https://api.tavily.com/search"
    assert req["headers"]["Authorization"] == "Bearer tvly-k"
    assert req["json"]["query"] == "hello"
    assert req["json"]["time_range"] == "week"
    assert req["json"]["include_images"] is True
    assert req["json"]["include_favicon"] is True

    assert out["success"] is True
    assert out["provider"] == "tavily"
    assert out["query"] == "hello"
    assert out["answer"] == "42"
    assert out["results"][0]["title"] == "R1"
    assert out["results"][0]["snippet"] == "snippet-1"
    assert out["results"][0]["score"] == 0.9
    assert out["results"][0]["favicon_url"] == "https://a.com/f.ico"
    assert out["results"][1]["published_date"] == "2026-09-01"
    assert out["images"] == [
        {"url": "https://img/1"},
        {"url": "https://img/2", "description": "d2"},
    ]


async def test_tavily_search_omits_absent_optional_fields() -> None:
    client = _FakeHttpClient([_ok_tavily()])

    out = await wsp.tavily_search(client, "tvly-k", "hello", 5, None)

    assert "time_range" not in client.requests[0]["json"]
    assert "answer" not in out
    assert out["results"][0]["score"] is None
    assert out["images"] == []


async def test_tavily_search_raises_provider_error_with_status() -> None:
    client = _FakeResponse(status_code=432, json_data={"detail": "Quota exceeded"})
    pool_client = _FakeHttpClient([client])

    with pytest.raises(wsp.ProviderRequestError) as exc_info:
        await wsp.tavily_search(pool_client, "tvly-k", "hello", 5, None)

    assert exc_info.value.status_code == 432


# ---------------------------------------------------------------------------
# Brave 供应商
# ---------------------------------------------------------------------------


async def test_brave_search_maps_freshness_and_normalizes() -> None:
    client = _FakeHttpClient([_ok_brave()])

    out = await wsp.brave_search(client, "brave-k", "hello", 3, "day")

    req = client.requests[0]
    assert req["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert req["headers"]["X-Subscription-Token"] == "brave-k"
    assert req["params"]["q"] == "hello"
    assert req["params"]["count"] == 3
    assert req["params"]["freshness"] == "pd"

    assert out["provider"] == "brave"
    assert out["results"][0]["title"] == "B"
    assert out["results"][0]["snippet"] == "d"
    assert out["images"] == []


async def test_brave_search_without_time_range_omits_freshness() -> None:
    client = _FakeHttpClient([_ok_brave()])

    await wsp.brave_search(client, "brave-k", "hello", 3, None)

    assert "freshness" not in client.requests[0]["params"]


# ---------------------------------------------------------------------------
# SearXNG 供应商
# ---------------------------------------------------------------------------


async def test_searxng_search_normalizes_and_passes_time_range() -> None:
    client = _FakeHttpClient(
        [
            _FakeResponse(
                json_data={
                    "answers": ["ans"],
                    "results": [
                        {
                            "title": "S1",
                            "url": "https://s.com/1",
                            "content": "c1",
                            "published_date": "2026-09-08",
                        },
                        {"title": "no-url", "content": "skipped"},
                    ],
                }
            )
        ]
    )

    out = await wsp.searxng_search(client, "https://searx.example", "key-opt", "hello", 5, "month")

    req = client.requests[0]
    assert req["url"] == "https://searx.example/search"
    assert req["params"]["format"] == "json"
    assert req["params"]["time_range"] == "month"
    assert req["headers"]["X-API-Key"] == "key-opt"

    assert out["provider"] == "searxng"
    assert out["answer"] == "ans"
    assert len(out["results"]) == 1
    assert out["results"][0]["title"] == "S1"
    assert out["results"][0]["snippet"] == "c1"


async def test_searxng_search_without_key_omits_header() -> None:
    client = _FakeHttpClient([_FakeResponse(json_data={"results": []})])

    await wsp.searxng_search(client, "https://searx.example", "", "hello", 5, None)

    assert "X-API-Key" not in (client.requests[0]["headers"] or {})


# ---------------------------------------------------------------------------
# execute_web_search 编排：轮询 / 冷却换 key / 供应商回退
# ---------------------------------------------------------------------------


def _configure(monkeypatch: pytest.MonkeyPatch, **values: Any) -> None:
    defaults = {
        "WEB_SEARCH_PROVIDER": "tavily",
        "TAVILY_API_KEYS": "",
        "BRAVE_API_KEYS": "",
        "SEARXNG_BASE_URL": "",
        "SEARXNG_API_KEY": "",
    }
    defaults.update(values)
    for key, value in defaults.items():
        monkeypatch.setattr(wsp.settings, key, value)


def _fake_client(
    monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResponse]
) -> _FakeHttpClient:
    client = _FakeHttpClient(responses)
    monkeypatch.setattr(wsp, "_get_client", lambda: client)
    return client


async def test_execute_web_search_rotates_keys_round_robin(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, TAVILY_API_KEYS="key-a,key-b")
    client = _fake_client(monkeypatch, [_ok_tavily(), _ok_tavily()])

    first = await wsp.execute_web_search("q1", 5, None)
    second = await wsp.execute_web_search("q2", 5, None)

    assert first["success"] is True
    assert second["success"] is True
    keys_used = [r["headers"]["Authorization"] for r in client.requests]
    assert keys_used == ["Bearer key-a", "Bearer key-b"]


async def test_execute_web_search_skips_rate_limited_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, TAVILY_API_KEYS="key-a,key-b")
    r429 = _FakeResponse(status_code=429, headers={"retry-after": "60"})
    client = _fake_client(monkeypatch, [r429, _ok_tavily(), _ok_tavily()])

    first = await wsp.execute_web_search("q1", 5, None)

    assert first["success"] is True
    await wsp.execute_web_search("q2", 5, None)
    keys_used = [r["headers"]["Authorization"] for r in client.requests]
    # key-a 429 冷却 → 同一次搜索切 key-b；冷却期内后续搜索直接用 key-b
    assert keys_used == ["Bearer key-a", "Bearer key-b", "Bearer key-b"]


async def test_execute_web_search_falls_back_to_next_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        monkeypatch, WEB_SEARCH_PROVIDER="auto", TAVILY_API_KEYS="tvly-x", BRAVE_API_KEYS="brave-y"
    )
    r432 = _FakeResponse(status_code=432, json_data={"detail": "quota"})
    client = _fake_client(monkeypatch, [r432, _ok_brave()])

    out = await wsp.execute_web_search("q", 5, None)

    assert out["success"] is True
    assert out["provider"] == "brave"


async def test_execute_web_search_returns_error_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, WEB_SEARCH_PROVIDER="auto")
    _fake_client(monkeypatch, [])

    out = await wsp.execute_web_search("q", 5, None)

    assert out["success"] is False
    assert out["error"]


async def test_execute_web_search_pinned_provider_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, WEB_SEARCH_PROVIDER="searxng", SEARXNG_BASE_URL="https://searx.example")
    client = _fake_client(monkeypatch, [_FakeResponse(status_code=502)])

    out = await wsp.execute_web_search("q", 5, None)

    assert out["success"] is False
    assert len(client.requests) == 1


async def test_execute_web_search_pool_rebuilds_when_keys_setting_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, TAVILY_API_KEYS="key-a")
    _fake_client(monkeypatch, [_ok_tavily(), _ok_tavily()])

    await wsp.execute_web_search("q1", 5, None)
    monkeypatch.setattr(wsp.settings, "TAVILY_API_KEYS", "key-z")
    await wsp.execute_web_search("q2", 5, None)

    keys_used = [
        r["headers"]["Authorization"]
        for r in wsp._get_client().requests  # type: ignore[attr-defined]
    ]
    assert keys_used == ["Bearer key-a", "Bearer key-z"]

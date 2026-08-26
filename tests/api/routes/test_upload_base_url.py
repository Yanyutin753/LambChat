"""上传 URL base_url 解析策略测试（分布式 P2-2 方案 A）。

多入口部署下上传 URL 应跟随当前请求入口（Host + X-Forwarded-Proto），
APP_BASE_URL 仅在无请求上下文（base_url 缺失）时兜底。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes.upload import _get_base_url
from src.kernel.config import settings


class _FakeRequest:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url
        self.headers = headers or {}


def _parse_headers(raw: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(
        get=lambda name, default="": raw.get(name.lower(), default)
    )


def _request(base_url: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
    req = _FakeRequest(base_url, headers)
    req.headers = _parse_headers(headers or {})
    return req


def test_request_entry_takes_priority_over_app_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com")

    result = _get_base_url(_request("https://test.lambchat.com/"))

    assert result == "https://test.lambchat.com"


def test_forwarded_proto_upgrades_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(
        _request(
            "http://test.lambchat.com/",
            {"x-forwarded-proto": "https"},
        )
    )

    assert result == "https://test.lambchat.com"


def test_app_base_url_used_as_fallback_when_request_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com/")

    result = _get_base_url(_request("http://None"))

    assert result == "https://lambchat.com"


def test_plain_http_without_forwarded_header_stays_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(_request("http://127.0.0.1:8010/"))

    assert result == "http://127.0.0.1:8010"

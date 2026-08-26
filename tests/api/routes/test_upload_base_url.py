"""上传 URL base_url 解析策略测试（分布式 P2-2 方案 A）。

多入口部署下上传 URL 应跟随当前请求入口（X-Forwarded-Host/Host +
X-Forwarded-Proto，兼容重写 Host 的代理与逗号列表），Host 不可用时才
回退 APP_BASE_URL（后台任务生成 URL 的场景）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes.upload import _get_base_url
from src.kernel.config import settings


def _request(base_url: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(base_url=base_url, headers=headers or {})


def test_request_entry_takes_priority_over_app_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com")

    result = _get_base_url(_request("http://internal:8000/", {"host": "test.lambchat.com"}))

    assert result == "https://test.lambchat.com"


def test_forwarded_proto_upgrades_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(
        _request(
            "http://test.lambchat.com/",
            {"host": "test.lambchat.com", "x-forwarded-proto": "https"},
        )
    )

    assert result == "https://test.lambchat.com"


def test_forwarded_proto_comma_list_uses_first_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(
        _request(
            "http://test.lambchat.com/",
            {"host": "test.lambchat.com", "x-forwarded-proto": "https, http"},
        )
    )

    assert result == "https://test.lambchat.com"


def test_forwarded_host_wins_over_rewritten_host_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重写 Host 的代理（proxy_set_header Host $proxy_host / 部分 ingress）下，
    X-Forwarded-Host 优先，避免生成内网地址。"""
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(
        _request(
            "http://127.0.0.1:8000/",
            {"host": "127.0.0.1:8000", "x-forwarded-host": "test.lambchat.com"},
        )
    )

    assert result == "https://test.lambchat.com"


def test_plain_direct_connection_keeps_request_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(_request("http://127.0.0.1:8010/", {"host": "127.0.0.1:8010"}))

    assert result == "http://127.0.0.1:8010"


def test_app_base_url_used_as_fallback_when_host_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com/")

    result = _get_base_url(_request("http://None"))

    assert result == "https://lambchat.com"

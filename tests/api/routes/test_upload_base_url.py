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


def _request(
    base_url: str, headers: dict[str, str] | None = None, url_scheme: str = "http"
) -> SimpleNamespace:
    return SimpleNamespace(
        base_url=base_url,
        headers=headers or {},
        url=SimpleNamespace(scheme=url_scheme),
    )


def test_request_entry_takes_priority_over_app_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com")

    result = _get_base_url(_request("http://internal:8000/", {"host": "test.lambchat.com"}))

    # 无转发头视为直连，scheme 跟随连接（http），入口 host 覆盖 APP_BASE_URL
    assert result == "http://test.lambchat.com"


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


def test_plain_http_lan_direct_connection_keeps_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """局域网/自签部署以 http 直连非环回地址时，不得误判成 https。"""
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(_request("http://192.168.1.10:8000/", {"host": "192.168.1.10:8000"}))

    assert result == "http://192.168.1.10:8000"


def test_direct_https_connection_keeps_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(
        _request(
            "https://192.168.1.10:8000/",
            {"host": "192.168.1.10:8000"},
            url_scheme="https",
        )
    )

    assert result == "https://192.168.1.10:8000"


def test_ipv6_loopback_direct_connection_keeps_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IPv6 环回直连不属于 localhost/127.0.0.1 字面匹配，同样按实际 scheme。"""
    monkeypatch.setattr(settings, "APP_BASE_URL", "")

    result = _get_base_url(_request("http://[::1]:8010/", {"host": "[::1]:8010"}))

    assert result == "http://[::1]:8010"


def test_app_base_url_used_as_fallback_when_host_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com/")

    result = _get_base_url(_request("http://None"))

    assert result == "https://lambchat.com"

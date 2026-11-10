"""伪 URL（裸 IPv6 literal/未闭合方括号）不得击穿产物投递的 URL 解析。

背景 #1220：模型输出的伪 URL 让 urlparse 抛 ValueError: Invalid IPv6 URL，
ArtifactDeliveryMiddleware.aafter_agent 整体失败——agent 已跑完、任务被判死、
产物未投递。与 #1032（分享页 urlsplit 容错）同族，全部解析点按「非目标形态」
语义容错，不向调用方抛异常。
"""

from src.infra.agent.middleware._artifact_delivery_support import (
    _extract_file_urls_from_text,
    _extract_upload_proxy_key,
    _is_auto_deliverable_url,
    _normalize_path,
    _should_skip_auto_artifact,
)

# urlparse 对未闭合方括号/裸 ] 的 netloc 抛 ValueError: Invalid IPv6 URL
_MALFORMED_URLS = [
    "http://[::1:8080/report.pdf",
    "http://::1]/report.pdf",
    "https://[fe80::1/report.csv",
]


def test_extract_upload_proxy_key_tolerates_malformed_ipv6() -> None:
    for url in _MALFORMED_URLS:
        assert _extract_upload_proxy_key(url) is None, url


def test_normalize_path_tolerates_malformed_ipv6() -> None:
    for path in _MALFORMED_URLS:
        normalized = _normalize_path(path)
        assert isinstance(normalized, str) and normalized, path


def test_is_auto_deliverable_url_tolerates_malformed_ipv6() -> None:
    for url in _MALFORMED_URLS:
        assert _is_auto_deliverable_url(url) is False, url


def test_should_skip_auto_artifact_tolerates_malformed_ipv6() -> None:
    for path in _MALFORMED_URLS:
        assert isinstance(_should_skip_auto_artifact(path), bool), path


def test_extract_file_urls_from_text_skips_malformed_ipv6() -> None:
    text = "结果见 http://[::1:8080/report.pdf 与 https://example.com/report.png 两个文件"
    assert _extract_file_urls_from_text(text) == ["https://example.com/report.png"]

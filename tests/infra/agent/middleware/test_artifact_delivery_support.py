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


def test_is_auto_deliverable_url_rejects_webpage_suffixes() -> None:
    """新闻站 CMS 的 .html/.htm 后缀是内容页链接，不是文件产物，不自动投递。

    实况（#DHTBetB3yAbD 分享对话）：日报回复的参考链接区含
    independent.co.uk 的 .html 文章链接，被按扩展名误判为文件，在 run
    尾部投成一张 0 字节的「HTML 文件」卡挂在对话末尾。
    """
    assert (
        _is_auto_deliverable_url(
            "https://www.independent.co.uk/news/world/middle-east/"
            "trump-netanyahu-call-iran-war-shouting-match-b3083649.html"
        )
        is False
    )
    assert _is_auto_deliverable_url("https://example.com/docs/index.htm") is False


def test_extract_file_urls_from_text_skips_webpage_html_links() -> None:
    """参考链接区混有 .html 新闻页时，只提取真正的文件 URL。"""
    text = (
        "参考链接：\n"
        "1. BBC — https://www.bbc.com/news/world-68345121\n"
        "2. Independent — https://www.independent.co.uk/news/world/middle-east/"
        "trump-netanyahu-call-iran-war-shouting-match-b3083649.html\n"
        "3. 报告 — https://cdn.example.com/reports/daily.pdf\n"
    )
    assert _extract_file_urls_from_text(text) == ["https://cdn.example.com/reports/daily.pdf"]

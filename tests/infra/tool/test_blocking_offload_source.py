"""守门：async 工具热路径的重 CPU 提取/编码必须经 run_long_blocking_io 卸载。

web_fetch 的 trafilatura/lxml 正文提取（≤5MB 任意 HTML）、document_parse 的
50MB 级 base64/ZIP 解包、image_analyze 的整图解码校验，都是无上限输入的
纯 CPU 活——内联执行会卡住整个事件循环（协作式调度一阻全阻）。
"""

from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parents[3] / "src" / "infra" / "tool"

_WEB_FETCH = (_TOOL_DIR / "web_fetch_providers.py").read_text(encoding="utf-8")
_DOC_PARSE = (_TOOL_DIR / "document_parse_providers.py").read_text(encoding="utf-8")
_IMAGE_ANALYSIS = (_TOOL_DIR / "image_analysis_tool.py").read_text(encoding="utf-8")


def test_web_fetch_extracts_html_off_event_loop() -> None:
    assert "title, markdown = _extract_wechat(html)" not in _WEB_FETCH
    assert "title, markdown = _extract_markdown(html)" not in _WEB_FETCH
    assert _WEB_FETCH.count("run_long_blocking_io(_extract_wechat, html") == 2
    assert _WEB_FETCH.count("run_long_blocking_io(_extract_markdown, html") == 1


def test_document_parse_encodes_and_unpacks_off_event_loop() -> None:
    # b64 编码只允许出现在同步 helper 内（随卸载进线程），调用处必须走卸载
    assert _DOC_PARSE.count('base64.b64encode(data).decode("ascii")') == 1
    assert _DOC_PARSE.count("run_long_blocking_io(_b64_ascii, data)") == 3
    assert "= extract_mineru_zip(zip_response.content)" not in _DOC_PARSE
    assert "run_long_blocking_io(extract_mineru_zip, zip_response.content)" in _DOC_PARSE
    assert "images = extract_ooxml_media_images(data)" not in _DOC_PARSE
    assert "run_long_blocking_io(extract_ooxml_media_images, data)" in _DOC_PARSE
    assert 'data = base64.b64decode(str(image.get("base64") or ""))' not in _DOC_PARSE
    assert 'run_long_blocking_io(base64.b64decode, str(image.get("base64")' in _DOC_PARSE


def test_image_analysis_validates_data_urls_off_event_loop() -> None:
    assert "_validate_attachment_data_urls(attachments)" not in _IMAGE_ANALYSIS
    assert "run_long_blocking_io(_validate_attachment_data_urls, attachments)" in _IMAGE_ANALYSIS

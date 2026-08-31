"""标题生成语言参数的白名单与规范化测试。"""

from __future__ import annotations

import pytest

from src.api.routes.session import SUPPORTED_LANGUAGES, normalize_title_language


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zh-CN", "zh"),
        ("zh", "zh"),
        ("en-US,en;q=0.9", "en"),
        ("ru", "ru"),
        ("JA", "ja"),
        ("ko-KR", "ko"),
        ("fr", "en"),
        ("", "en"),
    ],
)
def test_normalize_title_language_accepts_all_ui_locales(raw: str, expected: str) -> None:
    assert normalize_title_language(raw) == expected


def test_title_language_whitelist_covers_every_frontend_locale() -> None:
    # 前端 i18n 支持 en/zh/ja/ko/ru 五种语言，标题白名单必须同步覆盖
    assert SUPPORTED_LANGUAGES >= frozenset({"en", "zh", "ja", "ko", "ru"})

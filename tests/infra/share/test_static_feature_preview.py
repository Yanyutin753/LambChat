import json
import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("filename", "route", "docs", "heading"),
    [
        (
            "index.html",
            "/features",
            "/docs/en/",
            "Build, run, and share AI agents that actually finish work",
        ),
        (
            "zh-index.html",
            "/zh/features",
            "/docs/zh/",
            "构建、运行并分享真正能干完活的 AI Agent",
        ),
    ],
)
def test_static_features_keep_crawlable_content_with_responsive_brand_assets(
    filename: str, route: str, docs: str, heading: str
) -> None:
    page = (Path(__file__).parents[3] / "deploy/seo/features" / filename).read_text()

    assert f'<link rel="canonical" href="https://lambchat.com{route}"' in page
    assert f"<h1>{heading}</h1>" in page
    assert 'name="robots" content="index, follow, max-image-preview:large"' in page
    assert f'href="{docs}"' in page
    assert f'href="{docs}getting-started"' in page
    assert 'href="https://github.com/Yanyutin753/LambChat"' in page
    assert 'hreflang="en" href="https://lambchat.com/features"' in page
    assert 'hreflang="zh" href="https://lambchat.com/zh/features"' in page
    structured_data = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert structured_data is not None
    assert json.loads(structured_data.group(1))["@type"] == "SoftwareApplication"
    assert 'src="/images/lamb.webp"' in page
    assert "🐑" not in page
    assert 'src="/images/illustrations/auth-brand-workspace-light.webp"' in page
    assert 'srcset="/images/illustrations/auth-brand-workspace.webp"' in page
    assert 'media="(prefers-color-scheme: dark)"' in page
    assert 'src="/features/hero.webp"' in page
    assert ":focus-visible" in page
    assert "@media (max-width: 767px)" in page
    assert "minmax(0, 1fr)" in page
    assert "overflow-wrap: anywhere" in page
    assert "onclick=" not in page

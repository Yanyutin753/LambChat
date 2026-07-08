from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import main as api_main


class _FakeOwner:
    def __init__(self, username: str) -> None:
        self.username = username

    def model_dump(self) -> dict[str, str]:
        return {"username": self.username}


@pytest.mark.asyncio
async def test_shared_page_route_injects_share_specific_seo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <link rel="canonical" href="https://lambchat.com/" />
    <title>LambChat - AI Agent Platform</title>
    <meta name="description" content="Default description" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="Default og title" />
    <meta property="og:description" content="Default og description" />
    <meta property="og:url" content="https://lambchat.com/" />
    <meta name="twitter:title" content="Default twitter title" />
    <meta name="twitter:description" content="Default twitter description" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    async def _fake_get_shared_content(share_id: str, user=None):
        assert share_id == "ssehSOzUgKnX"
        assert user is None
        return SimpleNamespace(
            session={
                "name": "🤖 创意Agent专利",
                "agent_name": "Search Agent",
                "created_at": "2026-04-29T18:51:10.499000",
            },
            events=[
                {
                    "event_type": "user:message",
                    "data": {"content": "帮我写一个创意agent的训练方法的专利。"},
                },
                {
                    "event_type": "message:chunk",
                    "data": {"content": "技术交底书已完整生成。"},
                },
            ],
            owner=_FakeOwner("clivia.yang"),
        )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main.share, "get_shared_content", _fake_get_shared_content)
    monkeypatch.setattr(api_main.settings, "APP_BASE_URL", "https://lambchat.com")

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/shared/ssehSOzUgKnX")

    assert response.status_code == 200
    assert "<title>🤖 创意Agent专利 - LambChat Shared Session</title>" in response.text
    assert 'rel="canonical" href="https://lambchat.com/shared/ssehSOzUgKnX"' in response.text
    assert 'content="noindex, follow, max-image-preview:large"' in response.text
    assert "Shared session preview" in response.text


@pytest.mark.asyncio
async def test_public_home_route_injects_crawlable_seo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <link rel="canonical" href="https://lambchat.com/" />
    <title>LambChat - AI Agent Platform</title>
    <meta name="description" content="Default description" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="Default og title" />
    <meta property="og:description" content="Default og description" />
    <meta property="og:url" content="https://lambchat.com/" />
    <meta name="twitter:title" content="Default twitter title" />
    <meta name="twitter:description" content="Default twitter description" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main.settings, "APP_BASE_URL", "https://lambchat.com")

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "<h1>LambChat AI Agent Platform</h1>" in response.text
    assert 'content="index, follow, max-image-preview:large"' in response.text
    assert 'rel="canonical" href="https://lambchat.com/"' in response.text


@pytest.mark.asyncio
async def test_public_home_route_reuses_cached_index_html(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    index_file = static_dir / "index.html"
    index_file.write_text("<!doctype html><div id='root'></div>", encoding="utf-8")

    read_count = 0
    original_read_text = type(index_file).read_text

    def _counting_read_text(self, *args, **kwargs):
        nonlocal read_count
        if self == index_file:
            read_count += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(index_file), "read_text", _counting_read_text)
    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main.settings, "APP_BASE_URL", "https://lambchat.com")

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        first = await client.get("/")
        second = await client.get("/")

    assert first.status_code == 200
    assert second.status_code == 200
    assert read_count == 1


def test_index_html_cache_is_bounded(tmp_path: Path) -> None:
    api_main._INDEX_HTML_CACHE.clear()
    previous_limit = api_main.INDEX_HTML_CACHE_MAX_ENTRIES
    api_main.INDEX_HTML_CACHE_MAX_ENTRIES = 2
    try:
        for index in range(3):
            static_dir = tmp_path / f"dist-{index}"
            static_dir.mkdir()
            index_file = static_dir / "index.html"
            index_file.write_text(f"<!doctype html><div>{index}</div>", encoding="utf-8")

            assert api_main._read_index_html(index_file) == f"<!doctype html><div>{index}</div>"

        assert len(api_main._INDEX_HTML_CACHE) == 2
    finally:
        api_main.INDEX_HTML_CACHE_MAX_ENTRIES = previous_limit
        api_main._INDEX_HTML_CACHE.clear()


def test_read_index_html_rejects_oversized_file_before_reading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    index_file = tmp_path / "index.html"
    index_file.write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(api_main, "INDEX_HTML_MAX_BYTES", 8, raising=False)

    def _fail_read_text(self, *args, **kwargs):
        if self == index_file:
            raise AssertionError("oversized index.html should not be read into memory")
        return ""

    monkeypatch.setattr(type(index_file), "read_text", _fail_read_text)
    api_main._INDEX_HTML_CACHE.clear()

    with pytest.raises(ValueError, match="index.html too large"):
        api_main._read_index_html(index_file)

    assert api_main._INDEX_HTML_CACHE == {}


@pytest.mark.asyncio
async def test_auth_spa_routes_are_noindexed_in_initial_html(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <link rel="canonical" href="https://lambchat.com/" />
    <title>LambChat - AI Agent Platform</title>
    <meta name="description" content="Default description" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="Default og title" />
    <meta property="og:description" content="Default og description" />
    <meta property="og:url" content="https://lambchat.com/" />
    <meta name="twitter:title" content="Default twitter title" />
    <meta name="twitter:description" content="Default twitter description" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main.settings, "APP_BASE_URL", "https://lambchat.com")

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/auth/login")

    assert response.status_code == 200
    assert 'content="noindex, follow, max-image-preview:large"' in response.text
    assert 'rel="canonical" href="https://lambchat.com/auth/login"' in response.text


@pytest.mark.asyncio
async def test_image_static_files_include_cache_control(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    images_dir = static_dir / "images"
    images_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    (images_dir / "lamb.webp").write_bytes(b"fake-webp")

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/images/lamb.webp")

    assert response.status_code == 200
    assert response.headers["cache-control"] == (
        "public, max-age=604800, stale-while-revalidate=86400"
    )


@pytest.mark.asyncio
async def test_service_worker_is_served_without_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    (static_dir / "sw.js").write_text(
        "self.__lambchat = true;\n",
        encoding="utf-8",
        newline="\n",
    )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/sw.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.text == "self.__lambchat = true;\n"


@pytest.mark.asyncio
async def test_spa_static_file_metadata_check_runs_in_blocking_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    (static_dir / "sw.js").write_text("self.__lambchat = true;\n", encoding="utf-8")
    blocking_calls: list[str] = []

    async def _fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )
    monkeypatch.setattr(api_main, "run_blocking_io", _fake_run_blocking_io)

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/sw.js")

    assert response.status_code == 200
    assert "_is_existing_file" in blocking_calls


@pytest.mark.asyncio
async def test_offline_page_is_served_without_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    (static_dir / "offline.html").write_text(
        "<!doctype html><title>Offline</title>\n",
        encoding="utf-8",
        newline="\n",
    )

    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )

    app = api_main.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="https://lambchat.com") as client:
        response = await client.get("/offline.html")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<!doctype html><title>Offline</title>\n"

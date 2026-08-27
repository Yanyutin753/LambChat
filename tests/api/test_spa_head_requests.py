from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import main as api_main


def _make_static_dist(tmp_path: Path) -> Path:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        '<!doctype html><html lang="en"><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    return static_dir


def _patch_static_frontend(monkeypatch: pytest.MonkeyPatch, static_dir: Path) -> None:
    monkeypatch.setattr(
        api_main,
        "resolve_frontend_target",
        lambda _project_root, _frontend_dev_url: ("static", static_dir),
    )


@pytest.mark.asyncio
async def test_head_root_serves_spa_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """HEAD / 应返回 200——爬虫与可用性探测工具普遍使用 HEAD 探测首页。"""
    static_dir = _make_static_dist(tmp_path)
    _patch_static_frontend(monkeypatch, static_dir)

    app = api_main.create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.head("/")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_head_spa_deep_link_serves_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """HEAD 任意 SPA 深链也应返回 200 而非 405。"""
    static_dir = _make_static_dist(tmp_path)
    _patch_static_frontend(monkeypatch, static_dir)

    app = api_main.create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.head("/auth/login")
        assert resp.status_code == 200

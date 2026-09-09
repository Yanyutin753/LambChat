"""web_fetch 工具层：参数清洗、上限钳制、结果 JSON 序列化。"""

from __future__ import annotations

import json

import src.infra.tool.web_fetch_tool as wft


async def test_web_fetch_empty_url_short_circuits(monkeypatch) -> None:
    async def never(url, max_chars, **kwargs):  # noqa: ANN001, ANN003
        raise AssertionError("empty url must not reach providers")

    monkeypatch.setattr(wft, "execute_web_fetch", never)
    raw = await wft.web_fetch.ainvoke({"url": "   "})
    data = json.loads(raw)
    assert data == {"success": False, "error": "web_fetch_empty_url"}


async def test_web_fetch_clamps_max_chars(monkeypatch) -> None:
    seen: list[int] = []

    async def fake_execute(url, max_chars, **kwargs):  # noqa: ANN001, ANN003
        seen.append(max_chars)
        return {"success": True, "url": url, "content": "x"}

    monkeypatch.setattr(wft, "execute_web_fetch", fake_execute)

    await wft.web_fetch.ainvoke({"url": "https://example.com/a", "max_chars": 10**9})
    await wft.web_fetch.ainvoke({"url": "https://example.com/b", "max_chars": 1})
    # 上限钳到 262144；下限钳到 256
    assert seen == [wft.MAX_WEB_FETCH_CHARS, 256]


async def test_web_fetch_success_passes_through(monkeypatch) -> None:
    async def fake_execute(url, max_chars, **kwargs):  # noqa: ANN001, ANN003
        return {
            "success": True,
            "url": url,
            "final_url": url,
            "provider": "direct",
            "title": "T",
            "content": "# hello",
            "content_chars": 7,
            "truncated": False,
        }

    monkeypatch.setattr(wft, "execute_web_fetch", fake_execute)
    data = json.loads(await wft.web_fetch.ainvoke({"url": "https://example.com/x"}))
    assert data["success"] is True
    assert data["content"] == "# hello"


async def test_web_fetch_exception_becomes_error_json(monkeypatch) -> None:
    async def boom(url, max_chars, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("network down")

    monkeypatch.setattr(wft, "execute_web_fetch", boom)
    data = json.loads(await wft.web_fetch.ainvoke({"url": "https://example.com/x"}))
    assert data["success"] is False
    assert "web_fetch_failed" in data["error"]

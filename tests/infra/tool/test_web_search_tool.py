"""web_search 系统工具：参数钳制、JSON 返回契约、注册开关。"""

from __future__ import annotations

import json
from typing import Any

import pytest

import src.infra.tool.internal_registry as internal_registry
import src.infra.tool.web_search_tool as web_search_tool
from src.infra.tool.internal_registry import build_internal_tools


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_SEARCH", False)


async def test_web_search_returns_parsed_json_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute(query: str, max_results: int, time_range: str | None) -> dict[str, Any]:
        captured.update(query=query, max_results=max_results, time_range=time_range)
        return {
            "success": True,
            "query": query,
            "provider": "tavily",
            "results": [{"title": "T", "url": "https://t/1", "snippet": "c"}],
            "images": [],
        }

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_execute)

    raw = await web_search_tool.web_search.coroutine(query="hello", max_results=5)

    data = json.loads(raw)
    assert data["success"] is True
    assert data["provider"] == "tavily"
    assert captured == {"query": "hello", "max_results": 5, "time_range": None}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 1), (-3, 1), (99, 10), (5, 5)],
)
async def test_web_search_clamps_max_results(
    monkeypatch: pytest.MonkeyPatch, raw: int, expected: int
) -> None:
    seen: list[int] = []

    async def fake_execute(query: str, max_results: int, time_range: str | None) -> dict[str, Any]:
        seen.append(max_results)
        return {"success": True, "query": query, "results": [], "images": []}

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_execute)

    await web_search_tool.web_search.coroutine(query="q", max_results=raw)

    assert seen == [expected]


async def test_web_search_rejects_empty_query() -> None:
    raw = await web_search_tool.web_search.coroutine(query="   ")

    data = json.loads(raw)
    assert data["success"] is False
    assert data["error"]


async def test_web_search_swallows_provider_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execute(query: str, max_results: int, time_range: str | None) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(web_search_tool, "execute_web_search", fake_execute)

    raw = await web_search_tool.web_search.coroutine(query="q", max_results=5)

    data = json.loads(raw)
    assert data["success"] is False
    assert "boom" in data["error"]


def test_get_web_search_tool_shape() -> None:
    tool = web_search_tool.get_web_search_tool()

    assert tool.name == "web_search"


def test_build_internal_tools_includes_web_search_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_SEARCH", True)
    names = [t.name for t in build_internal_tools()]

    assert "web_search" in names


def test_build_internal_tools_excludes_web_search_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_SEARCH", False)
    names = [t.name for t in build_internal_tools()]

    assert "web_search" not in names

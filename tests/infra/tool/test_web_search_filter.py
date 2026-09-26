"""web_search 结果 System One 预筛（web_search_filter.py）契约测试。"""

from __future__ import annotations

import json

import pytest

from src.infra.tool import web_search_filter
from src.kernel.config import settings


def _configure(monkeypatch, *, mode="off", threshold=0.05):
    monkeypatch.setattr(settings, "WEB_SEARCH_SYSTEMONE_MODE", mode)
    monkeypatch.setattr(settings, "WEB_SEARCH_SYSTEMONE_RELEVANCE_THRESHOLD", threshold)
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "http://von.local")


def _results(n=3):
    return [{"title": f"t{i}", "url": f"https://x/{i}", "snippet": f"s{i}"} for i in range(n)]


def _judge_by_title(values: dict[str, float]):
    async def fake(state, instructions, *, criteria=None, transport=None):
        for key, value in values.items():
            if f"t{key}\n" in state or f"title {key}" in state:
                return value
        return 0.5

    return fake


@pytest.mark.asyncio
async def test_off_mode_returns_unchanged(monkeypatch):
    _configure(monkeypatch, mode="off")

    async def explode(*args, **kwargs):
        raise AssertionError("off 模式不得调用 System One")

    monkeypatch.setattr(web_search_filter, "judge_noul", explode)
    results = _results()
    assert await web_search_filter.filter_web_search_results("q", results) is results


@pytest.mark.asyncio
async def test_filter_mode_drops_junk_but_keeps_best(monkeypatch):
    _configure(monkeypatch, mode="filter", threshold=0.05)
    monkeypatch.setattr(
        web_search_filter, "judge_noul", _judge_by_title({"0": 0.9, "1": 0.001, "2": 0.002})
    )
    kept = await web_search_filter.filter_web_search_results("q", _results(3))
    assert [r["title"] for r in kept] == ["t0"]


@pytest.mark.asyncio
async def test_filter_mode_never_returns_empty(monkeypatch):
    _configure(monkeypatch, mode="filter", threshold=0.05)
    monkeypatch.setattr(
        web_search_filter, "judge_noul", _judge_by_title({"0": 0.001, "1": 0.0005, "2": 0.002})
    )
    kept = await web_search_filter.filter_web_search_results("q", _results(3))
    assert len(kept) == 1  # 全垃圾也保留最高分一条


@pytest.mark.asyncio
async def test_shadow_mode_keeps_all(monkeypatch):
    _configure(monkeypatch, mode="shadow")
    monkeypatch.setattr(
        web_search_filter, "judge_noul", _judge_by_title({"0": 0.9, "1": 0.001, "2": 0.5})
    )
    kept = await web_search_filter.filter_web_search_results("q", _results(3))
    assert len(kept) == 3


@pytest.mark.asyncio
async def test_per_result_failure_fails_open(monkeypatch):
    _configure(monkeypatch, mode="filter", threshold=0.05)

    async def flaky(state, instructions, *, criteria=None, transport=None):
        return None if "t1" in state else 0.9

    monkeypatch.setattr(web_search_filter, "judge_noul", flaky)
    kept = await web_search_filter.filter_web_search_results("q", _results(3))
    assert len(kept) == 3  # 判定失败的条目保留


@pytest.mark.asyncio
async def test_total_failure_returns_original(monkeypatch):
    _configure(monkeypatch, mode="filter")

    async def dead(state, instructions, *, criteria=None, transport=None):
        return None

    monkeypatch.setattr(web_search_filter, "judge_noul", dead)
    results = _results()
    assert await web_search_filter.filter_web_search_results("q", results) is results


@pytest.mark.asyncio
async def test_web_search_tool_end_to_end_filter(monkeypatch):
    """web_search 工具端到端：provider 返回三条，过滤后只剩相关一条。"""
    _configure(monkeypatch, mode="filter")

    async def fake_execute_web_search(query, max_results, time_range):
        return {
            "success": True,
            "query": query,
            "results": _results(3),
        }

    monkeypatch.setattr(
        "src.infra.tool.web_search_tool.execute_web_search", fake_execute_web_search
    )
    monkeypatch.setattr(
        web_search_filter, "judge_noul", _judge_by_title({"0": 0.9, "1": 0.001, "2": 0.002})
    )

    from src.infra.tool.web_search_tool import web_search

    payload = json.loads(await web_search.ainvoke({"query": "测试查询", "max_results": 3}))
    assert payload["success"] is True
    assert [r["title"] for r in payload["results"]] == ["t0"]

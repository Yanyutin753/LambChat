"""写时语义去重 System One 仲裁（dedup_arbiter.py）契约测试。"""

from __future__ import annotations

import pytest

from src.infra.memory import dedup_arbiter
from src.kernel.config import settings


def _configure(monkeypatch, *, mode="off", low=0.75, high=0.92, same=0.8):
    monkeypatch.setattr(settings, "MEMORY_DEDUP_SYSTEMONE_MODE", mode)
    monkeypatch.setattr(settings, "MEMORY_DEDUP_SYSTEMONE_GRAY_LOW", low)
    monkeypatch.setattr(settings, "MEMORY_DEDUP_SYSTEMONE_GRAY_HIGH", high)
    monkeypatch.setattr(settings, "MEMORY_DEDUP_SYSTEMONE_SAME_THRESHOLD", same)
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "http://von.local")


def _fetch(docs):
    async def fetch(user_id):
        return docs

    return fetch


def _doc(memory_id="m1", similarity_to=None, summary="既有记忆", memory_type="fact"):
    # 查询向量 [1,0]；embedding=[s, sqrt(1-s²)] 与其余弦恰为 s
    if similarity_to is None:
        embedding = None
    else:
        embedding = [similarity_to, (max(0.0, 1 - similarity_to**2)) ** 0.5]
    return {
        "memory_id": memory_id,
        "summary": summary,
        "memory_type": memory_type,
        "embedding": embedding,
    }


def _judge_returning(value):
    async def fake(state, instructions, *, criteria=None, transport=None):
        return value

    return fake


QUERY = [1.0, 0.0]


@pytest.mark.asyncio
async def test_off_mode_matches_legacy_threshold_behavior(monkeypatch):
    _configure(monkeypatch, mode="off")

    async def explode(*args, **kwargs):
        raise AssertionError("off 模式不得调用 System One")

    monkeypatch.setattr(dedup_arbiter, "judge_noul", explode)

    doc_low = _doc(similarity_to=0.80)
    result = await dedup_arbiter.resolve_semantic_match(
        _fetch([doc_low]), "u1", QUERY, "新记忆", "fact"
    )
    assert result is None  # 0.80 < 0.88 旧行为：新建

    doc_high = _doc(similarity_to=0.95)
    result = await dedup_arbiter.resolve_semantic_match(
        _fetch([doc_high]), "u1", QUERY, "新记忆", "fact"
    )
    assert result is doc_high  # ≥0.88 旧行为：合并


@pytest.mark.asyncio
async def test_arbitrate_mode_high_band_merges_without_judgment(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")

    async def explode(*args, **kwargs):
        raise AssertionError("高带不得调用 System One")

    monkeypatch.setattr(dedup_arbiter, "judge_noul", explode)
    doc = _doc(similarity_to=0.95)
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "新", "fact")
    assert result is doc


@pytest.mark.asyncio
async def test_arbitrate_mode_gray_zone_same_fact_merges(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")
    monkeypatch.setattr(dedup_arbiter, "judge_noul", _judge_returning(0.9))
    doc = _doc(similarity_to=0.85)  # 0.88 以下：旧行为新建，仲裁判同条
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "改写", "fact")
    assert result is doc


@pytest.mark.asyncio
async def test_arbitrate_mode_gray_zone_different_fact_creates_new(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")
    monkeypatch.setattr(dedup_arbiter, "judge_noul", _judge_returning(0.1))
    doc = _doc(similarity_to=0.90)  # 0.88 以上：旧行为合并，仲裁判不同
    result = await dedup_arbiter.resolve_semantic_match(
        _fetch([doc]), "u1", QUERY, "相关但不同", "fact"
    )
    assert result is None


@pytest.mark.asyncio
async def test_arbitrate_mode_below_gray_low_skips_judgment(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")

    async def explode(*args, **kwargs):
        raise AssertionError("低于灰区下界不得调用 System One")

    monkeypatch.setattr(dedup_arbiter, "judge_noul", explode)
    doc = _doc(similarity_to=0.6)
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "无关", "fact")
    assert result is None


@pytest.mark.asyncio
async def test_arbitrate_failure_falls_back_to_legacy_rule(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")
    monkeypatch.setattr(dedup_arbiter, "judge_noul", _judge_returning(None))
    doc = _doc(similarity_to=0.90)  # ≥0.88：回退旧行为合并
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "新", "fact")
    assert result is doc


@pytest.mark.asyncio
async def test_shadow_mode_keeps_legacy_outcome(monkeypatch):
    _configure(monkeypatch, mode="shadow")
    monkeypatch.setattr(dedup_arbiter, "judge_noul", _judge_returning(0.95))
    doc = _doc(similarity_to=0.85)  # 仲裁说同条，但 shadow 必须按旧规则新建
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "改写", "fact")
    assert result is None


@pytest.mark.asyncio
async def test_unconfigured_systemone_degrades_to_legacy(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "")

    async def explode(*args, **kwargs):
        raise AssertionError("未配置不得调用 System One")

    monkeypatch.setattr(dedup_arbiter, "judge_noul", explode)
    doc = _doc(similarity_to=0.90)
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "新", "fact")
    assert result is doc


@pytest.mark.asyncio
async def test_different_memory_type_never_matches(monkeypatch):
    _configure(monkeypatch, mode="arbitrate")
    doc = _doc(similarity_to=0.95, memory_type="rule")
    result = await dedup_arbiter.resolve_semantic_match(_fetch([doc]), "u1", QUERY, "新", "fact")
    assert result is None

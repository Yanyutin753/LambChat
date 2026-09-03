"""垃圾/重复记忆清理脚本的通用契约（scripts/cleanup_junk_memories.py）。

不写死任何语言/领域特征：重复判定走可注入的语义相似度（生产用 embedding
余弦，缺失退化为摘要 2-gram Jaccard），durable 判定走与写入端同一套 rubric
的 LLM 单行 KEEP/JUNK；解析失败保守 KEEP（清理删数据，宁漏删不误删）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from scripts.cleanup_junk_memories import (  # noqa: E402
    DURABILITY_JUDGE_PROMPT,
    apply_cleanup,
    confirm_apply,
    cosine_similarity,
    find_duplicate_memory_ids,
    judge_memory_durability,
    parse_judge_reply,
    plan_cleanup,
    render_report,
)


def _doc(memory_id: str, summary: str, updated_at: str = "2026-04-27", user_id: str = "u1", **extra):
    return {
        "memory_id": memory_id,
        "user_id": user_id,
        "title": summary[:10],
        "summary": summary,
        "source": "manual",
        "updated_at": updated_at,
        **extra,
    }


# ---------------------------------------------------------------------------
# 语义去重（无 embedding：摘要 2-gram Jaccard，近重复高阈值 0.9）
# ---------------------------------------------------------------------------


def test_near_identical_summaries_flag_older_copies():
    docs = [
        _doc("older", "用户强调研究中控制变量的必要性，关注研究设计的严谨性", updated_at="2026-04-25T16:44:00Z"),
        _doc("newer", "用户强调研究中控制变量的必要性，关注研究设计的严谨性", updated_at="2026-04-25T16:50:00Z"),
    ]
    assert find_duplicate_memory_ids(docs) == ["older"]


def test_embedding_duplicates_use_cosine_threshold():
    vec = [1.0, 0.0]
    near = [0.99, 0.141]  # 与 vec 余弦 ≈ 0.99
    far = [0.0, 1.0]
    assert cosine_similarity(vec, near) > 0.8
    assert cosine_similarity(vec, far) == 0.0

    docs = [
        _doc("old-dup", "s", updated_at="2026-04-01T00:00:00Z", embedding=near),
        _doc("kept", "t", updated_at="2026-05-01T00:00:00Z", embedding=vec),
        _doc("unrelated", "u", updated_at="2026-03-01T00:00:00Z", embedding=far),
    ]
    assert find_duplicate_memory_ids(docs) == ["old-dup"]


def test_cross_user_memories_never_compared():
    docs = [
        _doc("a", "完全相同的摘要内容一句不差", updated_at="2026-04-01T00:00:00Z", user_id="u1"),
        _doc("b", "完全相同的摘要内容一句不差", updated_at="2026-04-02T00:00:00Z", user_id="u2"),
    ]
    assert find_duplicate_memory_ids(docs) == []


def test_distinct_summaries_not_flagged():
    docs = [
        _doc("a", "月饼合同税率核实：内地13%/小规模1%，香港免征，新加坡GST9%"),
        _doc("b", "卤蛋漏液系包材质量问题，异常批次封存，9/2起发正常批次"),
        _doc("c", "茉莉绿茶3窨120元/kg合理；3窨用花量应≥茶坯1.8倍"),
    ]
    assert find_duplicate_memory_ids(docs) == []


# ---------------------------------------------------------------------------
# durable 判定（LLM rubric，与写入端 Phase 1 同一套最小信号门控）
# ---------------------------------------------------------------------------


def test_judge_prompt_reuses_minimum_signal_rubric():
    assert "durable, reusable fact" in DURABILITY_JUDGE_PROMPT
    assert "business facts" in DURABILITY_JUDGE_PROMPT
    assert "JUNK" in DURABILITY_JUDGE_PROMPT and "KEEP" in DURABILITY_JUDGE_PROMPT


def test_parse_judge_reply_variants():
    assert parse_judge_reply("KEEP - supplier prices are durable") == (
        True,
        "KEEP - supplier prices are durable",
    )
    assert parse_judge_reply("JUNK - describes only message form") == (
        False,
        "JUNK - describes only message form",
    )
    keep, reason = parse_judge_reply("完全无法解析的回复")
    assert keep is True  # 解析失败保守 KEEP


@pytest.mark.asyncio
async def test_judge_memory_durability_flags_junk():
    class FakeModel:
        async def ainvoke(self, messages):
            class R:
                content = "JUNK - only describes what the user sent, no usable fact"

            return R()

    verdict = await judge_memory_durability(FakeModel(), _doc("m1", "用户发送单字符A"))
    assert verdict["keep"] is False
    assert "JUNK" in verdict["reason"]


@pytest.mark.asyncio
async def test_judge_memory_durability_keeps_business_facts():
    class FakeModel:
        async def ainvoke(self, messages):
            class R:
                content = "KEEP - states supplier names and prices"

            return R()

    verdict = await judge_memory_durability(
        FakeModel(), _doc("m2", "皮蛋丁现用九只鸭15/旭日16元/kg")
    )
    assert verdict["keep"] is True


@pytest.mark.asyncio
async def test_judge_memory_durability_error_keeps_conservatively():
    class FakeModel:
        async def ainvoke(self, messages):
            raise RuntimeError("llm down")

    verdict = await judge_memory_durability(FakeModel(), _doc("m3", "任何内容"))
    assert verdict["keep"] is True
    assert "error" in verdict["reason"]


@pytest.mark.asyncio
async def test_plan_cleanup_skips_llm_by_default(monkeypatch):
    class FakeCursor:
        async def to_list(self, *, length):
            return [_doc("m1", "durable fact")]

    class FakeCollection:
        def find(self, query, projection):
            return FakeCursor()

    async def unexpected_model_init():
        raise AssertionError("default cleanup must not initialize an LLM")

    monkeypatch.setattr(
        "scripts.cleanup_junk_memories._get_judge_model",
        unexpected_model_init,
    )

    plan = await plan_cleanup(FakeCollection())

    assert plan["judgments"] == []


# ---------------------------------------------------------------------------
# 阈值对称性：混合 embedding 对一律走 Jaccard 高阈值（0.9），不得用 0.8 误删
# ---------------------------------------------------------------------------


def test_mixed_embedding_pair_uses_word_threshold():
    summary = "卤蛋供应商现用旭日16元/kg，异常批次已封存"
    # Jaccard 落在 (0.8, 0.9)：只有按「成对是否都有 embedding」选档才不会被删
    tweaked = "卤蛋供应商现用旭日16元/kg，异常批次已封存，待复核"

    from scripts.cleanup_junk_memories import word_similarity

    sim = word_similarity(summary, tweaked)
    assert 0.8 < sim < 0.9, f"fixture 相似度需落在 (0.8, 0.9)，实际 {sim}"

    # 候选有 embedding、保留的最新一条没有 → 实际度量是 Jaccard，必须用 0.9 档
    docs = [
        _doc("kept", summary, updated_at="2026-05-02T00:00:00Z"),
        _doc("cand", tweaked, updated_at="2026-05-01T00:00:00Z", embedding=[0.1, 0.9]),
    ]
    assert find_duplicate_memory_ids(docs) == []

    # 反向组合同理
    docs_rev = [
        _doc("kept", summary, updated_at="2026-05-02T00:00:00Z", embedding=[0.1, 0.9]),
        _doc("cand", tweaked, updated_at="2026-05-01T00:00:00Z"),
    ]
    assert find_duplicate_memory_ids(docs_rev) == []


# ---------------------------------------------------------------------------
# apply 链路：先删 Mongo（事实源），再清外部内容，最后删向量索引
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_cleanup_removes_external_content_in_order(monkeypatch):
    events: list[str] = []

    class FakeResult:
        deleted_count = 2

    class FakeCollection:
        async def delete_many(self, query):
            events.append(f"mongo:{sorted(query['memory_id']['$in'])}")
            return FakeResult()

    async def fake_delete_content(backend, user_id, key):
        events.append(f"content:{user_id}:{key}")

    async def fake_index_delete(user_id, memory_id):
        events.append(f"qdrant:{user_id}:{memory_id}")
        return True

    monkeypatch.setattr(
        "src.infra.memory.client.native.content.delete_memory_content",
        fake_delete_content,
    )
    monkeypatch.setattr(
        "src.infra.memory.client.native.vector_store.index_delete",
        fake_index_delete,
    )

    plan = {
        "duplicates": [{"memory_id": "m1"}, {"memory_id": "m2"}],
        "junk_ids": [],
        "docs_by_id": {
            "m1": _doc(
                "m1",
                "外部存储的长记忆正文",
                user_id="u1",
                content_storage_mode="store",
                content_store_key="memory:m1",
            ),
            "m2": _doc("m2", "inline 短记忆", user_id="u1"),
        },
    }

    result = await apply_cleanup(FakeCollection(), plan)

    assert result == {
        "deleted": 2,
        "qdrant_deleted": 2,
        "content_deleted": 1,
        "content_delete_failed": 0,
    }
    # 顺序：Mongo（事实源）先行，外部内容随后，向量索引最后；inline 记忆不碰外部存储
    assert events == [
        "mongo:['m1', 'm2']",
        "content:u1:memory:m1",
        "qdrant:u1:m1",
        "qdrant:u1:m2",
    ]


@pytest.mark.asyncio
async def test_apply_cleanup_survives_content_store_failure(monkeypatch):
    class FakeResult:
        deleted_count = 1

    class FakeCollection:
        async def delete_many(self, query):
            return FakeResult()

    async def failing_delete_content(backend, user_id, key):
        raise RuntimeError("store down")

    async def fake_index_delete(user_id, memory_id):
        return True

    monkeypatch.setattr(
        "src.infra.memory.client.native.content.delete_memory_content",
        failing_delete_content,
    )
    monkeypatch.setattr(
        "src.infra.memory.client.native.vector_store.index_delete",
        fake_index_delete,
    )

    plan = {
        "duplicates": [{"memory_id": "m1"}],
        "junk_ids": [],
        "docs_by_id": {
            "m1": _doc(
                "m1",
                "外部存储",
                user_id="u1",
                content_storage_mode="store",
                content_store_key="memory:m1",
            )
        },
    }

    result = await apply_cleanup(FakeCollection(), plan)
    # 单条外部内容删除失败不中断批次：统计失败数供人工跟进
    assert result["deleted"] == 1
    assert result["content_deleted"] == 0
    assert result["content_delete_failed"] == 1


# ---------------------------------------------------------------------------
# apply 确认门：批量删除必须显式确认
# ---------------------------------------------------------------------------


def _deletion_plan() -> dict:
    return {
        "total": 3,
        "duplicates": [{"memory_id": "m1"}, {"memory_id": "m2"}],
        "judgments": [],
        "junk_ids": ["m3"],
        "docs_by_id": {},
    }


def test_confirm_apply_yes_flag_bypasses_prompt(monkeypatch):
    def unexpected_input(prompt=""):
        raise AssertionError("--yes must skip the interactive prompt")

    monkeypatch.setattr("builtins.input", unexpected_input)
    assert confirm_apply(_deletion_plan(), assume_yes=True) is True


def test_confirm_apply_requires_typing_delete(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "DELETE")
    assert confirm_apply(_deletion_plan()) is True

    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    assert confirm_apply(_deletion_plan()) is False


def test_confirm_apply_aborts_on_eof(monkeypatch):
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert confirm_apply(_deletion_plan()) is False


# ---------------------------------------------------------------------------
# 报告脱敏：不输出记忆标题/LLM 理由等用户内容
# ---------------------------------------------------------------------------


def test_render_report_never_prints_memory_content():
    plan = {
        "total": 2,
        "duplicates": [{"memory_id": "m1", "title": "旭日皮蛋报价机密标题"}],
        "judgments": [
            {"memory_id": "m2", "keep": False, "reason": "JUNK - 复述了用户隐私内容XYZ"}
        ],
        "junk_ids": ["m2"],
        "docs_by_id": {},
    }

    report = render_report(plan)

    assert "旭日皮蛋报价机密标题" not in report
    assert "复述了用户隐私内容XYZ" not in report
    assert "[dup] m1" in report
    assert "[junk] m2" in report
    assert "near-duplicates to delete (1)" in report
    assert "JUNK (1) / judged (1)" in report


def test_duplicate_detection_orders_mixed_datetime_and_string_updated_at():
    """datetime 与 ISO 字符串混存时，str() 排序会因 'T' > ' ' 误判新旧。"""
    from datetime import datetime, timezone

    summary = "完全相同的近重复摘要内容一句不差"
    docs = [
        # datetime（str() 形如 "2026-05-02 09:00:00+00:00"，会排在 ISO 字符串之后）
        _doc("newer", summary, updated_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc)),
        # ISO 字符串（实际更早，但 str() 排序更晚）
        _doc("older", summary, updated_at="2026-05-01T23:00:00Z"),
    ]

    assert find_duplicate_memory_ids(docs) == ["older"]

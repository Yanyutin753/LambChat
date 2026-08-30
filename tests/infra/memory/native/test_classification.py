import pytest

from src.infra.memory.client.native.classification import (
    find_semantic_memory_match,
    is_manual_memory_worthy,
    looks_like_code_or_path,
)

# 生产实际被误拒的记忆内容（run_20260829_2bd6df77，memory_retain 两次均被拒）
_DURABLE_FACT_WITH_FILENAME = (
    "用户申请加入中国共产党：2026-08-29起多次请AI撰写约3000字入党申请书Word文档"
    "（作手写誊写底稿），已生成含标点3018字的通用版（不限定学生/职工身份），"
    "生成脚本gen_docx.py与底稿txt保留在工作区可复用。"
    "落款为占位符（XXX / XXXX年XX月XX日），身份场景仍未确认。"
)


def test_durable_fact_mentioning_single_filename_is_worthy():
    assert is_manual_memory_worthy(_DURABLE_FACT_WITH_FILENAME)


def test_single_filename_mention_is_not_code_or_path():
    assert not looks_like_code_or_path("生成脚本gen_docx.py与底稿txt保留在工作区可复用")


def test_single_path_fragment_mention_is_not_code_or_path():
    assert not looks_like_code_or_path("生成的脚本保留在 src/ 目录下供后续复用")


def test_single_tsx_mention_is_counted_once_not_double():
    assert not looks_like_code_or_path("前端入口组件在 App.tsx 里，后续要改样式")


def test_code_snippet_is_rejected():
    assert looks_like_code_or_path("import os\n\n\ndef main():\n    print('hi')")
    assert not is_manual_memory_worthy("import os\n\n\ndef main():\n    print('hi')")


def test_traceback_dump_is_rejected():
    assert looks_like_code_or_path("Traceback (most recent call last): File ...")
    assert not is_manual_memory_worthy("Traceback (most recent call last): File ...")


def test_multiple_file_references_are_rejected():
    assert looks_like_code_or_path("脚本 gen_docx.py 和构建脚本 build.js 都要重跑")
    assert not is_manual_memory_worthy("脚本 gen_docx.py 和构建脚本 build.js 都要重跑")


def test_path_with_multiple_segments_is_rejected():
    assert looks_like_code_or_path("部署脚本在 deploy/k8s/scripts/ 目录下的 run.sh")


@pytest.mark.asyncio
async def test_find_semantic_memory_match_returns_best_candidate_above_threshold():
    candidates = [
        {"memory_id": "m1", "memory_type": "user", "embedding": [1.0, 0.0]},
        {"memory_id": "m2", "memory_type": "user", "embedding": [0.0, 1.0]},
    ]

    async def fake_fetch(_user_id):
        return candidates

    match = await find_semantic_memory_match(
        fetch_candidates=fake_fetch,
        user_id="u1",
        query_embedding=[0.9, 0.44],
        memory_type="user",
    )

    assert match is not None
    assert match["memory_id"] == "m1"


@pytest.mark.asyncio
async def test_find_semantic_memory_match_returns_none_below_threshold():
    candidates = [
        {"memory_id": "m1", "memory_type": "user", "embedding": [1.0, 0.0]},
    ]

    async def fake_fetch(_user_id):
        return candidates

    match = await find_semantic_memory_match(
        fetch_candidates=fake_fetch,
        user_id="u1",
        query_embedding=[0.0, 1.0],
        memory_type="user",
    )

    assert match is None


@pytest.mark.asyncio
async def test_find_semantic_memory_match_skips_other_memory_types():
    candidates = [
        {"memory_id": "m1", "memory_type": "project", "embedding": [1.0, 0.0]},
    ]

    async def fake_fetch(_user_id):
        return candidates

    match = await find_semantic_memory_match(
        fetch_candidates=fake_fetch,
        user_id="u1",
        query_embedding=[1.0, 0.0],
        memory_type="user",
    )

    assert match is None

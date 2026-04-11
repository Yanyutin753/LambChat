from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.classification import (
    extract_tags,
    find_existing_memory_match,
    is_manual_memory_worthy,
)
from src.infra.memory.client.native.summaries import build_summary


def test_build_summary_truncates_cjk_content_cleanly():
    content = (
        "这是一个很长的中文句子，用来验证摘要生成逻辑在中文场景下也能正确工作，而且不会依赖空格。"
    )

    summary = build_summary(content, max_len=12)

    assert summary.endswith("...")
    assert len(summary) <= 15


def test_extract_tags_handles_english_and_cjk_content():
    english_tags = extract_tags("User prefers raw SQL and PostgreSQL for analytics workloads.")
    cjk_tags = extract_tags("用户偏好原始SQL，并且项目依赖知识图谱查询能力。")

    assert "postgresql" in english_tags
    assert any(len(tag) >= 2 for tag in cjk_tags)


def test_is_manual_memory_worthy_rejects_transient_code_like_content():
    assert not is_manual_memory_worthy("让我先看看 src/app.py 里这个 traceback error")
    assert is_manual_memory_worthy("The user prefers raw SQL for all analytics queries.")


@pytest.mark.asyncio
async def test_find_existing_memory_match_returns_best_existing_match():
    now = datetime.now(timezone.utc)
    candidates = [
        {
            "memory_id": "m1",
            "memory_type": "user",
            "summary": "Prefers raw SQL for analytics work.",
            "updated_at": now,
        },
        {
            "memory_id": "m2",
            "memory_type": "project",
            "summary": "Current release is blocked on migration work.",
            "updated_at": now,
        },
    ]

    async def fake_fetch(*_args, **_kwargs):
        return candidates

    match = await find_existing_memory_match(
        fetch_recent=fake_fetch,
        user_id="u1",
        summary="User prefers raw SQL for analytics queries.",
        memory_type="user",
    )

    assert match is not None
    assert match["memory_id"] == "m1"


@pytest.mark.asyncio
async def test_retain_updates_existing_memory_and_refreshes_embedding():
    now = datetime.now(timezone.utc)
    seen: dict[str, object] = {}

    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, length):
            return self._docs[:length]

    class FakeCollection:
        def find(self, *_args, **_kwargs):
            return FakeCursor(
                [
                    {
                        "memory_id": "m1",
                        "memory_type": "user",
                        "summary": "Prefers raw SQL for analytics work.",
                        "updated_at": now,
                    }
                ]
            )

        async def find_one(self, *_args, **_kwargs):
            return {
                "content_storage_mode": "inline",
                "content_store_key": None,
            }

        async def update_one(self, query, payload):
            seen["query"] = query
            seen["payload"] = payload

    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_invalidate(_user_id):
        return None

    async def fake_embed(text: str):
        return [float(len(text))]

    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]
    backend._maybe_embed = fake_embed  # type: ignore[method-assign]

    result = await backend.retain(
        "u1",
        "The user now prefers DuckDB for local analytics workloads.",
        context="user_identity",
        title="DuckDB preference",
        summary="Prefers raw SQL for analytics work.",
    )

    assert result["success"] is True
    assert result["updated_existing"] is True
    assert seen["query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["payload"]["$set"]["embedding"] == [58.0]

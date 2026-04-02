from datetime import datetime, timezone

from src.infra.memory.client.native.indexing import choose_index_memories


def test_choose_index_memories_stays_capped_and_prefers_stable_items():
    docs = [
        {
            "memory_id": "m1",
            "source": "manual",
            "access_count": 5,
            "updated_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "summary": "Stable preference",
        },
        {
            "memory_id": "m2",
            "source": "auto_retained",
            "access_count": 0,
            "updated_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "summary": "Very recent but low-value",
        },
        {
            "memory_id": "m3",
            "source": "manual",
            "access_count": 3,
            "updated_at": datetime(2026, 3, 30, tzinfo=timezone.utc),
            "summary": "Another useful preference",
        },
    ]

    chosen = choose_index_memories(
        docs,
        per_type_limit=2,
        now=datetime(2026, 4, 2, tzinfo=timezone.utc),
        staleness_days=30,
    )

    assert [doc["memory_id"] for doc in chosen] == ["m1", "m3"]

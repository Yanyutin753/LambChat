"""A changed body without an embedding must not retain an old vector."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.memory.client.native import vector_store


async def test_missing_replacement_embedding_removes_old_vector(monkeypatch):
    index = SimpleNamespace(upsert=AsyncMock(), delete=AsyncMock(return_value=True))
    monkeypatch.setattr(vector_store, "get_vector_index", AsyncMock(return_value=index))

    result = await vector_store.index_write_through(
        user_id="owner",
        memory_id="memory-1",
        embedding=None,
        memory_type="user",
        context="user",
        updated_at_ts=1,
    )

    assert result is True
    index.delete.assert_awaited_once_with(user_id="owner", memory_id="memory-1")
    index.upsert.assert_not_awaited()

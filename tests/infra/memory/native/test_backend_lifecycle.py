import pytest

from src.infra.memory.client.native.backend import NativeMemoryBackend


@pytest.mark.asyncio
async def test_delete_removes_store_payload_for_long_memory():
    seen: dict[str, object] = {}

    class FakeCollection:
        async def find_one(self, query, _projection=None):
            seen["find_query"] = query
            return {
                "user_id": "u1",
                "memory_id": "m1",
                "content_storage_mode": "store",
                "content_store_key": "memory:m1",
            }

        async def delete_one(self, query):
            seen["delete_query"] = query

            class Result:
                deleted_count = 1

            return Result()

    class FakeStore:
        async def aput(self, namespace, key, value):
            seen["store_delete"] = {"namespace": namespace, "key": key, "value": value}

    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()
    backend._store = FakeStore()

    async def fake_invalidate(_user_id):
        seen["invalidated"] = True

    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]

    result = await backend.delete("u1", "m1")

    assert result["success"] is True
    assert seen["find_query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["delete_query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["store_delete"] == {
        "namespace": ("memories", "u1", "content"),
        "key": "memory:m1",
        "value": None,
    }
    assert seen["invalidated"] is True

import pytest

from src.infra.memory.client.native.consolidation import consolidate_memories


@pytest.mark.asyncio
async def test_consolidation_skips_when_lock_service_is_unavailable():
    called = {"do": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 1}

    async def lock_unavailable(*_args, **_kwargs):
        return "unavailable"

    async def release(*_args, **_kwargs):
        return None

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_unavailable,
        release_lock=release,
    )

    assert result["skipped"] is True
    assert result["reason"] == "lock_unavailable"
    assert called["do"] is False


@pytest.mark.asyncio
async def test_consolidation_skips_when_lock_is_not_acquired():
    called = {"do": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 1}

    async def lock_not_acquired(*_args, **_kwargs):
        return "not_acquired"

    async def release(*_args, **_kwargs):
        return None

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_not_acquired,
        release_lock=release,
    )

    assert result["skipped"] is True
    assert result["reason"] == "lock_not_acquired"
    assert called["do"] is False


@pytest.mark.asyncio
async def test_consolidation_runs_only_when_lock_is_acquired():
    called = {"do": False, "release": False}

    class DummyBackend:
        async def _do_consolidate(self, _user_id):
            called["do"] = True
            return {"merged": 2, "pruned": 1}

    async def lock_acquired(*_args, **_kwargs):
        return "acquired"

    async def release(*_args, **_kwargs):
        called["release"] = True

    result = await consolidate_memories(
        DummyBackend(),
        "u1",
        acquire_lock=lock_acquired,
        release_lock=release,
    )

    assert result["merged"] == 2
    assert called["do"] is True
    assert called["release"] is True

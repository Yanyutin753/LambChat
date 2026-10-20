"""Real Redis fencing for the automatic vector-index completion marker."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from scripts.e2e_conversation_schedules import free_port, stop
from src.infra.memory.client.native import vector_store as vs

pytestmark = pytest.mark.skipif(
    os.environ.get("LAMBCHAT_MEMORY_REDIS_TEST") != "1", reason="Opt-in isolated real Redis"
)


@pytest.fixture
async def isolated_redis():
    executable = shutil.which("redis-server") or str(
        Path.home() / ".local/opt/redis/bin/redis-server"
    )
    port = free_port()
    server = subprocess.Popen(
        [
            executable,
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Redis(host="127.0.0.1", port=port, decode_responses=True)
    try:
        for _ in range(50):
            assert server.poll() is None
            try:
                await client.ping()
                break
            except ConnectionError:
                await asyncio.sleep(0.02)
        else:
            raise AssertionError("Isolated Redis did not start")
        yield client
    finally:
        await client.aclose()
        stop(server)


@pytest.mark.parametrize("outcome", ["success", "skipped", "expired", "taken_over", "failure"])
async def test_only_completed_current_backfill_publishes_done(monkeypatch, isolated_redis, outcome):
    rc = isolated_redis
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: rc)
    monkeypatch.setattr(
        "src.infra.memory.tools._get_backend",
        AsyncMock(return_value=SimpleNamespace(_collection=object())),
    )
    monkeypatch.setattr(vs, "_BACKFILL_LOCK_TTL", 1)

    async def backfill(collection):
        if outcome in {"expired", "taken_over"}:
            await asyncio.sleep(1.1)
            assert await rc.get(vs._BACKFILL_LOCK_KEY) is None
            if outcome == "taken_over":
                assert await rc.set(vs._BACKFILL_LOCK_KEY, "new-owner", nx=True, ex=10)
        if outcome == "failure":
            raise OSError("synthetic index outage")
        return {"skipped": True} if outcome == "skipped" else {"upserted": 7}

    monkeypatch.setattr(vs, "backfill_from_mongo", backfill)
    await vs._run_backfill_once()
    assert await rc.get(vs._BACKFILL_DONE_KEY) == ("1" if outcome == "success" else None)
    assert await rc.get(vs._BACKFILL_LOCK_KEY) == ("new-owner" if outcome == "taken_over" else None)

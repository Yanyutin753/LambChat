"""Real process death and competing workers; local fake delivery, no vendor calls.

MongoDB collections and the Redis Unix socket are exclusive to each test. Lease
expiry is accelerated only in those isolated resources after the worker is dead.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infra.channel.inbox import ChannelInbox
from src.infra.channel.inbox_worker import InboxWorker, current_delivery
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now

MESSAGE = {
    "message_id": "provider-message",
    "chat_id": "chat",
    "sender_id": "sender",
    "content": "hello",
}
DATABASE = "lambchat_channel_tests"


@pytest_asyncio.fixture
async def process_resources(tmp_path, monkeypatch):
    binary = shutil.which("redis-server")
    if not binary:
        pytest.skip("redis-server unavailable for isolated process recovery integration")
    mongo = AsyncMongoClient(build_mongo_connection_string(), serverSelectionTimeoutMS=1000)
    try:
        await mongo.admin.command("ping")
    except Exception:
        await mongo.close()
        pytest.skip("MongoDB unavailable for isolated process recovery integration")
    name = "process_" + uuid.uuid4().hex
    collection = mongo[DATABASE][name]
    audit = mongo[DATABASE][name + "_audit"]
    socket = str(tmp_path / "redis.sock")
    server = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    redis = Redis(unix_socket_path=socket, decode_responses=True)
    children = []
    try:
        async with asyncio.timeout(5):
            while True:
                try:
                    await redis.ping()
                    break
                except RedisConnectionError:
                    await asyncio.sleep(0.01)
        monkeypatch.setattr("src.infra.channel.chat_lease.get_redis_client", lambda: redis)
        yield SimpleNamespace(
            collection=collection,
            audit=audit,
            redis=redis,
            socket=socket,
            name=name,
            children=children,
            tmp_path=tmp_path,
        )
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            await asyncio.to_thread(child.wait, timeout=5)
        await collection.drop()
        await audit.drop()
        await mongo.close()
        await redis.aclose()
        server.terminate()
        await asyncio.to_thread(server.wait, timeout=5)


def spawn_child(resources, mode, suffix):
    ready = resources.tmp_path / (suffix + ".ready")
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            resources.name,
            resources.socket,
            str(ready),
            mode,
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    resources.children.append(child)
    return child, ready


async def wait_ready(child, ready):
    async with asyncio.timeout(20):
        while not ready.exists():
            assert child.poll() is None, "isolated worker exited before readiness"
            await asyncio.sleep(0.02)


async def deliver_to_local_ledger(message, audit):
    """Simulate persisted agent run selection and a successful vendor response."""
    context = current_delivery.get()
    assert context is not None
    run_id = context.checkpoint.get("run_id")
    if not run_id:
        run_id = uuid.uuid4().hex
        await audit.insert_one({"_id": run_id, "kind": "run"})
        await context.save(run_id=run_id, session_id="existing-session")
    await audit.insert_one({"kind": "delivery", "run_id": run_id, "content": message["content"]})


async def test_hard_process_death_recovers_checkpoint_and_completes_once(process_resources):
    resources = process_resources
    child, ready = spawn_child(resources, "crash", "first")
    await wait_ready(child, ready)
    before = await resources.collection.find_one({"state": "pending"})
    assert before is not None
    saved_run = before["checkpoint"]["run_id"]
    assert before["owner"]
    child.kill()  # SIGKILL: no cancellation, finally blocks, or graceful lease release.
    assert await asyncio.to_thread(child.wait, timeout=5) != 0
    assert await resources.audit.count_documents({"kind": "delivery"}) == 0

    inbox = ChannelInbox("weixin", "test-user", "test-instance", collection=resources.collection)

    async def handler(message):
        await deliver_to_local_ledger(message, resources.audit)

    restarted = InboxWorker(inbox, handler)
    assert not await inbox.pending()  # The dead process still owns unexpired work.
    await resources.collection.update_one(
        {"_id": before["_id"]}, {"$set": {"lease_until": utc_now() - timedelta(seconds=1)}}
    )
    chat_key = restarted._chat_key(MESSAGE)
    assert await resources.redis.exists(chat_key)
    await resources.redis.delete(chat_key)
    assert await asyncio.wait_for(restarted.drain(), 5)
    after = await resources.collection.find_one({"_id": before["_id"]})
    assert after["state"] == "done"
    assert "message" not in after and "checkpoint" not in after
    assert await resources.audit.count_documents({"kind": "run"}) == 1
    delivery = await resources.audit.find_one({"kind": "delivery"})
    assert delivery["run_id"] == saved_run
    assert await resources.audit.count_documents({"kind": "delivery"}) == 1

    assert await restarted.accept(MESSAGE)  # Provider redelivery after a restart.
    assert await restarted.drain()
    assert await resources.collection.count_documents({}) == 1
    assert await resources.audit.count_documents({"kind": "delivery"}) == 1
    await restarted.stop()


async def test_two_real_processes_accepting_same_message_execute_once(process_resources):
    resources = process_resources
    first, first_ready = spawn_child(resources, "race", "first")
    second, second_ready = spawn_child(resources, "race", "second")
    await asyncio.gather(wait_ready(first, first_ready), wait_ready(second, second_ready))
    (resources.tmp_path / "go").touch()
    results = await asyncio.gather(
        asyncio.to_thread(first.wait, timeout=20), asyncio.to_thread(second.wait, timeout=20)
    )
    assert results == [0, 0], "competing isolated workers failed"
    assert await resources.collection.count_documents({"state": "done"}) == 1
    assert await resources.collection.count_documents({}) == 1
    assert await resources.audit.count_documents({"kind": "started"}) == 1
    assert await resources.audit.count_documents({"kind": "run"}) == 1
    assert await resources.audit.count_documents({"kind": "delivery"}) == 1


async def child_main(name, socket, ready_path, mode):
    from src.infra.channel import chat_lease

    mongo = AsyncMongoClient(build_mongo_connection_string(), serverSelectionTimeoutMS=1000)
    collection = mongo[DATABASE][name]
    audit = mongo[DATABASE][name + "_audit"]
    redis = Redis(unix_socket_path=socket, decode_responses=True)
    chat_lease.get_redis_client = lambda: redis
    ready = Path(ready_path)
    inbox = ChannelInbox("weixin", "test-user", "test-instance", collection=collection)

    async def handler(message):
        if mode == "crash":
            context = current_delivery.get()
            assert context is not None
            run_id = uuid.uuid4().hex
            await audit.insert_one({"_id": run_id, "kind": "run"})
            await context.save(run_id=run_id, session_id="existing-session")
            ready.touch()
            await asyncio.Event().wait()
        else:
            await audit.insert_one({"kind": "started"})
            await asyncio.sleep(0.15)
            await deliver_to_local_ledger(message, audit)

    worker = InboxWorker(inbox, handler)
    assert await worker.accept(MESSAGE)
    if mode == "race":
        ready.touch()
        async with asyncio.timeout(15):
            while not (ready.parent / "go").exists():
                await asyncio.sleep(0.02)
    task = asyncio.create_task(worker.run())
    try:
        async with asyncio.timeout(30):
            while not await collection.find_one({"state": "done"}):
                await asyncio.sleep(0.02)
    finally:
        await worker.stop()
        await task
        await redis.aclose()
        await mongo.close()


if __name__ == "__main__":
    assert sys.argv[1] == "--child"
    asyncio.run(child_main(*sys.argv[2:]))

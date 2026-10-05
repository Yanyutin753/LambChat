"""Persistent acceptance and owner fencing against an isolated Mongo collection."""

import asyncio
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now


@pytest_asyncio.fixture
async def inbox_collection():
    client = AsyncMongoClient(build_mongo_connection_string(), serverSelectionTimeoutMS=1000)
    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.skip("MongoDB unavailable for isolated inbox integration test")
    collection = client["lambchat_channel_tests"]["inbox_" + uuid.uuid4().hex]
    try:
        yield collection
    finally:
        await collection.drop()
        await client.close()


async def test_accept_survives_recreation_and_concurrent_duplicates(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    first = ChannelInbox("telegram", "u", "i", collection=inbox_collection)
    message = {"message_id": "m", "chat_id": "c", "sender_id": "s", "content": "hello"}
    ids = await asyncio.gather(*(first.accept(message) for _ in range(8)))
    assert len(set(ids)) == 1
    restarted = ChannelInbox("telegram", "u", "i", collection=inbox_collection)
    pending = await restarted.pending()
    assert len(pending) == 1
    assert pending[0]["message"] == message
    assert await inbox_collection.count_documents({}) == 1


async def test_expired_owner_cannot_complete_or_renew_reclaimed_work(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    inbox = ChannelInbox("weixin", "u", "i", collection=inbox_collection)
    key = await inbox.accept({"message_id": "m", "content": "hello"})
    assert await inbox.claim(key, "old")
    assert not await inbox.claim(key, "new")
    await inbox_collection.update_one(
        {"_id": key}, {"$set": {"lease_until": utc_now() - timedelta(seconds=1)}}
    )
    assert await inbox.claim(key, "new")
    assert not await inbox.renew(key, "old")
    assert not await inbox.complete(key, "old")
    assert await inbox.complete(key, "new")
    assert not await inbox.pending()
    assert await inbox.accept({"message_id": "m", "content": "hello"}) == key
    assert not await inbox.pending()


async def test_checkpoint_survives_release_and_is_tenant_scoped(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    first = ChannelInbox("feishu", "u", "i", collection=inbox_collection)
    other = ChannelInbox("feishu", "other", "i", collection=inbox_collection)
    key = await first.accept({"message_id": "m", "content": "hello"})
    assert await other.accept({"message_id": "m", "content": "hello"}) != key
    assert await first.claim(key, "owner")
    await first.checkpoint(key, "owner", {"run_id": "run", "session_id": "session"})
    await first.release(key, "owner")
    restored = await first.claim(key, "next")
    assert restored["checkpoint"] == {"run_id": "run", "session_id": "session"}
    with pytest.raises(RuntimeError, match="lease"):
        await first.checkpoint(key, "owner", {"run_id": "wrong"})


async def test_leased_head_blocks_later_same_chat_but_not_other_chat(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    first = ChannelInbox("feishu", "u", "i", collection=inbox_collection)
    head = await first.accept({"message_id": "a", "chat_id": "same", "sender_id": "one"})
    await inbox_collection.update_one(
        {"_id": head}, {"$set": {"created_at": utc_now() - timedelta(seconds=1)}}
    )
    later = await first.accept({"message_id": "b", "chat_id": "same", "sender_id": "two"})
    other = await first.accept({"message_id": "c", "chat_id": "other"})
    assert await first.claim(head, "old-worker")
    restarted = ChannelInbox("feishu", "u", "i", collection=inbox_collection)
    assert [row["_id"] for row in await restarted.pending()] == [other]
    assert not await restarted.claim(later, "new-worker")
    assert await first.complete(head, "old-worker")
    assert {row["_id"] for row in await restarted.pending()} == {later, other}
    assert await restarted.claim(later, "new-worker")


async def test_same_chat_backlog_does_not_hide_unrelated_conversation(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    inbox = ChannelInbox("weixin", "u", "i", collection=inbox_collection)
    for index in range(140):
        await inbox.accept({"message_id": str(index), "chat_id": "busy"})
    other = await inbox.accept({"message_id": "other", "chat_id": "other"})
    pending = await inbox.pending(limit=2)
    assert len(pending) == 2
    assert other in {row["_id"] for row in pending}


async def test_generic_conversation_heads_keep_thread_and_sender_isolation(inbox_collection):
    from src.infra.channel.inbox import ChannelInbox

    inbox = ChannelInbox("telegram", "u", "i", collection=inbox_collection)
    for key, sender, thread in [("a", "s", 1), ("b", "s", 2), ("c", "other", 1)]:
        await inbox.accept(
            {
                "message_id": key,
                "chat_id": "same",
                "sender_id": sender,
                "metadata": {"message_thread_id": thread},
            }
        )
    assert len(await inbox.pending()) == 3


async def test_same_millisecond_inputs_keep_acceptance_order(inbox_collection, monkeypatch):
    from src.infra.channel import inbox as inbox_module

    frozen = utc_now()
    monkeypatch.setattr(inbox_module, "utc_now", lambda: frozen)
    inbox = inbox_module.ChannelInbox("feishu", "u", "i", collection=inbox_collection)
    first = await inbox.accept({"message_id": "b", "chat_id": "same"})
    second = await inbox.accept({"message_id": "a", "chat_id": "same"})
    assert second < first  # Hash sorting alone would reverse these arrivals.
    assert [row["_id"] for row in await inbox.pending()] == [first]
    assert await inbox.is_head(first)
    assert not await inbox.is_head(second)
    assert not await inbox.claim(second, "worker")
    assert await inbox.claim(first, "worker")
    assert await inbox.complete(first, "worker")
    assert [row["_id"] for row in await inbox.pending()] == [second]


async def test_production_collection_requires_journaled_majority_ack(inbox_collection, monkeypatch):
    from src.infra.channel import inbox as inbox_module

    monkeypatch.setattr(inbox_module, "get_mongo_client", lambda: inbox_collection.database.client)
    inbox = inbox_module.ChannelInbox("feishu", "u", "i")
    assert inbox.collection.write_concern.document == {"w": "majority", "j": True}
    isolated = inbox_module.ChannelInbox(
        "feishu",
        "u",
        "i",
        collection=inbox_collection.with_options(write_concern=inbox.collection.write_concern),
    )
    key = await isolated.accept({"message_id": "journaled", "chat_id": "same"})
    assert [row["_id"] for row in await isolated.pending()] == [key]

"""Durable worker lifecycle, fencing, and independent conversation progress."""

import asyncio
import copy

import pytest


class Inbox:
    scope = ["test", "user", "instance"]

    def __init__(self):
        self.rows = {}
        self.renew_ok = True

    async def accept(self, message):
        key = message["message_id"]
        self.rows.setdefault(
            key, {"_id": key, "message": message, "checkpoint": {}, "state": "pending"}
        )
        return key

    async def pending(self, limit=32):
        return [copy.deepcopy(r) for r in self.rows.values() if r["state"] == "pending"][:limit]

    async def is_head(self, key):
        from src.infra.channel.inbox import conversation_key

        conversation = conversation_key(self.scope, self.rows[key]["message"])
        return (
            next(
                row["_id"]
                for row in self.rows.values()
                if row["state"] == "pending"
                and conversation_key(self.scope, row["message"]) == conversation
            )
            == key
        )

    async def claim(self, key, owner):
        row = self.rows[key]
        if row.get("owner") or row["state"] != "pending":
            return None
        row["owner"] = owner
        return copy.deepcopy(row)

    async def renew(self, key, owner):
        return self.renew_ok and self.rows[key].get("owner") == owner

    async def checkpoint(self, key, owner, values):
        assert self.rows[key]["owner"] == owner
        self.rows[key]["checkpoint"].update(values)

    async def complete(self, key, owner):
        if not await self.renew(key, owner):
            return False
        self.rows[key]["state"] = "done"
        return True

    async def release(self, key, owner):
        if self.rows[key].get("owner") == owner:
            self.rows[key].pop("owner")


@pytest.fixture
def worker_module(monkeypatch):
    from src.infra.channel import inbox_worker

    locks = set()

    class Lease:
        def __init__(self, key):
            self.key = key
            self.owned = False

        async def acquire(self):
            if self.key in locks:
                return False
            locks.add(self.key)
            self.owned = True
            return True

        async def renew(self):
            return self.owned

        async def release(self):
            if self.owned:
                locks.discard(self.key)
                self.owned = False

    monkeypatch.setattr(inbox_worker, "ChatLease", Lease)
    monkeypatch.setattr(inbox_worker, "HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(inbox_worker, "POLL_SECONDS", 0.01)
    return inbox_worker


def message(key, chat="chat"):
    return {"message_id": key, "chat_id": chat, "sender_id": "sender", "metadata": {}}


async def test_accept_persists_without_dispatch_until_drain(worker_module):
    inbox = Inbox()
    delivered = []

    async def handle(msg):
        delivered.append(msg["message_id"])

    worker = worker_module.InboxWorker(inbox, handle)
    assert await worker.accept(message("one"))
    assert delivered == []
    assert inbox.rows["one"]["state"] == "pending"
    assert await worker.drain()
    assert delivered == ["one"]
    assert await worker.accept(message("one"))
    assert await worker.drain()
    assert delivered == ["one"]


async def test_checkpoint_survives_failure_and_new_worker(worker_module):
    inbox = Inbox()

    async def fail(msg):
        delivery = worker_module.current_delivery.get()
        await delivery.save(run_id="stable")
        assert delivery.checkpoint == {"run_id": "stable"}
        raise ValueError("private message")

    worker = worker_module.InboxWorker(inbox, fail)
    await worker.accept(message("one"))
    assert not await worker.drain()
    assert inbox.rows["one"]["state"] == "pending"
    assert "owner" not in inbox.rows["one"]
    seen = []

    async def recover(msg):
        seen.append(worker_module.current_delivery.get().checkpoint["run_id"])

    recovered = worker_module.InboxWorker(inbox, recover)
    assert await recovered.drain()
    assert seen == ["stable"]


async def test_lease_loss_cancels_handler_and_leaves_pending(worker_module):
    inbox = Inbox()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def handle(msg):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("one"))
    task = asyncio.create_task(worker.drain())
    await asyncio.wait_for(started.wait(), 1)
    inbox.renew_ok = False
    assert not await asyncio.wait_for(task, 1)
    assert cancelled.is_set()
    assert inbox.rows["one"]["state"] == "pending"
    assert "owner" not in inbox.rows["one"]


async def test_two_workers_serialize_chat_without_blocking_other_chat(worker_module):
    first, second = Inbox(), Inbox()
    entered, release, other = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []

    async def handle(msg):
        seen.append(msg["message_id"])
        if msg["message_id"] == "first":
            entered.set()
            await release.wait()
        if msg["message_id"] == "other":
            other.set()

    one = worker_module.InboxWorker(first, handle)
    two = worker_module.InboxWorker(second, handle)
    await one.accept(message("first"))
    task_one = asyncio.create_task(one.drain())
    await asyncio.wait_for(entered.wait(), 1)
    await two.accept(message("second"))
    await two.accept(message("other", "different"))
    task_two = asyncio.create_task(two.drain())
    await asyncio.wait_for(other.wait(), 1)
    assert "second" not in seen
    release.set()
    assert await asyncio.wait_for(task_one, 1)
    assert await asyncio.wait_for(task_two, 1)
    assert seen.index("first") < seen.index("second")


async def test_stop_cancels_active_work_and_releases_ownership(worker_module):
    inbox = Inbox()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def handle(msg):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("one"))
    running = asyncio.create_task(worker.run())
    await asyncio.wait_for(entered.wait(), 1)
    await worker.stop()
    await asyncio.wait_for(running, 1)
    assert cancelled.is_set()
    assert "owner" not in inbox.rows["one"]
    assert inbox.rows["one"]["state"] == "pending"


async def test_concurrent_stop_joins_release_even_when_release_yields(worker_module):
    inbox = Inbox()
    entered = asyncio.Event()
    release_entered = asyncio.Event()
    release_allowed = asyncio.Event()
    original_release = inbox.release

    async def delayed_release(key, owner):
        release_entered.set()
        await release_allowed.wait()
        await original_release(key, owner)

    inbox.release = delayed_release

    async def handle(msg):
        entered.set()
        await asyncio.Future()

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("one"))
    running = asyncio.create_task(worker.run())
    await asyncio.wait_for(entered.wait(), 1)
    stopping = asyncio.create_task(worker.stop())
    await asyncio.wait_for(release_entered.wait(), 1)
    second_stop = asyncio.create_task(worker.stop())
    await asyncio.sleep(0.02)
    release_allowed.set()
    await asyncio.wait_for(asyncio.gather(stopping, second_stop, running), 1)
    assert "owner" not in inbox.rows["one"]


async def test_heartbeat_cancels_lock_waiter_after_inbox_ownership_loss(worker_module):
    inbox = Inbox()
    lease = worker_module.ChatLease("occupied")
    await lease.acquire()
    seen = []

    async def handle(msg):
        seen.append(msg)

    worker = worker_module.InboxWorker(inbox, handle)
    worker._chat_key = lambda _: "occupied"
    await worker.accept(message("one"))
    task = asyncio.create_task(worker.drain())
    await asyncio.sleep(0.03)
    assert "owner" in inbox.rows["one"]
    inbox.renew_ok = False
    assert not await asyncio.wait_for(task, 1)
    await lease.release()
    assert seen == []
    assert "owner" not in inbox.rows["one"]


async def test_concurrency_is_bounded_and_stop_before_dispatch_keeps_inputs(worker_module):
    inbox = Inbox()
    entered = []
    capacity = asyncio.Event()

    async def handle(msg):
        entered.append(msg["message_id"])
        if len(entered) == 32:
            capacity.set()
        await asyncio.Future()

    worker = worker_module.InboxWorker(inbox, handle)
    for i in range(40):
        await worker.accept(message(str(i), str(i)))
    running = asyncio.create_task(worker.run())
    await asyncio.wait_for(capacity.wait(), 1)
    assert len(entered) == 32
    await worker.stop()
    await running
    assert all(row["state"] == "pending" and "owner" not in row for row in inbox.rows.values())

    another = worker_module.InboxWorker(inbox, handle)
    await another._schedule()
    await another.stop()
    assert len(entered) == 32
    assert all("owner" not in row for row in inbox.rows.values())


async def test_background_retries_failed_delivery_using_saved_checkpoint(worker_module):
    inbox = Inbox()
    completed = asyncio.Event()
    attempts = []

    async def handle(msg):
        delivery = worker_module.current_delivery.get()
        attempts.append(dict(delivery.checkpoint))
        if not delivery.checkpoint:
            await delivery.save(run_id="same-run")
            raise ValueError("private provider text")
        completed.set()

    worker = worker_module.InboxWorker(inbox, handle)
    running = asyncio.create_task(worker.run())
    try:
        assert await worker.accept(message("one"))
        await asyncio.wait_for(completed.wait(), 4)
        assert attempts == [{}, {"run_id": "same-run"}]
        await worker.drain()
        assert inbox.rows["one"]["state"] == "done"
    finally:
        await worker.stop()
        await running


async def test_redis_ownership_loss_cancels_dispatch(worker_module, monkeypatch):
    inbox = Inbox()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def lost(self):
        return False

    monkeypatch.setattr(worker_module.ChatLease, "renew", lost)

    async def handle(msg):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("one"))
    assert not await asyncio.wait_for(worker.drain(), 1)
    assert entered.is_set() and cancelled.is_set()
    assert inbox.rows["one"]["state"] == "pending"


async def test_accept_does_not_acknowledge_failed_persistence(worker_module):
    inbox = Inbox()

    async def unavailable(message):
        raise ConnectionError("private address")

    inbox.accept = unavailable

    async def handle(msg):
        pytest.fail("Unpersisted input must never reach dispatch")

    worker = worker_module.InboxWorker(inbox, handle)
    assert not await worker.accept(message("one"))
    assert inbox.rows == {}


@pytest.mark.parametrize("provider", ["weixin", "feishu"])
async def test_chat_scoped_providers_serialize_distinct_senders(worker_module, provider):
    first, second = Inbox(), Inbox()
    first.scope = second.scope = [provider, "user", "instance"]
    entered, release = asyncio.Event(), asyncio.Event()
    seen = []

    async def handle(msg):
        seen.append(msg["message_id"])
        if msg["message_id"] == "first":
            entered.set()
            await release.wait()

    one = worker_module.InboxWorker(first, handle)
    two = worker_module.InboxWorker(second, handle)
    await one.accept(message("first"))
    task_one = asyncio.create_task(one.drain())
    await asyncio.wait_for(entered.wait(), 1)
    different_sender = message("second")
    different_sender["sender_id"] = "another-sender"
    await two.accept(different_sender)
    task_two = asyncio.create_task(two.drain())
    try:
        await asyncio.sleep(0.03)
        assert seen == ["first"]
    finally:
        release.set()
        await asyncio.gather(task_one, task_two)


async def test_retrying_head_blocks_later_chat_message_but_allows_other_chat(worker_module):
    inbox = Inbox()
    seen = []

    async def handle(msg):
        seen.append(msg["message_id"])
        if msg["message_id"] == "first":
            raise RuntimeError("retry later")

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("first"))
    await worker.accept(message("second"))
    assert not await worker.drain()
    assert seen == ["first"]
    await worker.accept(message("other", "unrelated"))
    assert not await worker.drain()
    assert seen == ["first", "other"]
    await worker.stop()


async def test_dispatch_rechecks_conversation_head_after_claim(worker_module):
    inbox = Inbox()
    seen = []

    async def handle(msg):
        seen.append(msg["message_id"])

    worker = worker_module.InboxWorker(inbox, handle)
    await worker.accept(message("first"))
    await worker.accept(message("second"))
    # The in-memory claim deliberately allows a stale pending selection. The
    # dispatch check must still reject a later record after acquiring its lock.
    assert not await worker._process("second", worker._chat_key(message("second")))
    assert seen == []
    assert "owner" not in inbox.rows["second"]

"""Explicitly opted-in channel fakes; real persistence tests keep their own stores."""

from copy import deepcopy
from time import monotonic
from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_channel_inbox(monkeypatch):
    """Share durable inputs across test channel replicas without MongoDB or Redis."""
    from src.infra.channel.inbox import conversation_key

    state = SimpleNamespace(rows={}, accept_error=None, accept_gate=None)
    conversation_owners = {}

    class Inbox:
        def __init__(self, channel_type, user_id, instance_id):
            self.scope = [channel_type, user_id, instance_id]

        async def accept(self, message):
            if state.accept_gate is not None:
                await state.accept_gate.wait()
            if state.accept_error is not None:
                raise state.accept_error
            key = repr([*self.scope, message["message_id"]])
            state.rows.setdefault(
                key,
                {
                    "_id": key,
                    "scope": self.scope,
                    "state": "pending",
                    "conversation": conversation_key(self.scope, message),
                    "message": deepcopy(message),
                    "checkpoint": {},
                },
            )
            return key

        async def pending(self, limit=32):
            heads = {}
            for row in state.rows.values():
                if row["scope"] == self.scope and row["state"] == "pending":
                    heads.setdefault(row["conversation"], row)
            return deepcopy(
                [row for row in heads.values() if row.get("lease_until", 0) <= monotonic()][:limit]
            )

        async def is_head(self, key):
            row = state.rows.get(key)
            if not row or row["scope"] != self.scope or row["state"] != "pending":
                return False
            head = next(
                candidate
                for candidate in state.rows.values()
                if candidate["scope"] == self.scope
                and candidate["state"] == "pending"
                and candidate["conversation"] == row["conversation"]
            )
            return head["_id"] == key

        def owned(self, key, owner):
            row = state.rows.get(key)
            return (
                row
                if (
                    row
                    and row["scope"] == self.scope
                    and row["state"] == "pending"
                    and row.get("owner") == owner
                    and row.get("lease_until", 0) > monotonic()
                )
                else None
            )

        async def claim(self, key, owner):
            row = state.rows.get(key)
            if (
                not row
                or row["scope"] != self.scope
                or row["state"] != "pending"
                or row.get("lease_until", 0) > monotonic()
                or not await self.is_head(key)
            ):
                return None
            row.update(owner=owner, lease_until=monotonic() + 90)
            return deepcopy(row)

        async def renew(self, key, owner):
            row = self.owned(key, owner)
            if row is None:
                return False
            row["lease_until"] = monotonic() + 90
            return True

        async def checkpoint(self, key, owner, values):
            row = self.owned(key, owner)
            if row is None:
                raise RuntimeError("Channel inbox lease lost")
            row["checkpoint"].update(deepcopy(values))

        async def release(self, key, owner):
            row = state.rows.get(key)
            if row and row["scope"] == self.scope and row.get("owner") == owner:
                row.pop("owner", None)
                row.pop("lease_until", None)

        async def complete(self, key, owner):
            row = self.owned(key, owner)
            if row is None:
                return False
            row["state"] = "done"
            for field in ("message", "checkpoint", "owner", "lease_until"):
                row.pop(field, None)
            return True

    class Lease:
        def __init__(self, key):
            self.key = key
            self.owner = object()

        async def acquire(self):
            if self.key in conversation_owners:
                return False
            conversation_owners[self.key] = self.owner
            return True

        async def renew(self):
            return conversation_owners.get(self.key) is self.owner

        async def release(self):
            if conversation_owners.get(self.key) is self.owner:
                conversation_owners.pop(self.key)

    monkeypatch.setattr("src.infra.channel.chat.ChannelInbox", Inbox)
    monkeypatch.setattr("src.infra.channel.inbox_worker.ChatLease", Lease)
    return state

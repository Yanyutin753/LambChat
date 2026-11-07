"""Real storage races; isolated database, no model calls or account mutation."""

import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.assistant.service import AssistantService
from src.infra.assistant.store import AssistantStore
from src.infra.session.storage import SessionStorage
from src.infra.storage.mongodb import build_mongo_connection_string
from src.kernel.schemas.assistant import AssistantCreate, AssistantUpdate
from src.kernel.schemas.user import TokenPayload

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_ASSISTANT_MONGODB") != "1",
    reason="Set TEST_ASSISTANT_MONGODB=1 for real assistant storage races",
)


async def test_concurrent_updates_opening_and_reconnection_preserve_one_identity():
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"assistant_acceptance_{uuid4().hex}"
    database = client[database_name]
    store = AssistantStore(database.assistants)
    sessions = SessionStorage()
    sessions._collection = database.sessions
    user = TokenPayload(
        sub="assistant-acceptance", username="tester", roles=[], permissions=["chat:write"]
    )
    service = AssistantService(store=store, sessions=sessions)
    # Only model configuration is outside this storage test; all persistence is real.
    service.validate_configuration = AsyncMock()
    try:
        await store.ensure_indexes()
        assistant = await store.create(user.sub, AssistantCreate(name="Persistent helper"))
        opened = await asyncio.gather(
            *(service.open_conversation(user, assistant.id) for _ in range(12))
        )
        assert {session.id for session in opened} == {assistant.session_id}
        assert await database.sessions.count_documents({}) == 1
        assert await store.get("other-user", assistant.id) is None
        assert await store.for_session("other-user", assistant.session_id) is None
        updates = await asyncio.gather(
            *(
                store.update(
                    user.sub, assistant.id, AssistantUpdate(name=f"Edit {index}", revision=1)
                )
                for index in range(12)
            )
        )
        assert sum(item is not None for item in updates) == 1
        restored = await AssistantStore(database.assistants).get(user.sub, assistant.id)
        assert restored is not None and restored.revision == 2
        assert restored.session_id == assistant.session_id
        assert await store.count(user.sub) == 1
        await store.update(
            user.sub,
            assistant.id,
            AssistantUpdate(name=restored.name, revision=2, status="archived"),
        )
        assert await store.list(user.sub) == []
        assert len(await store.list(user.sub, archived=True)) == 1
        assert await database.sessions.count_documents({}) == 1
    finally:
        await client.drop_database(database_name)
        await client.close()


async def test_memory_management_and_restore_keep_real_mongo_partitions(monkeypatch):
    import json

    from src.api.routes import memory as routes
    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.kernel.errors import AppError
    from tests.api.routes.test_memory_import_export import _FakeStore

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database = client[f"assistant_memory_acceptance_{uuid4().hex}"]
    store = AssistantStore(database.assistants)
    backend = NativeMemoryBackend()
    backend._collection = database.native_memories
    backend._store = _FakeStore()
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    monkeypatch.setattr(routes, "_write_vector_index", AsyncMock())
    monkeypatch.setattr("src.infra.assistant.memory_management.AssistantStore", lambda: store)
    user = TokenPayload(sub="owner", username="tester", roles=[])
    try:
        await backend._collection.create_index("memory_id", unique=True)
        assistant = await store.create(user.sub, AssistantCreate(name="Private researcher"))
        other = await store.create(user.sub, AssistantCreate(name="Other researcher"))
        short = await routes.create_memory(
            {"content": "Private research fact."}, user=user, assistant_id=assistant.id
        )
        long = await routes.create_memory(
            {"content": "Durable research evidence. " * 120}, user=user, assistant_id=assistant.id
        )
        foreign_bank = await routes.create_memory(
            {"content": "Other assistant fact."}, user=user, assistant_id=other.id
        )
        await routes.create_memory({"content": "Personal preference fact."}, user=user)
        listed = await routes.list_memories(
            memory_type=None,
            search=None,
            context=None,
            limit=50,
            offset=0,
            user=user,
            assistant_id=assistant.id,
        )
        assert {row["memory_id"] for row in listed["memories"]} == {
            short["memory_id"],
            long["memory_id"],
        }
        assert listed["total"] == 2
        for operation in (routes.get_memory, routes.delete_memory):
            with pytest.raises(AppError):
                await operation(foreign_bank["memory_id"], user=user, assistant_id=assistant.id)
        with pytest.raises(AppError):
            await routes.update_memory(
                foreign_bank["memory_id"],
                {"content": "Forbidden bank edit"},
                user=user,
                assistant_id=assistant.id,
            )
        response = await routes.export_memories(user=user, assistant_id=assistant.id)
        backup = json.loads("".join([part async for part in response.body_iterator]))
        assert len(backup["memories"]) == 2
        assert (await routes.import_memories(backup, user=user, assistant_id=assistant.id))[
            "overwritten"
        ] == 2
        assert (await routes.get_memory(long["memory_id"], user=user, assistant_id=assistant.id))[
            "content"
        ] == "Durable research evidence. " * 119 + "Durable research evidence."
        assert (
            await routes.delete_memory(short["memory_id"], user=user, assistant_id=assistant.id)
        )["success"]
        assert await backend._collection.count_documents({}) == 3
    finally:
        await client.drop_database(database.name)
        await client.close()


async def test_rule_claims_survive_restart_and_bound_concurrent_wakeups(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    from src.infra.assistant import rules
    from src.infra.scheduler.storage import ScheduledTaskStorage
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.scheduled_task import ScheduledTask

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database = client[f"assistant_rules_acceptance_{uuid4().hex}"]
    storage = ScheduledTaskStorage()
    storage._collections = {
        name: database[name]
        for name in ("scheduled_tasks", "task_run_records", "scheduled_task_metadata")
    }
    user = TokenPayload(
        sub="owner", username="tester", roles=[], permissions=["chat:write", "scheduled_task:write"]
    )
    monkeypatch.setattr(rules, "_load_user_payload", AsyncMock(return_value=user))
    monkeypatch.setattr(
        rules.AssistantStore, "get", AsyncMock(return_value=SimpleNamespace(status="active"))
    )
    execute = AsyncMock()
    monkeypatch.setattr(rules.AssistantTaskService, "create", execute)
    task = ScheduledTask(
        id="rule",
        owner_id=user.sub,
        name="Observe",
        agent_id="search",
        trigger_type="interval",
        trigger_config={"seconds": 60},
        input_payload={
            "message": "Check",
            "assistant_rule": {
                "assistant_id": "helper",
                "mode": "observe",
                "timeout_seconds": 120,
                "max_wakeups": 2,
            },
        },
    )
    try:
        await storage.ensure_indexes()
        await storage.create_task(task)
        results = await asyncio.gather(
            *(rules.run_assistant_rule(task, "interval", storage) for _ in range(12))
        )
        assert sum(result.get("status") == "observed" for result in results) == 1
        assert await database.task_run_records.count_documents({"status": "success"}) == 1
        await database.scheduled_tasks.update_one(
            {"_id": "rule"}, {"$set": {"assistant_rule_last_at": utc_now() - timedelta(seconds=65)}}
        )
        restarted = ScheduledTaskStorage()
        restarted._collections = dict(storage._collections)
        restored = await restarted.get_task_for_execution("rule")
        assert (await rules.run_assistant_rule(restored, "interval", restarted))[
            "status"
        ] == "observed"
        await database.scheduled_tasks.update_one(
            {"_id": "rule"}, {"$set": {"assistant_rule_last_at": utc_now() - timedelta(seconds=65)}}
        )
        assert (await rules.run_assistant_rule(restored, "interval", restarted))["skipped"] is True
        saved = await database.scheduled_tasks.find_one({"_id": "rule"})
        assert saved["assistant_rule_wakeups"] == 2
        assert saved["total_runs"] == 2
        execute.assert_not_awaited()
    finally:
        await client.drop_database(database.name)
        await client.close()

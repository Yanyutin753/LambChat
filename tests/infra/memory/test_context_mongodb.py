"""Real local MongoDB coverage: TEST_MEMORY_MONGODB=1 uv run pytest <this file>."""

import os
from uuid import uuid4

import pytest

from src.infra.memory import extraction
from src.infra.memory.evolution import reflector
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1",
    reason="Set TEST_MEMORY_MONGODB=1 to test against local MongoDB",
)


@pytest.mark.asyncio
async def test_real_trace_context_is_removed_before_memory_extraction(monkeypatch):
    client = get_mongo_client()
    database_name = settings.MONGODB_DB
    db = client[database_name]
    run_id = f"memory-context-{uuid4().hex}"
    session_id = f"memory-session-{uuid4().hex}"
    question = "请记住：项目部署必须支持回滚。"
    answer = "已确认，部署失败时回滚到上一版本。"
    try:
        await client.admin.command("ping")
        for injected_chars in (10, 6000):
            block = "<memory_context>" + "x" * injected_chars + "</memory_context>"
            await db[settings.MONGODB_TRACES_COLLECTION].insert_one(
                {
                    "run_id": run_id,
                    "session_id": session_id,
                    "user_id": "user-1",
                    "status": "completed",
                    "started_at": utc_now(),
                    "conversation_search": {
                        "user_text": block + question,
                        "assistant_final_text": block + answer,
                    },
                    "events": [
                        {
                            "event_type": "user:message",
                            "data": {"content": block + question},
                        },
                        {
                            "event_type": "message:chunk",
                            "data": {"text_id": "text-1", "content": block + answer},
                        },
                    ],
                }
            )
            transcript = await extraction.load_session_transcript(
                db, session_id, "user-1", max_chars=1000
            )
            assert transcript == [{"run_id": run_id, "user": question, "assistant": answer}]
            assert await reflector._load_exchange(run_id, session_id, "user-1") == (
                question,
                answer,
            )
            await db[settings.MONGODB_TRACES_COLLECTION].delete_one({"run_id": run_id})
        assert (
            await extraction.load_session_transcript(db, session_id, "other-user", max_chars=1000)
            == []
        )
        assert await reflector._load_exchange(run_id, session_id, "other-user") == ("", "")
    finally:
        await db[settings.MONGODB_TRACES_COLLECTION].delete_one({"run_id": run_id})

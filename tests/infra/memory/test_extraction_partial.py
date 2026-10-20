"""A partial batch must retain identities and avoid repeating model extraction."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.memory import extraction


@pytest.fixture(autouse=True)
def no_forget_watermark(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.memory import extraction as module

    monkeypatch.setattr(module, "source_watermark", AsyncMock(return_value=None))


@pytest.mark.parametrize("failure", ["quality", "network"])
async def test_partial_batch_keeps_written_ids_and_retries_only_unfinished_items(
    monkeypatch, failure
):
    monkeypatch.setattr(
        extraction,
        "load_session_transcript",
        AsyncMock(
            return_value=[
                {
                    "run_id": "r1",
                    "user": "Personal preference and project decision",
                    "assistant": "Recorded",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "src.infra.memory.extraction_gate.evaluate_extraction_gate", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("src.infra.memory.extraction_gate.log_context_second_opinion", AsyncMock())
    monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(return_value=object()))
    invoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {"raw_memory": "The user prefers concise answers.", "context": "user"},
                        {
                            "raw_memory": "Alpha uses PostgreSQL for durable data.",
                            "context": "project",
                        },
                    ]
                }
            )
        )
    )
    monkeypatch.setattr("src.infra.llm.retry.ainvoke_with_retry", invoke)
    failed_result = (
        {"success": False, "error": "not durable enough", "retryable": False}
        if failure == "quality"
        else OSError("storage unavailable")
    )
    retain = AsyncMock(
        side_effect=[
            {"success": True, "memory_id": "m1"},
            failed_result,
            {"success": True, "memory_id": "m2"},
        ]
    )
    backend = SimpleNamespace(retain=retain, _collection=None)
    session = {"session_id": "s1", "metadata": {"project_id": "alpha"}}
    saved = []

    async def save(state):
        saved.append(json.loads(json.dumps(state)))

    outcome = await extraction.extract_session_memory(
        backend,
        None,
        "u1",
        session,
        save_resume_state=save,
    )

    assert outcome.status == "failed"
    assert outcome.memory_ids == ("m1",)
    assert outcome.retryable is (failure == "network")
    assert outcome.error == (
        "not durable enough" if failure == "quality" else "storage unavailable"
    )
    assert saved[0]["next_index"] == 0 and saved[0]["memory_ids"] == []
    assert saved[-1]["next_index"] == 1 and saved[-1]["memory_ids"] == ["m1"]
    if failure == "network":
        resumed = await extraction.extract_session_memory(
            backend,
            None,
            "u1",
            session,
            resume_state=outcome.resume_state,
        )
        assert resumed.status == "succeeded"
        assert resumed.memory_ids == ("m1", "m2")
        assert retain.await_count == 3
        invoke.assert_awaited_once()

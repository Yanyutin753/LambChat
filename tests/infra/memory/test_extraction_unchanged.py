"""Repeated maintenance must skip paid work only for the same successful input."""

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


@pytest.mark.parametrize("change", [None, "fact", "run", "project", "prompt", "model"])
async def test_successful_input_revision_controls_repeated_extraction(monkeypatch, change):
    turns = [{"run_id": "r1", "user": "I prefer concise answers.", "assistant": "Recorded."}]
    monkeypatch.setattr(extraction, "load_session_transcript", AsyncMock(return_value=turns))
    monkeypatch.setattr(
        "src.infra.memory.extraction_gate.evaluate_extraction_gate", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("src.infra.memory.extraction_gate.log_context_second_opinion", AsyncMock())
    monkeypatch.setattr(
        extraction, "load_stage_one_system_prompt", lambda: "Extract durable facts."
    )
    monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(return_value=object()))
    invoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {"raw_memory": "The user prefers concise answers.", "context": "user"}
                    ],
                }
            )
        )
    )
    monkeypatch.setattr("src.infra.llm.retry.ainvoke_with_retry", invoke)
    backend = SimpleNamespace(
        retain=AsyncMock(return_value={"success": True, "memory_id": "m1"}),
        _collection=None,
    )
    session = {"session_id": "s1", "name": "Preferences", "metadata": {"project_id": "alpha"}}

    first = await extraction.extract_session_memory(backend, None, "u1", session)
    assert first.status == "succeeded"
    assert first.input_fingerprint
    if change == "fact":
        turns[0]["user"] = "I now prefer detailed answers."
    elif change == "run":
        turns[0]["run_id"] = "r2"
    elif change == "project":
        session["metadata"]["project_id"] = "beta"
    elif change == "prompt":
        monkeypatch.setattr(
            extraction, "load_stage_one_system_prompt", lambda: "Updated extraction rules."
        )
    elif change == "model":
        monkeypatch.setattr(extraction.settings, "NATIVE_MEMORY_MODEL", "another-model")

    second = await extraction.extract_session_memory(
        backend,
        None,
        "u1",
        session,
        previous_input_fingerprint=first.input_fingerprint,
    )

    assert second.status == ("succeeded_no_output" if change is None else "succeeded")
    assert invoke.await_count == (1 if change is None else 2)
    assert backend.retain.await_count == invoke.await_count

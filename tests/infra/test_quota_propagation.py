"""Quota denials stop graph fallbacks and background paid work."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.infra.llm.quota import quota_user_id
from src.kernel.errors import AppError, ErrorCode


@pytest.fixture
def denied():
    return AppError(ErrorCode.USAGE_QUOTA_EXCEEDED)


async def test_model_fallback_does_not_replay_quota_denial(monkeypatch, denied):
    from src.infra.agent.middleware.retry import ModelFallbackMiddleware

    middleware = ModelFallbackMiddleware(fallback_model="fallback")
    monkeypatch.setattr(middleware, "_schedule_prewarm", lambda: None)
    fallback = AsyncMock()
    monkeypatch.setattr(middleware, "_invoke_fallback", fallback)
    with pytest.raises(AppError) as error:
        await middleware.awrap_model_call(object(), AsyncMock(side_effect=denied))
    assert error.value is denied
    fallback.assert_not_awaited()


async def test_parent_context_compression_propagates_quota_before_writing(monkeypatch, denied):
    from src.infra.agent.middleware.main_agent_context import (
        CompressibleMarkdownLog,
        MainAgentContextMiddleware,
    )

    backend = SimpleNamespace(awrite=AsyncMock())
    monkeypatch.setattr(
        CompressibleMarkdownLog, "check_and_compress", AsyncMock(side_effect=denied)
    )
    with pytest.raises(AppError) as error:
        await MainAgentContextMiddleware(backend=backend)._write_context_file(
            SimpleNamespace(state={"messages": [HumanMessage("Prior context")]})
        )
    assert error.value is denied
    backend.awrite.assert_not_awaited()


async def test_activity_compression_propagates_quota(denied):
    from src.infra.agent.middleware.subagent_activity import SubagentActivityMiddleware

    middleware = SubagentActivityMiddleware(
        backend=object(), max_log_chars=10, compressor=AsyncMock(side_effect=denied)
    )
    with pytest.raises(AppError) as error:
        await middleware._cap_transcript("activity " * 20)
    assert error.value is denied


async def test_recall_binds_explicit_owner_and_restores_context(monkeypatch):
    from src.infra.memory.client.native import backend

    observed = []

    async def recall(*args, **kwargs):
        observed.append(quota_user_id())
        return {"memories": []}

    monkeypatch.setattr(backend, "recall_memories", recall)
    before = quota_user_id()
    await backend.NativeMemoryBackend.recall(object(), "memory-owner", "query")
    assert observed == ["memory-owner"]
    assert quota_user_id() == before


async def test_extraction_model_denial_is_not_converted_to_retryable_failure(monkeypatch, denied):
    from src.infra.memory import extraction, extraction_gate

    monkeypatch.setattr(
        extraction, "load_session_transcript", AsyncMock(return_value=[{"run_id": "run"}])
    )
    monkeypatch.setattr(extraction_gate, "evaluate_extraction_gate", AsyncMock(return_value=None))
    monkeypatch.setattr(extraction, "render_stage_one_input", lambda *args: "history")
    monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(side_effect=denied))
    with pytest.raises(AppError) as error:
        await extraction.extract_session_memory(object(), object(), "owner", {"session_id": "s"})
    assert error.value is denied


async def test_extraction_pass_stops_after_nonretryable_quota_failure(monkeypatch, denied):
    from src.infra.memory import distributed, extraction, user_pref
    from src.infra.storage import mongodb
    from src.infra.usage import quota

    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(
        quota,
        "UsageQuota",
        lambda: SimpleNamespace(
            snapshot=AsyncMock(
                return_value={"five_hour": {"blocked": False}, "weekly": {"blocked": False}}
            )
        ),
    )

    jobs = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    db = {extraction.EXTRACTION_JOBS_COLLECTION: jobs}
    monkeypatch.setattr(mongodb, "get_mongo_client", lambda: {extraction.settings.MONGODB_DB: db})
    monkeypatch.setattr(user_pref, "user_memory_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(distributed, "check_auto_retain_daily_limit", AsyncMock(return_value="ok"))
    recorded = AsyncMock()
    monkeypatch.setattr(distributed, "record_auto_retain_usage", recorded)
    monkeypatch.setattr(extraction, "ensure_extraction_job_indexes", AsyncMock())
    monkeypatch.setattr(
        extraction,
        "claim_candidate_jobs",
        AsyncMock(
            return_value=[
                ({"session_id": key}, {"_id": key, "attempts": 1}) for key in ("first", "second")
            ]
        ),
    )
    extract = AsyncMock(side_effect=denied)
    monkeypatch.setattr(extraction, "extract_session_memory", extract)
    outcome = await extraction.run_extraction_pass("owner", backend=object())
    assert outcome["failed"] == 1
    assert outcome["succeeded"] == 0
    extract.assert_awaited_once()
    recorded.assert_not_awaited()
    assert jobs.update_one.await_args.args[1]["$set"]["status"] == "exhausted"
    assert jobs.update_one.await_args.args[1]["$set"]["next_retry_at"] is None


async def test_reflection_model_quota_is_not_reported_as_skipped_success(monkeypatch, denied):
    from src.infra.memory.evolution import reflector

    monkeypatch.setattr(reflector, "_load_exchange", AsyncMock(return_value=("question", "answer")))
    backend = SimpleNamespace(_get_memory_model=AsyncMock(side_effect=denied))
    signal = reflector.SignalRun(run_id="run", session_id="session", kind="failed")
    with pytest.raises(AppError) as error:
        await reflector.reflect_on_run(backend, "owner", signal)
    assert error.value is denied


@pytest.mark.parametrize("positive", [False, True])
async def test_evolution_stops_on_quota_and_counts_only_earlier_writes(
    monkeypatch, denied, positive
):
    from src.infra.memory import user_pref
    from src.infra.memory.evolution import reflector

    monkeypatch.setattr(user_pref, "user_memory_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(reflector, "_check_daily_quota", AsyncMock(return_value=True))
    signals = [
        reflector.SignalRun(run_id=str(index), session_id="session", kind="failed")
        for index in range(3)
    ]
    monkeypatch.setattr(
        reflector, "collect_signal_runs", AsyncMock(return_value=[] if positive else signals)
    )
    monkeypatch.setattr(reflector, "_should_sample_positive", lambda: True)
    positives = AsyncMock(return_value=signals)
    monkeypatch.setattr(reflector, "collect_positive_runs", positives)
    reflect = AsyncMock(side_effect=[{"stored": 1}, denied, {"stored": 1}])
    monkeypatch.setattr(reflector, "reflect_on_run", reflect)
    processed, counted = AsyncMock(), AsyncMock()
    monkeypatch.setattr(reflector, "_mark_signal_processed", processed)
    monkeypatch.setattr(reflector, "_increment_daily_quota", counted)
    with pytest.raises(AppError) as error:
        await reflector.evolve_user(object(), "owner", max_per_night=3)
    assert error.value is denied
    assert reflect.await_count == 2
    processed.assert_awaited_once_with(signals[0], "owner")
    counted.assert_awaited_once_with("owner", 1)
    if not positive:
        positives.assert_not_awaited()

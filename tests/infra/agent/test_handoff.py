from types import SimpleNamespace

import pytest

from src.agents.core.node_utils import resolve_run_usage_carry
from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.agent.handoff import (
    get_run_handoff,
    resolve_execution_agent_id,
    restore_handoff_usage,
)


@pytest.mark.parametrize("prior_certified", [True, False])
def test_read_denominator_certificate_survives_handoff_only_when_all_segments_certified(
    prior_certified,
):
    prior = {
        "input_tokens": 100,
        "unknown_usage_fields": [],
        "input_includes_cache": prior_certified,
    }
    latest = {"input_tokens": 200, "unknown_usage_fields": [], "input_includes_cache": True}
    result = restore_handoff_usage({"prior_usage": prior}, latest)["prior_usage"]
    assert (result.get("input_includes_cache") is True) is prior_certified
    _, carried = resolve_run_usage_carry({"prior_usage": result}, default_started_at=1.0)
    assert carried == result


@pytest.mark.parametrize(
    "selected,run_id,target,expected",
    [
        ("quick", "run-1", "search", "search"),
        ("quick", "old-run", "search", "quick"),
        ("quick", "run-1", "team", "quick"),
        ("team", "run-1", "search", "team"),
    ],
)
def test_recovery_only_uses_the_current_runs_authorized_handoff(selected, run_id, target, expected):
    metadata = {
        "agent_id": selected,
        "current_run_id": "run-1",
        "agent_handoff": {"run_id": run_id, "agent_id": target},
    }
    assert resolve_execution_agent_id(metadata) == expected


def test_missing_run_ids_cannot_activate_a_handoff():
    assert get_run_handoff({"agent_id": "quick", "agent_handoff": {"agent_id": "search"}}) == {}


def test_restart_uses_latest_cumulative_usage_without_overwriting_the_original_request():
    carry = restore_handoff_usage(
        {
            "message_id": "handoff-user:run-1",
            "run_started_at": 100.0,
            "prior_usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        },
        {"input_tokens": 100, "output_tokens": 12, "total_tokens": 112, "cache_read_tokens": 20},
    )
    assert carry == {
        "run_started_at": 100.0,
        "prior_usage": {
            "input_tokens": 100,
            "output_tokens": 12,
            "total_tokens": 112,
            "cache_read_tokens": 20,
        },
    }
    assert "message_id" not in carry


async def test_handoff_and_two_approval_resumes_keep_all_usage_exactly_once(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.writer.present import Presenter, PresenterConfig

    monkeypatch.setattr(
        "src.infra.agent.events.processor.compute_usage_cost", AsyncMock(return_value=None)
    )
    presenter = Presenter(PresenterConfig(enable_storage=False))
    emitted = []
    monkeypatch.setattr(presenter, "emit", AsyncMock(side_effect=emitted.append))
    carry = {
        "run_started_at": 100.0,
        "prior_usage": {
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 1,
            "unknown_usage_fields": [],
        },
    }
    for resume, usage, expected_total, expected_cache in [
        (
            None,
            {
                "input_tokens": 20,
                "output_tokens": 3,
                "total_tokens": 23,
                "input_token_details": {"cache_read": 5, "cache_creation": 0},
            },
            35,
            8,
        ),
        (
            {
                "run_started_at": 100.0,
                "prior_usage": {
                    "input_tokens": 30,
                    "output_tokens": 5,
                    "total_tokens": 35,
                    "cache_read_tokens": 8,
                    "cache_creation_tokens": 1,
                    "unknown_usage_fields": [],
                },
            },
            {
                "input_tokens": 7,
                "output_tokens": 1,
                "total_tokens": 8,
                "input_token_details": {"cache_read": 0, "cache_creation": 0},
            },
            43,
            8,
        ),
        (
            {
                "run_started_at": 100.0,
                "prior_usage": {
                    "input_tokens": 37,
                    "output_tokens": 6,
                    "total_tokens": 43,
                    "cache_read_tokens": 8,
                    "cache_creation_tokens": 1,
                    "unknown_usage_fields": [],
                },
            },
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_token_details": {"cache_read": 0, "cache_creation": 0},
            },
            43,
            8,
        ),
    ]:
        start, prior = resolve_run_usage_carry(
            resume, default_started_at=200.0, handoff_usage=carry
        )
        assert start == 100.0
        processor = AgentEventProcessor(presenter)
        processor.seed_usage(prior)
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "data": {"output": SimpleNamespace(usage_metadata=usage)},
                "metadata": {},
            }
        )
        await processor.emit_token_usage()
        assert emitted[-1]["data"]["total_tokens"] == expected_total
        assert emitted[-1]["data"]["cache_read_tokens"] == expected_cache
        assert emitted[-1]["data"]["cache_creation_tokens"] == 1


@pytest.mark.parametrize("unknown", [[], ["cache_read_tokens"]])
def test_restart_preserves_completeness_through_restore_resolve_and_seed(unknown):
    counts = {
        "input_tokens": 100,
        "output_tokens": 10,
        "total_tokens": 110,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "unknown_usage_fields": unknown,
        "usage_observed": True,
    }
    restored = restore_handoff_usage({"prior_usage": counts}, counts)
    _, carried = resolve_run_usage_carry(restored, default_started_at=1)
    from src.infra.writer.present import create_presenter

    processor = AgentEventProcessor(create_presenter(session_id="s", agent_id="search"))
    processor.seed_usage(carried)
    assert processor.usage_totals() == {
        **counts,
        "_usage_ledger_id": processor._usage_ledger_id,
        "cost_source": "provider_settlement",
        "cost_receipts": {},
        "legacy_cost_units": 0,
        "legacy_cost_unknown": True,
        "legacy_actual_models": [],
        "legacy_model_identity_complete": False,
    }

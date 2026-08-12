from __future__ import annotations

import logging

import pytest

from src.infra.agent.first_event_timing import FirstEventTiming


def test_first_event_timing_records_each_allowlisted_phase_once(caplog) -> None:
    times = iter([10.0, 10.4, 10.7])
    timing = FirstEventTiming(clock=lambda: next(times))

    with caplog.at_level(logging.INFO, logger="src.infra.agent.first_event_timing"):
        timing.start_model()
        timing.record_once("provider_first_delta")
        timing.record_once("provider_first_reasoning")
        timing.record_once("provider_first_reasoning")

    records = [record for record in caplog.records if record.msg == "first_event_timing"]
    assert [record.first_event_phase for record in records] == [
        "provider_first_delta",
        "provider_first_reasoning",
    ]
    assert [record.duration_ms for record in records] == [400.0, 700.0]


def test_first_event_timing_rejects_dynamic_phase_names() -> None:
    timing = FirstEventTiming(clock=lambda: 0.0)
    with pytest.raises(ValueError, match="Unsupported first-event phase"):
        timing.record_once("session-secret")  # type: ignore[arg-type]

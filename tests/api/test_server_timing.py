from __future__ import annotations

import pytest

from src.api.server_timing import (
    begin_server_timing_request,
    record_server_timing,
    reset_server_timing_request,
    serialize_server_timing,
)


def test_server_timing_serializes_allowlisted_metrics_stably() -> None:
    token = begin_server_timing_request()
    try:
        record_server_timing("settings", 4.126)
        record_server_timing("history", 12.345)
        record_server_timing("history", 0.655)

        assert serialize_server_timing() == "history;dur=13.00, settings;dur=4.13"
    finally:
        reset_server_timing_request(token)


def test_server_timing_rejects_dynamic_or_secret_metric_names() -> None:
    token = begin_server_timing_request()
    try:
        with pytest.raises(ValueError, match="Unsupported Server-Timing metric"):
            record_server_timing("session-04480e79-secret", 1.0)  # type: ignore[arg-type]
        assert serialize_server_timing() == ""
    finally:
        reset_server_timing_request(token)

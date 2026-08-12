"""Request-local, allowlisted Server-Timing phase collection."""

from __future__ import annotations

import math
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import AsyncIterator, Literal

ServerTimingMetric = Literal[
    "feedback",
    "history",
    "session_detail",
    "session_list",
    "session_mark_read",
    "settings",
    "teams",
]

_ALLOWED_METRICS = frozenset(
    {
        "feedback",
        "history",
        "session_detail",
        "session_list",
        "session_mark_read",
        "settings",
        "teams",
    }
)
_request_timings: ContextVar[dict[str, float] | None] = ContextVar(
    "server_timings",
    default=None,
)


def begin_server_timing_request() -> Token[dict[str, float] | None]:
    return _request_timings.set({})


def reset_server_timing_request(token: Token[dict[str, float] | None]) -> None:
    _request_timings.reset(token)


def record_server_timing(name: ServerTimingMetric, duration_ms: float) -> None:
    if name not in _ALLOWED_METRICS:
        raise ValueError(f"Unsupported Server-Timing metric: {name}")
    if not math.isfinite(duration_ms):
        return
    timings = _request_timings.get()
    if timings is None:
        return
    timings[name] = timings.get(name, 0.0) + max(float(duration_ms), 0.0)


def serialize_server_timing() -> str:
    timings = _request_timings.get()
    if not timings:
        return ""
    return ", ".join(f"{name};dur={timings[name]:.2f}" for name in sorted(timings))


@asynccontextmanager
async def timed_server_phase(name: ServerTimingMetric) -> AsyncIterator[None]:
    started_at = time.perf_counter()
    try:
        yield
    finally:
        record_server_timing(name, (time.perf_counter() - started_at) * 1000)

"""Safe, content-free timing for the first top-level provider events."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from src.infra.logging import get_logger

logger = get_logger(__name__)

FirstEventPhase = Literal[
    "provider_first_delta",
    "provider_first_reasoning",
    "provider_first_text",
]
_ALLOWED_PHASES = frozenset(
    {
        "provider_first_delta",
        "provider_first_reasoning",
        "provider_first_text",
    }
)


class FirstEventTiming:
    """Record each allowlisted milestone once, relative to model start."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._model_started_at: float | None = None
        self._seen: set[str] = set()

    def start_model(self) -> None:
        if self._model_started_at is None:
            self._model_started_at = self._clock()

    def record_once(self, phase: FirstEventPhase) -> None:
        if phase not in _ALLOWED_PHASES:
            raise ValueError(f"Unsupported first-event phase: {phase}")
        if phase in self._seen or self._model_started_at is None:
            return

        self._seen.add(phase)
        logger.info(
            "first_event_timing",
            extra={
                "first_event_phase": phase,
                "duration_ms": round((self._clock() - self._model_started_at) * 1000, 2),
            },
        )

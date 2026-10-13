"""Session-scoped objectives; distinct from an ordinary run's rubric."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

GoalStatus = Literal[
    "active", "paused", "waiting_human", "blocked", "completed", "budget_limited", "cleared"
]


class GoalLimits(BaseModel):
    max_turns: int = Field(10, ge=1, le=10)
    max_tokens: int = Field(100000, ge=1, le=100000)
    max_seconds: int = Field(3600, ge=1, le=3600)


class GoalAccounting(BaseModel):
    turns: int = 0
    tokens: int | None = 0


class GoalRunAccounting(BaseModel):
    run_id: str
    version: int
    tokens: int | None = 0
    completed: bool = False


class PersistentGoalCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=8000)
    rubric: str = Field(min_length=1, max_length=16000)
    limits: GoalLimits = Field(default_factory=GoalLimits)
    expected_revision: int | None = None


class PersistentGoal(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    user_id: str
    objective: str
    rubric: str
    version: int = 1
    revision: int = 1
    status: GoalStatus = "active"
    limits: GoalLimits = Field(default_factory=GoalLimits)
    accounting: GoalAccounting = Field(default_factory=GoalAccounting)
    run_accounting: list[GoalRunAccounting] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_run_id: str | None = None
    continuation_sequence: int = 0
    stagnant_turns: int = 0
    last_progress_signature: str = ""
    last_verdict: dict[str, Any] | None = None
    intent_submitted: bool = False
    dispatch_token: str | None = None
    dispatch_expires_at: datetime | None = None

"""Session-scoped objectives; distinct from an ordinary run's rubric."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

GoalStatus = Literal[
    "active", "paused", "waiting_human", "blocked", "completed", "budget_limited", "cleared"
]


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
    expected_revision: int | None = None


class PersistentGoalUpdate(PersistentGoalCreate):
    model_config = {"str_strip_whitespace": True}
    expected_revision: int


class PersistentGoal(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    user_id: str
    objective: str
    rubric: str
    version: int = 1
    revision: int = 1
    status: GoalStatus = "active"
    stop_reason: str | None = None
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

    @model_validator(mode="before")
    @classmethod
    def restore_legacy_budget_stop(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("status") == "budget_limited":
            return {**value, "status": "paused", "stop_reason": None}
        return value

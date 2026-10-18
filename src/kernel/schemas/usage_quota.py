"""Validated mutation contracts for account quota resets."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResetCardIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: UUID


class ScopedResetCardIssueRequest(ResetCardIssueRequest):
    window: Literal["five_hour", "weekly"] = "five_hour"


class QuotaResetRequest(ResetCardIssueRequest):
    window: Literal["five_hour", "weekly"]


class ResetCardConsumeRequest(ResetCardIssueRequest):
    credit_id: str | None = Field(default=None, min_length=1, max_length=128)

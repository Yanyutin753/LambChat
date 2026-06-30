"""Scheduled task schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.kernel.schemas.channel import ChannelType

# ── Enums ──────────────────────────────────────────


class TriggerType(str, Enum):
    INTERVAL = "interval"
    CRON = "cron"
    DATE = "date"


class ScheduledTaskStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


# ── Trigger configs ────────────────────────────────


class IntervalTriggerConfig(BaseModel):
    """Fixed-interval trigger."""

    seconds: int = Field(..., ge=1, description="Interval in seconds")


class CronTriggerConfig(BaseModel):
    """Cron-expression trigger. All fields accept standard cron syntax."""

    year: Optional[str] = Field(None, description="Year pattern")
    month: Optional[str] = Field(None, description="Month pattern (1-12)")
    day: Optional[str] = Field(None, description="Day of month pattern (1-31)")
    week: Optional[str] = Field(None, description="ISO week pattern (1-53)")
    day_of_week: Optional[str] = Field(None, description="Day of week pattern (mon,tue,...)")
    hour: Optional[str] = Field("0", description="Hour pattern (0-23)")
    minute: Optional[str] = Field("0", description="Minute pattern (0-59)")
    second: Optional[str] = Field("0", description="Second pattern (0-59)")


class DateTriggerConfig(BaseModel):
    """One-time trigger at a specific UTC timestamp."""

    run_date: datetime = Field(..., description="One-time execution datetime")


class ChannelDeliveryConfig(BaseModel):
    """Optional channel delivery target for scheduled-task results."""

    channel_type: ChannelType = Field(..., description="Channel type to deliver task results to")
    chat_id: str = Field(..., min_length=1, description="Target channel chat/conversation ID")
    channel_instance_id: Optional[str] = Field(
        None,
        description="Channel instance ID that originated this delivery target",
    )
    enabled: bool = Field(True, description="Whether channel result delivery is enabled")
    send_on_success: bool = Field(True, description="Send successful agent results to channel")
    max_content_chars: int = Field(
        4000,
        ge=1,
        le=20000,
        description="Maximum text characters sent to the channel",
    )


# ── Task models ────────────────────────────────────


class ScheduledTaskCreate(BaseModel):
    """Request body for creating a scheduled task."""

    name: str = Field(..., min_length=1, max_length=200)
    agent_id: str = Field(..., min_length=1)
    trigger_type: TriggerType
    trigger_config: dict = Field(
        ...,
        description="Trigger config (IntervalTriggerConfig | CronTriggerConfig | DateTriggerConfig)",
    )
    timezone: str = Field("UTC", description="IANA timezone used for cron/date schedule semantics")
    input_payload: dict = Field(default_factory=dict, description="Agent input parameters")
    description: Optional[str] = Field(None, max_length=2000)
    enabled: bool = Field(True)
    run_on_start: bool = Field(False)
    max_retries: int = Field(0, ge=0, le=10)
    timeout_seconds: int = Field(3600, ge=10, le=7200)
    source_session_id: Optional[str] = Field(
        None, description="Conversation session where the task was created"
    )
    source_run_id: Optional[str] = Field(None, description="Agent run where the task was created")
    created_by: str = Field("user", description="Creator source: user / agent / api")
    delivery: Optional[ChannelDeliveryConfig] = Field(
        None,
        description="Optional channel target for delivering successful task results",
    )


class ScheduledTaskUpdate(BaseModel):
    """Request body for updating a scheduled task."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    agent_id: Optional[str] = Field(None, min_length=1)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    timezone: Optional[str] = None
    input_payload: Optional[dict] = None
    description: Optional[str] = Field(None, max_length=2000)
    enabled: Optional[bool] = None
    run_on_start: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(None, ge=10, le=7200)
    delivery: Optional[ChannelDeliveryConfig] = None


class ScheduledTask(BaseModel):
    """Full task document persisted in MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    name: str
    description: Optional[str] = None
    agent_id: str
    trigger_type: TriggerType
    trigger_config: dict
    timezone: str = "UTC"
    input_payload: dict
    status: ScheduledTaskStatus = ScheduledTaskStatus.ACTIVE
    enabled: bool = True
    run_on_start: bool = False
    max_retries: int = 0
    timeout_seconds: int = 3600
    owner_id: str = Field(..., description="Creator user_id")
    source_session_id: Optional[str] = None
    source_run_id: Optional[str] = None
    created_by: str = "user"
    delivery: Optional[ChannelDeliveryConfig] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[RunStatus] = None
    last_run_id: Optional[str] = None
    total_runs: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Run record models ──────────────────────────────


class TaskRunRecord(BaseModel):
    """Single execution record persisted in MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id", description="run_id (UUID)")
    task_id: str
    agent_id: str
    trigger_type: str = Field("cron", description="Trigger mode: cron / interval / date / manual")
    status: RunStatus = RunStatus.PENDING
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    input_snapshot: dict = Field(default_factory=dict)
    output_result: Any = None
    error_message: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None


# ── API responses ──────────────────────────────────


class ScheduledTaskResponse(BaseModel):
    """API response for a scheduled task."""

    id: str
    name: str
    description: Optional[str] = None
    agent_id: str
    trigger_type: TriggerType
    trigger_config: dict
    timezone: str = "UTC"
    input_payload: dict
    status: ScheduledTaskStatus
    enabled: bool
    run_on_start: bool
    max_retries: int
    timeout_seconds: int
    owner_id: str
    source_session_id: Optional[str] = None
    source_run_id: Optional[str] = None
    created_by: str = "user"
    delivery: Optional[ChannelDeliveryConfig] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[RunStatus] = None
    last_run_id: Optional[str] = None
    total_runs: int = 0
    unread_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaskRunResponse(BaseModel):
    """API response for a single task run."""

    id: str
    task_id: str
    agent_id: str
    trigger_type: str
    status: RunStatus
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    input_snapshot: dict
    output_result: Any = None
    error_message: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None


class TaskRunListResponse(BaseModel):
    """API response for paginated task run list."""

    items: list[TaskRunResponse]
    total: int


class ScheduledTaskListResponse(BaseModel):
    """API response for paginated scheduled task list."""

    items: list[ScheduledTaskResponse]
    total: int


# ── Task session responses ──────────────────────────


class TaskSessionResponse(BaseModel):
    """Lightweight session response for the scheduled-task drill-down."""

    id: str
    name: Optional[str] = None
    agent_id: str = "default"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    unread_count: int = 0


class TaskSessionListResponse(BaseModel):
    """API response for paginated task session list."""

    items: list[TaskSessionResponse]
    total: int

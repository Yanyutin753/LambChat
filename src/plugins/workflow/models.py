"""Models for the workflow plugin."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

WORKFLOW_MODEL_FORMAT = "lambchat.workflow.v1"


class WorkflowDefinition(BaseModel):
    workflow_id: str
    owner_user_id: str
    name: str
    description: str = ""
    status: Literal["draft", "published", "archived"] = "draft"
    latest_version_id: str | None = None
    published_version_id: str | None = None
    version_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkflowVersion(BaseModel):
    version_id: str
    workflow_id: str
    owner_user_id: str
    version_number: int
    source: Literal["workflow"] = "workflow"
    source_format: Literal["json", "yaml"] = "json"
    source_payload: dict[str, Any] = Field(default_factory=dict)
    internal_model: dict[str, Any] = Field(default_factory=dict)
    compatibility_report: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime


class WorkflowListResult(BaseModel):
    workflows: list[WorkflowDefinition]
    total: int


WorkflowRunStatus = Literal["queued", "running", "paused", "succeeded", "failed", "cancelled"]


class WorkflowRun(BaseModel):
    run_id: str
    workflow_id: str
    version_id: str
    owner_user_id: str
    status: WorkflowRunStatus = "queued"
    mode: Literal["sync", "async", "stream"] = "sync"
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    pause: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None


class WorkflowRunEvent(BaseModel):
    event_id: str
    run_id: str
    workflow_id: str
    version_id: str
    owner_user_id: str
    sequence: int
    event_type: str
    node_id: str | None = None
    node_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowCredential(BaseModel):
    credential_id: str
    owner_user_id: str
    ref: str
    type: str = "credential_ref"
    label: str = ""
    description: str = ""
    has_secret: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WorkflowRunResult(BaseModel):
    run: WorkflowRun
    events: list[WorkflowRunEvent] = Field(default_factory=list)

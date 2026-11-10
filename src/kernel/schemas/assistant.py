"""User-owned assistant identity, separate from its conversations and executions."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.kernel.schemas.persona_preset import PersonaStarterPrompt
from src.kernel.schemas.project import ProjectWorkspace

AssistantName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
ResourceId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]


class AssistantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: AssistantName
    description: str = Field(default="", max_length=500)
    avatar: str | None = None
    starter_prompts: list[PersonaStarterPrompt] = Field(default_factory=list)
    kind: Literal["assistant", "group", "chief"] = "assistant"
    member_ids: list[ResourceId] = Field(default_factory=list, max_length=12)
    leader_id: ResourceId | None = None
    instructions: str = Field(default="", max_length=20_000)
    model_id: ResourceId | None = None
    persona_preset_id: ResourceId | None = None
    team_id: ResourceId | None = None
    project_id: ResourceId | None = None
    memory_mode: Literal["private", "project"] = "private"
    sandbox: Literal["local", "cloud"] | None = None
    workspace: ProjectWorkspace | None = None

    @model_validator(mode="after")
    def validate_environment(self):
        if self.kind == "group":
            if len(self.member_ids) < 2 or len(set(self.member_ids)) != len(self.member_ids):
                raise ValueError("A group requires 2-12 distinct assistants")
            if self.leader_id not in self.member_ids:
                raise ValueError("The group coordinator must be a member")
            if self.team_id or self.persona_preset_id or self.memory_mode != "private":
                raise ValueError("Groups use their members and isolated group memory")
        elif self.member_ids or self.leader_id:
            raise ValueError("Only groups have members")
        if self.memory_mode == "project" and not self.project_id:
            raise ValueError("Shared assistant memory requires a project")
        if self.team_id and self.persona_preset_id:
            raise ValueError("Choose a persona or a team")
        if (self.sandbox == "local") != (self.workspace is not None):
            raise ValueError("A local environment requires a workspace picker receipt")
        return self


class AssistantUpdate(AssistantCreate):
    revision: int = Field(strict=True, ge=1)
    status: Literal["active", "paused", "archived"] = "active"


class AssistantActivity(BaseModel):
    state: Literal[
        "waiting_human",
        "running",
        "starting",
        "pending",
        "queued",
        "recovering",
        "cancelling",
        "completed",
        "failed",
        "cancelled",
        "expired",
    ]
    session_id: str
    preview: str | None = None
    updated_at: datetime
    unread_count: int = 0


class Assistant(AssistantCreate):
    activity: AssistantActivity | None = None
    context_kind: Literal["conversation", "task"] = "conversation"
    context_session_id: str | None = None
    context_task_id: str | None = None
    id: str
    user_id: str
    session_id: str
    revision: int
    status: Literal["active", "paused", "archived"]
    created_at: datetime
    updated_at: datetime


class AssistantList(BaseModel):
    assistants: list[Assistant]
    total: int
    skip: int
    limit: int


class AssistantTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID
    description: str = Field(min_length=1, max_length=20_000)
    timeout_seconds: int = Field(default=1800, strict=True, ge=30, le=86400)


class AssistantTaskReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: ResourceId
    accepted: bool = Field(strict=True)
    revision: int = Field(default=0, strict=True, ge=0)


class AssistantRulePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_id: ResourceId
    mode: Literal["off", "observe", "auto"] = "observe"
    event_task_id: ResourceId | None = None
    timeout_seconds: int = Field(default=300, strict=True, ge=30, le=3600)
    max_wakeups: int = Field(default=10, strict=True, ge=1, le=100)


class AssistantRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: AssistantName
    instructions: str = Field(min_length=1, max_length=18000)
    mode: Literal["off", "observe", "auto"] = "observe"
    interval_seconds: int = Field(default=3600, strict=True, ge=60, le=31536000)
    event_task_id: ResourceId | None = None
    timeout_seconds: int = Field(default=300, strict=True, ge=30, le=3600)
    max_wakeups: int = Field(default=10, strict=True, ge=1, le=100)

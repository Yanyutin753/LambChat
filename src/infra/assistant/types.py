"""Assistant domain models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssistantScope(str, Enum):
    """Assistant visibility scope."""

    PUBLIC = "public"
    PRIVATE = "private"


class AssistantRecord(BaseModel):
    """Stored assistant record."""

    assistant_id: str
    name: str
    description: str = ""
    system_prompt: str
    scope: AssistantScope = AssistantScope.PRIVATE
    created_by: str | None = None
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    category: str = "general"
    avatar_url: str | None = None
    cloned_from_assistant_id: str | None = None
    version: str = "1.0.0"
    bound_skill_names: list[str] = Field(default_factory=list)
    default_model: str | None = None
    default_agent_options: dict[str, Any] = Field(default_factory=dict)
    default_disabled_tools: list[str] = Field(default_factory=list)
    default_disabled_skills: list[str] = Field(default_factory=list)
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class AssistantCreate(BaseModel):
    """Create request for a private assistant."""

    name: str
    system_prompt: str
    description: str = ""
    scope: AssistantScope = AssistantScope.PRIVATE
    tags: list[str] = Field(default_factory=list)
    category: str = "general"
    avatar_url: str | None = None
    version: str = "1.0.0"
    bound_skill_names: list[str] = Field(default_factory=list)
    default_model: str | None = None
    default_agent_options: dict[str, Any] = Field(default_factory=dict)
    default_disabled_tools: list[str] = Field(default_factory=list)
    default_disabled_skills: list[str] = Field(default_factory=list)


class AssistantUpdate(BaseModel):
    """Partial update request for an assistant."""

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tags: list[str] | None = None
    category: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None
    version: str | None = None


class AssistantResponse(AssistantRecord):
    """Response shape for assistant APIs."""


class AssistantSelectRequest(BaseModel):
    """Bind an assistant to a session."""

    session_id: str

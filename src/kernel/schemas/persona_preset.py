"""Persona preset schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PersonaPresetScope(str, Enum):
    """Preset ownership scope."""

    GLOBAL = "global"
    USER = "user"


class PersonaPresetVisibility(str, Enum):
    """Preset visibility."""

    PUBLIC = "public"
    PRIVATE = "private"


class PersonaPresetStatus(str, Enum):
    """Preset publication status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PersonaPresetBase(BaseModel):
    """Common persona preset fields."""

    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    avatar: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    system_prompt: str = Field(..., min_length=1)
    skill_names: list[str] = Field(default_factory=list)
    scope: PersonaPresetScope = PersonaPresetScope.USER
    visibility: PersonaPresetVisibility = PersonaPresetVisibility.PRIVATE
    status: PersonaPresetStatus = PersonaPresetStatus.DRAFT

    @field_validator("tags", "skill_names")
    @classmethod
    def _dedupe_strings(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result


class PersonaPresetCreate(PersonaPresetBase):
    """Create persona preset request."""


class PersonaPresetUpdate(BaseModel):
    """Update persona preset request."""

    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=500)
    avatar: Optional[str] = None
    tags: Optional[list[str]] = None
    system_prompt: Optional[str] = Field(None, min_length=1)
    skill_names: Optional[list[str]] = None
    visibility: Optional[PersonaPresetVisibility] = None
    status: Optional[PersonaPresetStatus] = None

    @field_validator("tags", "skill_names")
    @classmethod
    def _dedupe_optional_strings(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return PersonaPresetBase._dedupe_strings(values)


class PersonaPreset(BaseModel):
    """Persona preset response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: PersonaPresetScope
    owner_user_id: Optional[str] = None
    name: str
    description: str = ""
    avatar: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    system_prompt: str
    skill_names: list[str] = Field(default_factory=list)
    visibility: PersonaPresetVisibility
    status: PersonaPresetStatus
    source_preset_id: Optional[str] = None
    copied_from_version: Optional[int] = None
    version: int = 1
    usage_count: int = 0
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PersonaPresetSnapshot(BaseModel):
    """Immutable runtime snapshot saved with a chat session."""

    preset_id: str
    name: str
    system_prompt: str
    skill_names: list[str] = Field(default_factory=list)
    missing_skill_names: list[str] = Field(default_factory=list)
    version: int = 1
    avatar: Optional[str] = None


class PersonaPresetListResponse(BaseModel):
    """Paginated persona preset list."""

    presets: list[PersonaPreset]
    total: int
    skip: int = 0
    limit: int = 100

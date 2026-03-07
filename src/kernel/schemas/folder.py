"""Folder-related schemas for session organization."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FolderBase(BaseModel):
    """Base folder schema."""

    name: str
    type: str = "custom"  # "favorites" or "custom"
    sort_order: int = 0


class FolderCreate(FolderBase):
    """Schema for creating a folder."""

    pass


class FolderUpdate(BaseModel):
    """Schema for updating a folder."""

    name: Optional[str] = None
    sort_order: Optional[int] = None


class Folder(FolderBase):
    """Folder model."""

    id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True

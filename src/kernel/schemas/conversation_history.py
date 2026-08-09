"""Schemas shared by conversation history and memory source references."""

from pydantic import BaseModel, ConfigDict, Field


class ConversationSourceRef(BaseModel):
    """A stable pointer from durable memory to one persisted conversation run."""

    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)

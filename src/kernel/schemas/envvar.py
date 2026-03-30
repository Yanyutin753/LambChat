"""
Environment Variable schemas for API request/response
"""

from typing import Optional

from pydantic import BaseModel, Field


class EnvVarCreate(BaseModel):
    """Schema for creating a new environment variable"""

    key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Environment variable name (must start with letter or underscore)",
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Environment variable value",
    )


class EnvVarUpdate(BaseModel):
    """Schema for updating an environment variable"""

    value: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Environment variable value",
    )


class EnvVarResponse(BaseModel):
    """Single environment variable response"""

    key: str
    value: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EnvVarListResponse(BaseModel):
    """List of environment variables"""

    variables: list[EnvVarResponse] = Field(default_factory=list)
    count: int = 0


class EnvVarBulkUpdateRequest(BaseModel):
    """Bulk upsert environment variables"""

    variables: dict[str, str] = Field(
        ...,
        description="Key-value pairs to upsert (key must match ^[A-Za-z_][A-Za-z0-9_]*$)",
    )


class EnvVarBulkUpdateResponse(BaseModel):
    """Response after bulk updating"""

    updated_count: int
    message: str

"""Model-related schemas."""

from typing import Optional

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Model configuration (global)."""

    id: str = Field(..., description="Model ID (the 'value' from LLM_AVAILABLE_MODELS)")
    name: str = Field(..., description="Model display name (the 'label')")
    description: str = Field("", description="Model description")
    enabled: bool = Field(True, description="Whether the model is enabled globally")


class ModelConfigUpdate(BaseModel):
    """Update global model configuration."""

    models: list[ModelConfig] = Field(..., description="List of model configurations")


class GlobalModelConfigResponse(BaseModel):
    """Response for global model config."""

    models: list[ModelConfig] = Field(..., description="All models with enabled status")
    available_models: list[str] = Field(..., description="List of enabled model IDs")


# ============================================
# Role Model Schemas
# ============================================


class RoleModelAssignment(BaseModel):
    """Role's accessible models."""

    role_id: str = Field(..., description="Role ID")
    role_name: str = Field(..., description="Role name")
    allowed_models: list[str] = Field(default_factory=list, description="List of allowed model IDs")


class RoleModelAssignmentUpdate(BaseModel):
    """Update role's accessible models."""

    allowed_models: list[str] = Field(..., description="List of allowed model IDs")


class RoleModelAssignmentResponse(BaseModel):
    """Response after updating role's accessible models."""

    role_id: str = Field(..., description="Role ID")
    role_name: str = Field(..., description="Role name")
    allowed_models: list[str] = Field(default_factory=list, description="List of allowed model IDs")


# ============================================
# User Allowed Models
# ============================================


class UserAllowedModelsResponse(BaseModel):
    """Response for user's allowed models."""

    models: list[str] = Field(..., description="List of model IDs the user can access")

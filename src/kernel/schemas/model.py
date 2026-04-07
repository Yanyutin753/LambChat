"""Model-related schemas."""

from typing import Optional

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Model configuration item (inside a provider group)."""

    value: str = Field(..., description="Model ID/value (unique identifier)")
    label: str = Field(..., description="Model display name")
    description: str = Field("", description="Model description")
    enabled: bool = Field(True, description="Whether the model is enabled globally")
    provider: Optional[str] = Field(
        None, description="Provider name this model belongs to (for flat_models)"
    )


class ModelProviderConfig(BaseModel):
    """Provider group with its credentials and models."""

    provider: str = Field(..., description="Provider name (anthropic/openai/google/minimax/zai)")
    label: str = Field(..., description="Provider display name")
    base_url: Optional[str] = Field(None, description="API base URL override for this provider")
    api_key: Optional[str] = Field(None, description="API key for this provider (stored encrypted)")
    # Per-provider defaults (can be overridden per-request)
    temperature: float = Field(0.7, description="Default temperature for this provider")
    max_tokens: int = Field(4096, description="Default max tokens for this provider")
    max_retries: int = Field(3, description="Max retries for this provider")
    retry_delay: float = Field(1.0, description="Base retry delay in seconds")
    models: list[ModelConfig] = Field(
        default_factory=list, description="Models in this provider group"
    )


class ProviderModelConfigResponse(BaseModel):
    """Response for provider-based model config."""

    providers: list[ModelProviderConfig] = Field(..., description="All provider groups")
    flat_models: list[ModelConfig] = Field(
        ..., description="All models flattened (for backwards compat)"
    )
    available_models: list[str] = Field(..., description="List of enabled model IDs")


class ProviderModelConfigUpdate(BaseModel):
    """Update provider-based model configuration."""

    providers: list[ModelProviderConfig] = Field(..., description="Provider groups with models")


# ============================================
# Legacy/Compat Schemas (deprecated, kept for migration)
# ============================================


class ModelConfigLegacy(BaseModel):
    """Legacy model config (deprecated - use ModelConfig in provider)."""

    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Model display name")
    description: str = Field("", description="Model description")
    enabled: bool = Field(True, description="Whether the model is enabled globally")


class ModelConfigUpdate(BaseModel):
    """Update global model configuration (legacy - deprecated)."""

    models: list[ModelConfigLegacy] = Field(..., description="List of model configurations")


class GlobalModelConfigResponse(BaseModel):
    """Response for global model config (legacy - deprecated)."""

    models: list[ModelConfigLegacy] = Field(..., description="All models with enabled status")
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

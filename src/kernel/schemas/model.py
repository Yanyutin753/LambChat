"""Model-related schemas."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ============================================
# Provider Schemas
# ============================================


class ProviderConfig(BaseModel):
    """Provider configuration with API credentials."""

    name: str = Field(..., description="Provider name (e.g., openai, anthropic, deepseek)")
    display_name: str = Field("", description="Human-readable provider name")
    api_key: Optional[str] = Field(None, description="Provider-level API key")
    api_base: Optional[str] = Field(None, description="Provider-level API base URL")
    enabled: bool = Field(True, description="Whether the provider is enabled")


class ProviderConfigUpdate(BaseModel):
    """Update provider configurations."""

    providers: list[ProviderConfig] = Field(..., description="List of provider configurations")


# ============================================
# Model Config Schemas
# ============================================


class ModelConfig(BaseModel):
    """Model configuration (global)."""

    id: str = Field(..., description="Model ID (format: provider/model_name)")
    name: str = Field(..., description="Model display name (the 'label')")
    description: str = Field("", description="Model description")
    enabled: bool = Field(True, description="Whether the model is enabled globally")
    api_key: Optional[str] = Field(None, description="Per-model API key (overrides provider)")
    api_base: Optional[str] = Field(None, description="Per-model API base URL (overrides provider)")


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


# ============================================
# LLM Provider Schemas (Custom Provider System)
# ============================================


class ProviderType(str, Enum):
    """Determines which LangChain chat model class to use."""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC_COMPATIBLE = "anthropic_compatible"
    GOOGLE_COMPATIBLE = "google_compatible"


class LLMProviderModel(BaseModel):
    """A model entry within an LLM provider."""

    id: str = Field(..., description="Full model ID (format: provider_name/model_name)")
    name: str = Field(..., description="Display name shown in UI")
    model_name: str = Field("", description="Actual model name sent to the API")
    description: str = Field("", description="Model description")
    enabled: bool = Field(True, description="Whether this model is enabled")
    supports_thinking: bool = Field(False, description="Whether model supports extended thinking")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")


class LLMProviderCreate(BaseModel):
    """Schema for creating a new custom LLM provider."""

    name: str = Field(
        ...,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description="Unique provider identifier (lowercase alphanumeric, hyphens, underscores)",
    )
    display_name: str = Field(..., min_length=1, description="Human-readable provider name")
    provider_type: ProviderType = Field(..., description="Which API protocol to use")
    api_key: Optional[str] = Field(None, description="Provider-level API key")
    api_base: Optional[str] = Field(None, description="Provider-level API base URL")
    enabled: bool = Field(True, description="Whether the provider is enabled")
    models: list[LLMProviderModel] = Field(default_factory=list, description="Initial model list")
    color: str = Field("#78716C", description="Brand color hex for UI")


class LLMProviderUpdate(BaseModel):
    """Schema for updating an existing LLM provider."""

    display_name: Optional[str] = Field(None, min_length=1)
    provider_type: Optional[ProviderType] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    enabled: Optional[bool] = None
    models: Optional[list[LLMProviderModel]] = None
    color: Optional[str] = None


class LLMProvider(BaseModel):
    """Full LLM provider response."""

    name: str
    display_name: str
    provider_type: ProviderType
    enabled: bool
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    models: list[LLMProviderModel]
    is_builtin: bool = False
    builtin_provider_name: Optional[str] = None
    color: str = "#78716C"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LLMProvidersResponse(BaseModel):
    """Response for listing all LLM providers."""

    providers: list[LLMProvider]
    available_models: list[str] = Field(
        default_factory=list, description="Flat list of all enabled model IDs"
    )


class LLMProviderTestRequest(BaseModel):
    """Request body for testing a provider connection."""

    model_name: Optional[str] = Field(None, description="Specific model name to test")


class LLMProviderTestResponse(BaseModel):
    """Response for provider connection test."""

    success: bool
    error: Optional[str] = None
    latency_ms: Optional[int] = None

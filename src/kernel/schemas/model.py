"""Model-related schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelProfile(BaseModel):
    """Per-model profile configuration."""

    model_config = ConfigDict(extra="ignore")

    max_input_tokens: Optional[int] = Field(None, description="Max input tokens for this model")


class ModelConfig(BaseModel):
    """Model configuration stored in database."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, description="Model ID (auto-generated if not provided)")
    value: str = Field(..., description="Model identifier (e.g., anthropic/claude-3-5-sonnet)")
    provider: Optional[str] = Field(
        None,
        description="Explicit LLM provider (e.g. openai/anthropic/google/deepseek). Auto-detected from value if not set.",
    )
    label: str = Field(..., description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    fallback_model: Optional[str] = Field(
        None, description="Fallback model ID (UUID) when this model fails"
    )
    enabled: bool = Field(True, description="Whether this model is enabled")
    order: int = Field(0, description="Display order")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class ModelConfigCreate(BaseModel):
    """Create a new model configuration."""

    value: str = Field(..., description="Model identifier (e.g., anthropic/claude-3-5-sonnet)")
    provider: Optional[str] = Field(
        None,
        description="Explicit LLM provider (e.g. openai/anthropic/google/deepseek). Auto-detected from value if not set.",
    )
    label: str = Field(..., description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    fallback_model: Optional[str] = Field(
        None, description="Fallback model ID (UUID) when this model fails"
    )
    enabled: bool = Field(True, description="Whether this model is enabled")
    order: Optional[int] = Field(0, description="Display order")


class ModelConfigUpdate(BaseModel):
    """Update an existing model configuration."""

    provider: Optional[str] = Field(None, description="Explicit LLM provider override")
    label: Optional[str] = Field(None, description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    fallback_model: Optional[str] = Field(
        None, description="Fallback model ID (UUID) when this model fails"
    )
    enabled: Optional[bool] = Field(None, description="Whether this model is enabled")
    order: Optional[int] = Field(None, description="Display order")


class ModelListResponse(BaseModel):
    """Response for listing all models."""

    models: list[ModelConfig] = Field(
        default_factory=list, description="List of model configurations"
    )
    count: int = Field(0, description="Total number of models")
    enabled_count: int = Field(0, description="Number of enabled models")


def mask_api_key(model: ModelConfig) -> ModelConfig:
    """Return a copy of the model with the API key masked for safe display."""
    if model.api_key:
        key = model.api_key
        masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"
        return model.model_copy(update={"api_key": masked})
    return model


class ModelResponse(BaseModel):
    """Response for a single model operation."""

    model: ModelConfig = Field(..., description="The model configuration")
    message: Optional[str] = Field(None, description="Optional success message")

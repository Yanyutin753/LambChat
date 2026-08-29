"""Model-related schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Wire format for OpenAI-protocol providers: classic /chat/completions or the
# newer /responses endpoint. Per-model override; falls back to the
# LLM_OPENAI_API_FORMAT global setting.
ApiFormat = Literal["chat_completions", "responses"]


class ModelProfile(BaseModel):
    """Per-model profile configuration."""

    model_config = ConfigDict(extra="ignore")

    max_input_tokens: Optional[int] = Field(None, description="Max input tokens for this model")
    supports_vision: Optional[bool] = Field(
        False,
        description="Whether this model accepts image input",
    )
    image_url_to_base64: Optional[bool] = Field(
        False,
        description="Whether image_url blocks should be converted to base64 data URLs before model calls",
    )


class ModelPricingOverride(BaseModel):
    """Per-model USD pricing override (per 1M tokens).

    覆盖 models.dev 同步价格（中转站等价格不一致场景）；
    字段级生效：未填写的档位沿用同步价格（若有匹配）。
    """

    model_config = ConfigDict(extra="ignore")

    input: Optional[float] = Field(None, description="Input price (USD / 1M tokens)")
    output: Optional[float] = Field(None, description="Output price (USD / 1M tokens)")
    cache_read: Optional[float] = Field(None, description="Cache read price (USD / 1M tokens)")
    cache_write: Optional[float] = Field(None, description="Cache write price (USD / 1M tokens)")


class ModelConfig(BaseModel):
    """Model configuration stored in database."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, description="Model ID (auto-generated if not provided)")
    value: str = Field(..., description="Model identifier (e.g., anthropic/claude-3-5-sonnet)")
    provider: Optional[str] = Field(
        None,
        description="Explicit LLM provider (e.g. openai/anthropic/google/deepseek). Auto-detected from value if not set.",
    )
    icon: Optional[str] = Field(
        None,
        description="Explicit display icon slug. Falls back to provider/model inference when not set.",
    )
    label: str = Field(..., description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    api_format: Optional[ApiFormat] = Field(
        None,
        description="Wire format for OpenAI-protocol providers (chat_completions | responses)",
    )
    request_headers: Optional[dict[str, str]] = Field(
        None,
        description="Per-model HTTP header overrides merged over the anti-ban defaults",
    )
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    pricing: Optional[ModelPricingOverride] = Field(
        None, description="Per-model USD pricing override (per 1M tokens)"
    )
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
    icon: Optional[str] = Field(
        None,
        description="Explicit display icon slug. Falls back to provider/model inference when not set.",
    )
    label: str = Field(..., description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    api_format: Optional[ApiFormat] = Field(
        None,
        description="Wire format for OpenAI-protocol providers (chat_completions | responses)",
    )
    request_headers: Optional[dict[str, str]] = Field(
        None,
        description="Per-model HTTP header overrides merged over the anti-ban defaults",
    )
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    pricing: Optional[ModelPricingOverride] = Field(
        None, description="Per-model USD pricing override (per 1M tokens)"
    )
    fallback_model: Optional[str] = Field(
        None, description="Fallback model ID (UUID) when this model fails"
    )
    enabled: bool = Field(True, description="Whether this model is enabled")
    order: Optional[int] = Field(0, description="Display order")


class ModelConfigUpdate(BaseModel):
    """Update an existing model configuration."""

    provider: Optional[str] = Field(None, description="Explicit LLM provider override")
    icon: Optional[str] = Field(None, description="Explicit display icon slug override")
    label: Optional[str] = Field(None, description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    api_key: Optional[str] = Field(None, description="Per-model API key override")
    api_base: Optional[str] = Field(None, description="Per-model API base URL override")
    # "" 表示清除覆盖、恢复「跟随默认」（与 api_key 的清空语义一致，路由会映射为 None）
    api_format: Optional[Literal["chat_completions", "responses", ""]] = Field(
        None,
        description="Wire format for OpenAI-protocol providers (chat_completions | responses)",
    )
    # null / {} 表示清除覆盖、回落全局设置与内置防封默认头
    request_headers: Optional[dict[str, str]] = Field(
        None,
        description="Per-model HTTP header overrides merged over the anti-ban defaults",
    )
    temperature: Optional[float] = Field(None, description="Per-model temperature override")
    max_tokens: Optional[int] = Field(None, description="Per-model max tokens override")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    pricing: Optional[ModelPricingOverride] = Field(
        None, description="Per-model USD pricing override (per 1M tokens)"
    )
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


class AvailableModel(BaseModel):
    """Public model information safe for non-admin model selectors."""

    id: Optional[str] = Field(None, description="Model ID")
    value: str = Field(..., description="Model identifier")
    provider: Optional[str] = Field(None, description="LLM provider")
    icon: Optional[str] = Field(None, description="Explicit display icon slug")
    label: str = Field(..., description="Display name for the model")
    description: Optional[str] = Field(None, description="Model description")
    profile: Optional[ModelProfile] = Field(None, description="Per-model profile settings")
    supports_thinking: Optional[bool] = Field(
        None,
        description="Computed per request from the LLM client capability gates; not persisted",
    )


class AvailableModelListResponse(BaseModel):
    """Response for listing models visible to the current user."""

    models: list[AvailableModel] = Field(
        default_factory=list, description="List of public model entries"
    )
    count: int = Field(0, description="Number of visible models")
    enabled_count: int = Field(0, description="Number of visible enabled models")
    default_model_id: Optional[str] = Field(
        None,
        description="Effective default model ID for this user's visible model set",
    )


def to_available_model(model: ModelConfig) -> AvailableModel:
    """Return a public model view without credentials or routing internals."""
    return AvailableModel(
        id=model.id,
        value=model.value,
        provider=model.provider,
        icon=model.icon,
        label=model.label,
        description=model.description,
        profile=model.profile,
    )


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

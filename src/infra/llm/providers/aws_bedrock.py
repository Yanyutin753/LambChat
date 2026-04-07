"""
AWS Bedrock provider.
"""

from typing import Any, Optional

from src.infra.llm.providers.registry import (
    BaseLLMProvider,
    ProviderConfig,
    ProviderModelInfo,
    PROVIDER_BRAND_COLORS,
    ProviderUIMeta,
)
from src.kernel.config import settings


class AWSBedrockProvider(BaseLLMProvider):
    """AWS Bedrock - Claude, Llama, Mistral, etc. via AWS Bedrock."""

    name = "bedrock"
    display_name = "AWS Bedrock"
    category = "aws_compatible"
    langchain_class_path = "langchain_aws.ChatBedrock"
    ui_meta = ProviderUIMeta(
        icon="aws",
        color=PROVIDER_BRAND_COLORS["bedrock"],
        website="https://aws.amazon.com/bedrock",
        description="Amazon's managed service for AI models - Claude, Llama, Mistral",
    )

    default_models = [
        # Anthropic on Bedrock
        ProviderModelInfo(
            model_id="anthropic.claude-3-5-sonnet-20241022-v1:0",
            aliases=["anthropic.claude-3-5-sonnet-v1", "bedrock-claude-3-5-sonnet"],
            supports_thinking=True,
            max_tokens=8192,
        ),
        ProviderModelInfo(
            model_id="anthropic.claude-3-opus-20240229-v1:0",
            aliases=["anthropic.claude-3-opus-v1"],
            supports_thinking=True,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            aliases=["anthropic.claude-3-sonnet-v1"],
            supports_thinking=True,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            aliases=["anthropic.claude-3-haiku-v1"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        # Meta Llama on Bedrock
        ProviderModelInfo(
            model_id="meta.llama3-70b-instruct-v1:0",
            aliases=["meta.llama3-70b-instruct", "llama-3-70b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="meta.llama3-8b-instruct-v1:0",
            aliases=["meta.llama3-8b-instruct", "llama-3-8b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        # Mistral on Bedrock
        ProviderModelInfo(
            model_id="mistral.mixtral-8x7b-instruct-v0:1",
            aliases=["mistral.mixtral-8x7b", "mixtral-8x7b"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        # AI21 Jurassic on Bedrock
        ProviderModelInfo(
            model_id="ai21.j2-mid-v1",
            aliases=["ai21.j2-mid"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        # Cohere on Bedrock
        ProviderModelInfo(
            model_id="cohere.command-r-plus-v1:0",
            aliases=["cohere.command-r-plus"],
            supports_thinking=False,
            max_tokens=4096,
        ),
        ProviderModelInfo(
            model_id="cohere.command-r-v1:0",
            aliases=["cohere.command-r"],
            supports_thinking=False,
            max_tokens=4096,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    @classmethod
    def matches_model(cls, model_id: str) -> bool:
        prefixes = ["anthropic.", "meta.", "mistral.", "ai21.", "cohere.", "amazon."]
        return any(model_id.startswith(p) for p in prefixes) or "bedrock" in model_id.lower()

    def matches_url(self, base_url: str) -> bool:
        if not base_url:
            return False
        return "bedrock" in base_url.lower() or "amazonaws" in base_url.lower()

    def _build_langchain_kwargs(
        self,
        model_name: str,
        *,
        temperature: float,
        max_tokens: Optional[int],
        thinking: Optional[dict],
        profile: Optional[dict],
        **kwargs: Any,
    ) -> dict[str, Any]:
        # AWS Bedrock uses boto3 session, not direct API key
        # The api_key in config is actually AWS access key (or uses default credential chain)
        # base_url can be overridden for testing
        return {
            "model_id": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            # AWS Bedrock via langchain-aws uses credentials from boto3 session
            # Model_kwargs can include additional params
            "profile": profile,
            "max_retries": kwargs.get("max_retries", getattr(settings, "LLM_MAX_RETRIES", 3)),
        }

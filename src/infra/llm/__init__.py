"""
LLM 客户端模块
"""

from src.infra.llm.deepagents_patch import apply_deepagents_patches
from src.infra.llm.openai_compat_patch import apply_openai_compatible_patches
from src.infra.llm.reasoning_patch import apply_reasoning_patches

apply_reasoning_patches()
apply_openai_compatible_patches()
apply_deepagents_patches()

from src.infra.llm.client import LLMClient, get_llm_client  # noqa: E402
from src.infra.llm.models_service import (  # noqa: E402
    get_available_models,
    invalidate_cache,
    refresh_models,
)
from src.infra.llm.pubsub import (  # noqa: E402
    get_model_config_pubsub,
    publish_model_config_changed,
)

__all__ = [
    "LLMClient",
    "get_llm_client",
    "get_available_models",
    "invalidate_cache",
    "refresh_models",
    "get_model_config_pubsub",
    "publish_model_config_changed",
]

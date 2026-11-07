"""Per-request model access and sanitized worker configuration."""

from src.infra.logging import get_logger
from src.kernel.exceptions import AuthorizationError
from src.kernel.schemas.model import ModelConfig, effective_image_url_mode
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)


def _model_profile_dict(model: ModelConfig) -> dict | None:
    if not model.profile:
        return None
    return (
        model.profile.model_dump() if hasattr(model.profile, "model_dump") else dict(model.profile)
    )


def _safe_model_config_dict(model: ModelConfig) -> dict:
    return model.model_copy(update={"api_key": None}).model_dump(mode="json")


async def _attach_resolved_model_options(
    agent_options: dict, model: ModelConfig, allowed_model_ids: list[str] | None
) -> None:
    """Attach runtime-only model details after checking the effective model scope."""
    agent_options["model_id"] = model.id
    agent_options["model"] = model.value
    agent_options["_resolved_model_config"] = _safe_model_config_dict(model)
    agent_options["_resolved_supports_vision"] = bool(
        getattr(model.profile, "supports_vision", False)
    )
    agent_options["_resolved_image_url_mode"] = effective_image_url_mode(model.profile)
    if model.api_key:
        from src.infra.llm.models_service import set_cached_api_key

        set_cached_api_key(model.value, model.api_key)

    fallback_value = None
    if model.fallback_model:
        from src.infra.agent.model_storage import get_model_storage

        try:
            fallback = await get_model_storage().get(model.fallback_model)
            if (
                fallback
                and fallback.enabled
                and (
                    allowed_model_ids is None
                    or fallback.id in allowed_model_ids
                    or fallback.value in allowed_model_ids
                )
            ):
                fallback_value = fallback.value
        except Exception as e:
            logger.warning("Failed to resolve fallback model %s: %s", model.fallback_model, e)
    agent_options["_resolved_fallback_model"] = fallback_value
    agent_options["_resolved_model_profile"] = _model_profile_dict(model)


async def validate_agent_model_access(
    agent_options: dict | None,
    user: TokenPayload,
) -> None:
    """Validate per-request model selection against enabled models and role access."""
    if agent_options is None:
        agent_options = {}
    # Only the executor/recovery path may supply cumulative handoff accounting.
    agent_options.pop("_handoff_usage", None)
    for key in list(agent_options):
        if key.startswith("_resolved_"):
            agent_options.pop(key)

    model_id = agent_options.get("model_id")
    selected_model = agent_options.get("model")

    from src.infra.agent.model_storage import get_model_storage

    storage = get_model_storage()
    from src.infra.agent.model_access import resolve_user_allowed_model_ids

    allowed_model_ids = await resolve_user_allowed_model_ids(user)

    if not model_id and not selected_model:
        if allowed_model_ids is None:
            return
        # 批量解析 allowed 模型（一次 $in 查询），逐个 get/get_by_value 是 N+1
        by_id, by_value = await storage.get_many_by_ids_and_values(allowed_model_ids)
        for allowed_model_id in allowed_model_ids:
            model = by_id.get(allowed_model_id)
            if model is None:
                model = by_value.get(allowed_model_id)
            if model and model.enabled:
                await _attach_resolved_model_options(agent_options, model, allowed_model_ids)
                return
        raise AuthorizationError("model_disabled")

    model = None
    if isinstance(model_id, str) and model_id:
        model = await storage.get(model_id)
    elif isinstance(selected_model, str) and selected_model:
        model = await storage.get_by_value(selected_model)

    if not model or not model.enabled:
        raise AuthorizationError("model_not_found" if not model else "model_disabled")

    allowed_model_set = set(allowed_model_ids or [])
    if allowed_model_ids is not None and (
        model.id not in allowed_model_set and model.value not in allowed_model_set
    ):
        raise AuthorizationError("model_not_allowed")

    await _attach_resolved_model_options(agent_options, model, allowed_model_ids)

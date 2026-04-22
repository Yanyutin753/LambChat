"""Prompt builder for user environment variable keys.

Only variable names are exposed to the model. Values stay encrypted in storage
and are injected into sandbox command execution by the backend.
"""

import time

from src.infra.envvar.storage import EnvVarStorage
from src.infra.logging import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 300
_env_var_prompt_cache: dict[str, tuple[str, float]] = {}


async def build_env_var_prompt(user_id: str, force_refresh: bool = False) -> str:
    """Build a prompt section listing environment variable keys for a user."""
    if not user_id:
        return ""

    _cleanup_stale_cache()
    if not force_refresh and user_id in _env_var_prompt_cache:
        prompt, ts = _env_var_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            return prompt

    try:
        variables = await EnvVarStorage().list_vars(user_id)
    except Exception:
        logger.warning(
            "[EnvVar Prompt] Failed to list env vars for user %s", user_id, exc_info=True
        )
        return ""

    keys = sorted(variable.key for variable in variables if getattr(variable, "key", ""))
    if not keys:
        prompt = ""
    else:
        lines = [
            "## Available Environment Variables",
            "",
            "The following environment variables are configured for sandbox execution. "
            "Their secret contents are not shown. Use the names directly in shell commands "
            "or code, for example `$FIRECRAWL_API_KEY` in shell or "
            '`os.environ.get("FIRECRAWL_API_KEY")` in Python. Do not print or reveal secrets.',
            "",
        ]
        lines.extend(f"- `{key}`" for key in keys)
        prompt = "\n".join(lines)

    _env_var_prompt_cache[user_id] = (prompt, time.time())
    return prompt


def invalidate_env_var_prompt_cache(user_id: str) -> None:
    """Invalidate cached env-var prompt for one user."""
    _env_var_prompt_cache.pop(user_id, None)


def _cleanup_stale_cache() -> None:
    now = time.time()
    stale = [user_id for user_id, (_, ts) in _env_var_prompt_cache.items() if now - ts > _CACHE_TTL]
    for user_id in stale:
        del _env_var_prompt_cache[user_id]

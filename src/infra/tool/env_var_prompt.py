"""Prompt builder for user environment variable keys.

Only variable names are exposed to the model. Values stay encrypted in storage
and are injected into sandbox command execution by the backend.
"""

import time

from src.infra.envvar.storage import EnvVarStorage
from src.infra.logging import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 300
_MAX_PROMPT_CACHE_ENTRIES = 500
_env_var_prompt_cache: dict[str, tuple[tuple[str, ...], float]] = {}


async def build_env_var_prompt_sections(
    user_id: str, force_refresh: bool = False
) -> tuple[str, ...]:
    """Build prompt sections listing environment variable keys for a user."""
    if not user_id:
        return ()

    _cleanup_stale_cache()
    if not force_refresh and user_id in _env_var_prompt_cache:
        prompt_sections, ts = _env_var_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            return prompt_sections

    try:
        variables = await EnvVarStorage().list_vars(user_id)
    except Exception:
        logger.warning(
            "[EnvVar Prompt] Failed to list env vars for user %s", user_id, exc_info=True
        )
        return ()

    keys = sorted(variable.key for variable in variables if getattr(variable, "key", ""))
    if not keys:
        prompt_sections = ()
    else:
        intro_lines = [
            "## Available Environment Variables",
            "",
            'Names only; values are secret. Reference `$KEY` or `os.environ.get("KEY")`; '
            "never print or reveal values.",
        ]
        key_lines = [f"- `{key}`" for key in keys]
        prompt_sections = ("\n".join(intro_lines), "\n".join(key_lines))

    _env_var_prompt_cache[user_id] = (prompt_sections, time.time())
    return prompt_sections


async def build_env_var_prompt(user_id: str, force_refresh: bool = False) -> str:
    """Build a prompt section listing environment variable keys for a user."""
    return "\n\n".join(await build_env_var_prompt_sections(user_id, force_refresh))


def invalidate_env_var_prompt_cache(user_id: str) -> None:
    """Invalidate cached env-var prompt for one user."""
    _env_var_prompt_cache.pop(user_id, None)


def _cleanup_stale_cache() -> None:
    now = time.time()
    stale = [user_id for user_id, (_, ts) in _env_var_prompt_cache.items() if now - ts > _CACHE_TTL]
    for user_id in stale:
        del _env_var_prompt_cache[user_id]
    _cleanup_excess_prompt_cache_entries()


def _cleanup_excess_prompt_cache_entries() -> int:
    max_entries = max(int(_MAX_PROMPT_CACHE_ENTRIES), 1)
    if len(_env_var_prompt_cache) <= max_entries:
        return 0

    to_remove = len(_env_var_prompt_cache) - max_entries
    oldest = sorted(
        _env_var_prompt_cache.items(),
        key=lambda item: item[1][1],
    )[:to_remove]
    for user_id, _entry in oldest:
        _env_var_prompt_cache.pop(user_id, None)
    return len(oldest)

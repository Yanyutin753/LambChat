"""LLM-callable environment variable tools.

The tools allow the agent to manage the current user's encrypted environment
variables without ever reading plaintext values back into model context.
"""

import json
import re
import sys
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool
from pydantic import BaseModel, Field

from src.infra.envvar.storage import EnvVarStorage
from src.infra.tool.backend_utils import get_user_id_from_runtime
from src.infra.tool.env_var_prompt import invalidate_env_var_prompt_cache
from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]


_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _ListInput(BaseModel):
    pass


class _SetInput(BaseModel):
    key: str = Field(
        ...,
        description="Environment variable key. Must match ^[A-Za-z_][A-Za-z0-9_]*$.",
    )
    value: str = Field(..., description="Environment variable value to store encrypted.")


class _DeleteInput(BaseModel):
    key: str = Field(
        ...,
        description="Environment variable key. Must match ^[A-Za-z_][A-Za-z0-9_]*$.",
    )


class _DeleteAllInput(BaseModel):
    pass


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _get_user_id(runtime: ToolRuntime) -> str | None:
    user_id = get_user_id_from_runtime(runtime)
    return user_id if user_id else None


async def _sync_current_sandbox(runtime: ToolRuntime, user_id: str) -> None:
    from src.infra.tool.backend_utils import get_backend_from_runtime

    backend = get_backend_from_runtime(runtime)
    if backend is not None:
        await ensure_sandbox_mcp(backend, user_id)


def _validate_key(key: str) -> str | None:
    if _ENV_KEY_PATTERN.match(key):
        return None
    return "Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$"


def _masked_var(variable: Any) -> dict[str, Any]:
    return {
        "key": variable.key,
        "value": "***",
        "created_at": variable.created_at,
        "updated_at": variable.updated_at,
    }


async def _env_var_list(runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str:
    user_id = _get_user_id(runtime)
    if not user_id:
        return _json({"error": "No user context available"})

    variables = await EnvVarStorage().list_vars(user_id)
    masked = [_masked_var(variable) for variable in variables]
    return _json({"variables": masked, "count": len(masked)})


async def _env_var_set(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    key: str,
    value: str,
) -> str:
    user_id = _get_user_id(runtime)
    if not user_id:
        return _json({"error": "No user context available"})

    validation_error = _validate_key(key)
    if validation_error:
        return _json({"error": validation_error})

    variable = await EnvVarStorage().set_var(user_id, key, value)
    invalidate_env_var_prompt_cache(user_id)
    await _sync_current_sandbox(runtime, user_id)
    return _json(
        {
            "success": True,
            "message": f"Environment variable '{key}' saved",
            "variable": _masked_var(variable),
        }
    )


async def _env_var_delete(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    key: str,
) -> str:
    user_id = _get_user_id(runtime)
    if not user_id:
        return _json({"error": "No user context available"})

    validation_error = _validate_key(key)
    if validation_error:
        return _json({"error": validation_error})

    deleted = await EnvVarStorage().delete_var(user_id, key)
    if not deleted:
        return _json({"error": f"Environment variable '{key}' not found"})
    invalidate_env_var_prompt_cache(user_id)
    await _sync_current_sandbox(runtime, user_id)
    return _json({"success": True, "message": f"Environment variable '{key}' deleted"})


async def _env_var_delete_all(runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str:
    user_id = _get_user_id(runtime)
    if not user_id:
        return _json({"error": "No user context available"})

    count = await EnvVarStorage().delete_all_vars(user_id)
    invalidate_env_var_prompt_cache(user_id)
    await _sync_current_sandbox(runtime, user_id)
    return _json(
        {
            "success": True,
            "message": f"Deleted {count} environment variable(s)",
            "deleted_count": count,
        }
    )


def get_env_var_tools() -> list[BaseTool]:
    """Return safe environment variable CRUD tools for the current user."""
    return [
        StructuredTool(
            name="env_var_list",
            description=(
                "List the current user's saved environment variable keys. "
                "Values are always masked and plaintext secrets are never returned."
            ),
            args_schema=_ListInput,
            func=None,
            coroutine=_env_var_list,
        ),
        StructuredTool(
            name="env_var_set",
            description=(
                "Create or update one encrypted environment variable for the current user. "
                "Use this when configuring sandbox MCP env_keys. The saved value is never "
                "returned; responses contain only a masked value."
            ),
            args_schema=_SetInput,
            func=None,
            coroutine=_env_var_set,
        ),
        StructuredTool(
            name="env_var_delete",
            description="Delete one environment variable for the current user by key.",
            args_schema=_DeleteInput,
            func=None,
            coroutine=_env_var_delete,
        ),
        StructuredTool(
            name="env_var_delete_all",
            description=(
                "Delete all environment variables for the current user. Use only when the "
                "user explicitly asks to clear all environment variables."
            ),
            args_schema=_DeleteAllInput,
            func=None,
            coroutine=_env_var_delete_all,
        ),
    ]

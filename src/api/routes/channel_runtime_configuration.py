"""Normalize non-secret execution options and authorize explicit local machines."""

from typing import Any

from src.infra.channel.runtime import normalize_runtime_config
from src.kernel.errors import AppError, ErrorCode


async def validate_runtime_configuration(
    value: Any, user_id: str, existing: dict | None = None
) -> dict:
    try:
        runtime = normalize_runtime_config(value, existing)
    except (ValueError, TypeError):
        raise AppError(ErrorCode.VALIDATION_ERROR) from None
    if runtime.get("sandbox") == "local" and runtime.get("sandbox_machine_id"):
        from src.infra.sandbox.relay.registry import SandboxClientRegistry

        machines = await SandboxClientRegistry().list_machines(user_id, include_offline=True)
        if not any(row["machine_id"] == runtime["sandbox_machine_id"] for row in machines):
            raise AppError(ErrorCode.VALIDATION_ERROR)
    return runtime

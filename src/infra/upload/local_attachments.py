"""Local references retain existing daemon permissions and require the exact target."""

from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AttachmentSchema


async def validate_local_attachments(
    attachments: list[AttachmentSchema] | None,
    options: dict,
    user_id: str,
    agent_id: str | None = None,
) -> None:
    local = [item.local_file for item in attachments or [] if item.local_file]
    if not local:
        return
    if agent_id:
        from src.agents.core.base import get_agent_class

        if not getattr(get_agent_class(agent_id), "_supports_sandbox", False):
            raise AppError(ErrorCode.INVALID_ATTACHMENTS)
    machine = options.get("sandbox_machine_id")
    if (
        options.get("sandbox") != "local"
        or not machine
        or any(item.machine_id != machine for item in local)
    ):
        raise AppError(ErrorCode.INVALID_ATTACHMENTS)
    from src.infra.sandbox.relay.registry import SandboxClientRegistry

    if await SandboxClientRegistry().resolve_target(user_id, machine) != machine:
        raise AppError(ErrorCode.INVALID_ATTACHMENTS)

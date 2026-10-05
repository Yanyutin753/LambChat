"""Persistent, local, and cloud backend setup for Team Agent runs."""

import time
import uuid
from typing import Any

from src.agents.team_agent.context import TeamAgentContext
from src.infra.backend import create_persistent_backend, create_sandbox_backend
from src.infra.envvar.sync import (
    apply_sandbox_env_overrides,
    resolve_channel_env_vars,
    sync_sandbox_env_vars,
)
from src.infra.logging import get_logger
from src.infra.sandbox.session_manager import get_session_sandbox_manager
from src.infra.storage.mongodb_store import acreate_store
from src.kernel.config import settings

logger = get_logger(__name__)


async def load_backend_bundle(
    *,
    state: dict[str, Any],
    context: TeamAgentContext,
    presenter: Any,
    assistant_id: str,
    agent_options: dict[str, Any],
) -> tuple[Any, Any, Any, str | None]:
    """Create the team's run-owned backend and apply its channel environment."""
    backend_start = time.time()
    loaded_sandbox_backend: Any = None
    loaded_sandbox_work_dir = None
    sandbox_choice = agent_options.get("sandbox")
    sandbox_platform = (
        sandbox_choice
        if isinstance(sandbox_choice, str) and sandbox_choice in {"local", "cloud"}
        else settings.SANDBOX_PLATFORM.lower()
    )
    env_overrides = (
        await resolve_channel_env_vars(context.user_id or "", agent_options)
        if settings.ENABLE_SANDBOX
        else {}
    )

    if not settings.ENABLE_SANDBOX:
        loaded_backend = create_persistent_backend(
            assistant_id=assistant_id,
            user_id=context.user_id,
            session_id=state.get("session_id", str(uuid.uuid4())),
        )
        logger.info(
            f"[TeamAgent] Sandbox disabled, using PersistentBackend for assistant: {assistant_id}"
        )
    elif sandbox_platform == "local":
        from src.infra.backend.local import WorkspaceAliasBackend
        from src.infra.backend.workspace_selection import selected_workspace_id

        if not context.user_id:
            raise ValueError("Sandbox requires authenticated user (user_id is required)")
        workspace_id = selected_workspace_id(agent_options)
        loaded_sandbox_backend = WorkspaceAliasBackend(
            user_id=context.user_id,
            session_id=(
                f".selected/{workspace_id}"
                if workspace_id
                else state.get("session_id") or context.session_id
            ),
            machine_id=agent_options.get("sandbox_machine_id") or None,
        )
        await sync_sandbox_env_vars(loaded_sandbox_backend, context.user_id)
        apply_sandbox_env_overrides(loaded_sandbox_backend, env_overrides)
        loaded_sandbox_work_dir = loaded_sandbox_backend.work_dir
        loaded_backend = create_sandbox_backend(
            loaded_sandbox_backend, assistant_id, user_id=context.user_id
        )
    else:
        if not context.user_id:
            raise ValueError("Sandbox requires authenticated user (user_id is required)")
        sandbox_manager = get_session_sandbox_manager()
        try:
            await presenter.emit_sandbox_starting()
        except Exception as exc:
            logger.warning("Failed to emit sandbox:starting event: %s", exc)
        try:
            (
                loaded_sandbox_backend,
                loaded_sandbox_work_dir,
            ) = await sandbox_manager.get_or_create(
                session_id=state.get("session_id", str(uuid.uuid4())),
                user_id=context.user_id,
            )
            apply_sandbox_env_overrides(loaded_sandbox_backend, env_overrides)
            try:
                sandbox_id = getattr(loaded_sandbox_backend.default, "id", "unknown")
                await presenter.emit_sandbox_ready(
                    sandbox_id=sandbox_id,
                    work_dir=loaded_sandbox_work_dir,
                )
            except Exception as exc:
                logger.warning("Failed to emit sandbox:ready event: %s", exc)
            loaded_backend = create_sandbox_backend(
                loaded_sandbox_backend.default,
                assistant_id,
                user_id=context.user_id,
            )
            logger.info(
                f"[TeamAgent] Sandbox enabled, using sandbox backend for assistant: {assistant_id}"
            )
        except Exception as exc:
            try:
                await presenter.emit_sandbox_error(f"沙箱初始化失败: {str(exc)}")
            except Exception as emit_exc:
                logger.warning("Failed to emit sandbox:error event: %s", emit_exc)
            raise

    loaded_store = await acreate_store()
    logger.debug(f"[TeamAgent] Backend init: {(time.time() - backend_start) * 1000:.3f}ms")
    return (
        loaded_backend,
        loaded_store,
        loaded_sandbox_backend,
        loaded_sandbox_work_dir,
    )

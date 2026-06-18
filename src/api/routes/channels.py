"""Generic channel configuration API router.

Provides endpoints for managing per-user channel configurations.
Supports multiple channel types and multiple instances per channel type.
"""

import inspect

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import get_current_user_required, require_permissions
from src.infra.agent.config_storage import get_agent_config_storage
from src.infra.async_utils.blocking import run_blocking_io
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.pubsub import publish_channel_config_changed
from src.infra.channel.registry import get_registry
from src.infra.logging import get_logger
from src.infra.role.storage import RoleStorage
from src.kernel.exceptions import AuthorizationError, NotFoundError
from src.kernel.extensions import (
    FEISHU_CONNECTOR_ID,
    FEISHU_CONNECTOR_PLUGIN_ID,
    PluginRuntime,
    PluginUnavailableError,
)
from src.kernel.schemas.channel import (
    ChannelConfigCreate,
    ChannelConfigResponse,
    ChannelConfigStatus,
    ChannelConfigUpdate,
    ChannelListResponse,
    ChannelType,
    ChannelTypeListResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

logger = get_logger(__name__)

router = APIRouter()
CHANNEL_LIST_MAX_ITEMS = 200


async def get_channel_storage() -> ChannelStorage:
    """Dependency to get ChannelStorage"""
    return ChannelStorage()


def get_plugin_runtime(request: Request) -> PluginRuntime | None:
    runtime = getattr(request.app.state, "plugin_runtime", None)
    if isinstance(runtime, PluginRuntime):
        return runtime
    return None


def _plugin_unavailable_http_error(exc: PluginUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "plugin_unavailable",
            "plugin_id": FEISHU_CONNECTOR_PLUGIN_ID,
            "message": str(exc),
        },
    )


def _is_feishu_connector_available(plugin_runtime: object) -> bool:
    if not isinstance(plugin_runtime, PluginRuntime):
        return True
    try:
        plugin_runtime.ensure_channel_connector_available(FEISHU_CONNECTOR_ID)
    except PluginUnavailableError:
        return False
    return True


def _ensure_channel_connector_available(
    channel_type: ChannelType,
    plugin_runtime: object,
) -> None:
    if channel_type != ChannelType.FEISHU:
        return
    if not isinstance(plugin_runtime, PluginRuntime):
        return
    try:
        plugin_runtime.ensure_channel_connector_available(FEISHU_CONNECTOR_ID)
    except PluginUnavailableError as exc:
        raise _plugin_unavailable_http_error(exc) from exc


async def _validate_agent_id(agent_id: str | None, user: TokenPayload) -> None:
    """Validate that the user has permission to use the specified agent."""
    if not agent_id:
        return

    agent_storage = get_agent_config_storage()

    # Check agent is globally enabled
    if not await agent_storage.is_agent_enabled(agent_id):
        raise HTTPException(status_code=400, detail=f"Agent '{agent_id}' is not available")

    # Check agent is allowed for user's roles
    if user.roles:
        role_storage = RoleStorage()
        allowed = set()
        for role in await role_storage.get_by_names(user.roles):
            if role.allowed_agents:
                allowed.update(role.allowed_agents)
        if allowed and agent_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Agent '{agent_id}' is not allowed for your role",
            )


async def _validate_project_id(project_id: str | None, user: TokenPayload) -> None:
    """Validate that the project exists and belongs to the current user."""
    if not project_id:
        return

    from src.infra.folder.storage import get_project_storage

    project_storage = get_project_storage()
    project = await project_storage.get_by_id(project_id, user.sub)
    if not project:
        raise HTTPException(status_code=400, detail=f"Project '{project_id}' does not exist")


async def _validate_persona_preset_id(persona_preset_id: str | None, user: TokenPayload) -> None:
    """Validate that the selected persona preset is visible to the current user."""
    if not persona_preset_id:
        return

    from src.infra.persona_preset.manager import PersonaPresetManager

    try:
        await PersonaPresetManager().get_preset(
            persona_preset_id,
            user_id=user.sub,
            is_admin=Permission.PERSONA_PRESET_ADMIN in (user.permissions or []),
        )
    except NotFoundError:
        raise HTTPException(status_code=400, detail="Persona preset does not exist")
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Persona preset is not allowed")


async def _is_manager_connected(manager, user_id: str, instance_id: str) -> bool:
    distributed_checker = getattr(manager, "is_connected_distributed", None)
    if callable(distributed_checker):
        result = distributed_checker(user_id, instance_id)
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)
    return bool(manager.is_connected(user_id, instance_id))


@router.get(
    "/types",
    response_model=ChannelTypeListResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def get_channel_types(
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
):
    """Get all available channel types with metadata"""
    registry = get_registry()
    metadata_list = registry.get_channel_metadata()
    if not _is_feishu_connector_available(plugin_runtime):
        metadata_list = [
            metadata
            for metadata in metadata_list
            if metadata.get("channel_type") != ChannelType.FEISHU.value
        ]
    return ChannelTypeListResponse(types=metadata_list)


@router.post(
    "/feishu/registrations",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def start_feishu_registration(
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
):
    """Start a one-click Feishu app registration session."""
    _ensure_channel_connector_available(ChannelType.FEISHU, plugin_runtime)
    try:
        from src.infra.channel.feishu.registration import start_registration

        session = await run_blocking_io(start_registration, timeout=5.0)
        return session.to_dict(include_secret=False)
    except ImportError as e:
        raise HTTPException(
            status_code=400,
            detail=f"lark-oapi register_app is unavailable: {e}",
        )


@router.get(
    "/feishu/registrations/{session_id}",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def get_feishu_registration(
    session_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
):
    """Poll a one-click Feishu app registration session."""
    _ensure_channel_connector_available(ChannelType.FEISHU, plugin_runtime)
    from src.infra.channel.feishu.registration import get_registration

    session = await run_blocking_io(get_registration, session_id, timeout=5.0)
    if not session:
        raise HTTPException(status_code=404, detail="Registration session not found")
    return session.to_dict(include_secret=session.status == "success")


@router.delete(
    "/feishu/registrations/{session_id}",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def cancel_feishu_registration(
    session_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
):
    """Cancel a one-click Feishu app registration session."""
    _ensure_channel_connector_available(ChannelType.FEISHU, plugin_runtime)
    from src.infra.channel.feishu.registration import cancel_registration

    if not await run_blocking_io(cancel_registration, session_id, timeout=5.0):
        raise HTTPException(status_code=404, detail="Registration session not found")
    return {"cancelled": True}


@router.get(
    "/",
    response_model=ChannelListResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def list_user_channels(
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """List all configured channel instances for current user"""
    registry = get_registry()
    total_configs = await storage.count_user_configs(user.sub)
    if total_configs > CHANNEL_LIST_MAX_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many channel configurations to list at once (max {CHANNEL_LIST_MAX_ITEMS})",
        )
    configs = await storage.list_user_configs(user.sub)

    responses = []
    for config in configs:
        try:
            channel_type = ChannelType(config.get("channel_type"))
            if channel_type == ChannelType.FEISHU and not _is_feishu_connector_available(plugin_runtime):
                continue
            metadata = registry.get_channel_class(channel_type)
            if metadata:
                meta = metadata.get_metadata()
                sensitive_fields = set()
                for field in meta.get("config_fields", []):
                    if field.get("sensitive"):
                        sensitive_fields.add(field["name"])

                # Mask sensitive fields
                masked_config = {k: v for k, v in config.items() if k not in sensitive_fields}
                for field in sensitive_fields:
                    if config.get(field):
                        masked_config[field] = "***"

                responses.append(
                    ChannelConfigResponse(
                        id=config.get("instance_id", ""),
                        channel_type=channel_type,
                        name=config.get("name", ""),
                        user_id=user.sub,
                        enabled=config.get("enabled", True),
                        config=masked_config,
                        capabilities=meta.get("capabilities", []),
                        agent_id=config.get("agent_id"),
                        model_id=config.get("model_id"),
                        project_id=config.get("project_id"),
                        persona_preset_id=config.get("persona_preset_id"),
                        created_at=config.get("created_at"),
                        updated_at=config.get("updated_at"),
                    )
                )
        except ValueError:
            # Unknown channel type, skip
            continue

    return ChannelListResponse(channels=responses)


@router.get(
    "/{channel_type}",
    response_model=ChannelListResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def list_channel_instances(
    channel_type: ChannelType,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """List all instances of a specific channel type"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    total_configs = await storage.count_user_configs_by_type(user.sub, channel_type)
    if total_configs > CHANNEL_LIST_MAX_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many channel configurations to list at once (max {CHANNEL_LIST_MAX_ITEMS})",
        )

    configs = await storage.list_user_configs_by_type(user.sub, channel_type)

    metadata = channel_class.get_metadata()
    responses = []
    for config in configs:
        sensitive_fields = set()
        for field in metadata.get("config_fields", []):
            if field.get("sensitive"):
                sensitive_fields.add(field["name"])

        # Mask sensitive fields
        masked_config = {k: v for k, v in config.items() if k not in sensitive_fields}
        for field in sensitive_fields:
            if config.get(field):
                masked_config[field] = "***"

        responses.append(
            ChannelConfigResponse(
                id=config.get("instance_id", ""),
                channel_type=channel_type,
                name=config.get("name", ""),
                user_id=user.sub,
                enabled=config.get("enabled", True),
                config=masked_config,
                capabilities=metadata.get("capabilities", []),
                agent_id=config.get("agent_id"),
                model_id=config.get("model_id"),
                project_id=config.get("project_id"),
                persona_preset_id=config.get("persona_preset_id"),
                created_at=config.get("created_at"),
                updated_at=config.get("updated_at"),
            )
        )

    return ChannelListResponse(channels=responses)


@router.get(
    "/{channel_type}/{instance_id}",
    response_model=ChannelConfigResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def get_channel_instance(
    channel_type: ChannelType,
    instance_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get a specific channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    config = await storage.get_config(user.sub, channel_type, instance_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    metadata = channel_class.get_metadata()
    return storage.build_response_from_config(config, channel_type, user.sub, metadata)


@router.post(
    "/{channel_type}",
    response_model=ChannelConfigResponse,
    status_code=201,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def create_channel_instance(
    channel_type: ChannelType,
    data: ChannelConfigCreate,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Create a new channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    if data.channel_type != channel_type:
        raise HTTPException(
            status_code=400,
            detail=f"Channel type mismatch: expected {channel_type}, got {data.channel_type}",
        )

    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="Instance name is required")

    # Check channel limit from user roles
    max_channels = None  # Default: no limit
    if user.roles:
        role_storage = RoleStorage()
        for role in await role_storage.get_by_names(user.roles):
            if role.limits and role.limits.max_channels is not None:
                # Get the minimum limit among all roles (most restrictive)
                if max_channels is None or role.limits.max_channels < max_channels:
                    max_channels = role.limits.max_channels

    if max_channels is not None and max_channels >= 0:
        existing_channel_count = await storage.count_user_configs(user.sub)
        if existing_channel_count >= max_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum channel limit ({max_channels}) reached. Please delete an existing channel before creating a new one.",
            )

    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()

    # Validate agent_id against user permissions
    await _validate_agent_id(data.agent_id, user)
    await _validate_project_id(data.project_id, user)
    await _validate_persona_preset_id(data.persona_preset_id, user)

    try:
        config = await storage.create_config(
            user_id=user.sub,
            channel_type=channel_type,
            config=data.config,
            name=data.name.strip(),
            agent_id=data.agent_id,
            model_id=data.model_id,
            project_id=data.project_id,
            team_id=data.team_id,
            persona_preset_id=data.persona_preset_id,
        )

        # Reload the channel client if manager exists
        manager_class = registry.get_manager_class(channel_type)
        if manager_class:
            try:
                manager = manager_class.get_instance()
                await manager.reload_user(user.sub, config.get("instance_id"))
            except Exception as e:
                logger.warning(f"Failed to reload {channel_type} client: {e}")

        await publish_channel_config_changed(
            user_id=user.sub,
            channel_type=channel_type.value,
            channel_instance_id=config.get("instance_id"),
            action="created",
        )

        return await storage.get_response(
            user.sub, channel_type, config.get("instance_id"), metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/{channel_type}/{instance_id}",
    response_model=ChannelConfigResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def update_channel_instance(
    channel_type: ChannelType,
    instance_id: str,
    data: ChannelConfigUpdate,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Update a specific channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()

    # Get existing config to merge with updates
    existing = await storage.get_config(user.sub, channel_type, instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Merge configs: keep existing values for empty sensitive fields
    merged_config = {**existing, **data.config}
    for field in metadata.get("config_fields", []):
        if field.get("sensitive") and not data.config.get(field["name"]):
            # Keep existing value for empty sensitive fields
            merged_config[field["name"]] = existing.get(field["name"])

    # Validate agent_id if explicitly provided in the request
    agent_id_value: str | None = ...  # type: ignore[assignment]
    if "agent_id" in data.model_fields_set:
        await _validate_agent_id(data.agent_id, user)
        agent_id_value = data.agent_id
    else:
        agent_id_value = ...  # type: ignore[assignment]

    # Handle model_id with same ellipsis pattern
    model_id_value: str | None = ...  # type: ignore[assignment]
    if "model_id" in data.model_fields_set:
        model_id_value = data.model_id
    else:
        model_id_value = ...  # type: ignore[assignment]

    # Handle project_id with same ellipsis pattern
    project_id_value: str | None = ...  # type: ignore[assignment]
    if "project_id" in data.model_fields_set:
        await _validate_project_id(data.project_id, user)
        project_id_value = data.project_id
    else:
        project_id_value = ...  # type: ignore[assignment]

    # Handle team_id with same ellipsis pattern
    team_id_value: str | None = ...  # type: ignore[assignment]
    if "team_id" in data.model_fields_set:
        team_id_value = data.team_id
    else:
        team_id_value = ...  # type: ignore[assignment]

    # Handle persona_preset_id with same ellipsis pattern
    persona_preset_id_value: str | None = ...  # type: ignore[assignment]
    if "persona_preset_id" in data.model_fields_set:
        await _validate_persona_preset_id(data.persona_preset_id, user)
        persona_preset_id_value = data.persona_preset_id
    else:
        persona_preset_id_value = ...  # type: ignore[assignment]

    config = await storage.update_config(
        user_id=user.sub,
        channel_type=channel_type,
        config=merged_config,
        instance_id=instance_id,
        enabled=data.enabled,
        agent_id=agent_id_value,
        model_id=model_id_value,
        project_id=project_id_value,
        team_id=team_id_value,
        persona_preset_id=persona_preset_id_value,
    )

    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Reload the channel client
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub, instance_id)
        except Exception as e:
            logger.warning(f"Failed to reload {channel_type} client: {e}")

    await publish_channel_config_changed(
        user_id=user.sub,
        channel_type=channel_type.value,
        channel_instance_id=instance_id,
        action="updated",
    )

    return await storage.get_response(user.sub, channel_type, instance_id, metadata)


@router.delete(
    "/{channel_type}/{instance_id}",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_DELETE))],
)
async def delete_channel_instance(
    channel_type: ChannelType,
    instance_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Delete a specific channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    # Check if instance exists
    existing = await storage.get_config(user.sub, channel_type, instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Delete config first, then stop the running channel
    # (must delete before reload, otherwise reload sees the config and restarts it)
    deleted = await storage.delete_config(user.sub, channel_type, instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Stop the channel client after config is removed
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub, instance_id)
        except Exception as e:
            logger.error(
                f"Failed to stop {channel_type} client for user {user.sub}, instance {instance_id}. "
                f"The channel may still be running. Error: {e}"
            )

    await publish_channel_config_changed(
        user_id=user.sub,
        channel_type=channel_type.value,
        channel_instance_id=instance_id,
        action="deleted",
    )

    return {"message": "Channel instance deleted successfully"}


@router.get(
    "/{channel_type}/{instance_id}/status",
    response_model=ChannelConfigStatus,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def get_channel_instance_status(
    channel_type: ChannelType,
    instance_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get connection status for a specific channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    # Check if instance exists
    config = await storage.get_config(user.sub, channel_type, instance_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    status = await storage.get_status(user.sub, channel_type, instance_id)

    # Update connection status from channel manager
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            connected = await _is_manager_connected(manager, user.sub, instance_id)
            status.connected = connected
        except Exception as e:
            logger.warning(
                "Failed to refresh %s channel status for user %s, instance %s: %s",
                channel_type.value,
                user.sub,
                instance_id,
                e,
            )

    return status


@router.post(
    "/{channel_type}/{instance_id}/test",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def test_channel_instance_connection(
    channel_type: ChannelType,
    instance_id: str,
    plugin_runtime: PluginRuntime | None = Depends(get_plugin_runtime),
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Test connection for a specific channel instance"""
    _ensure_channel_connector_available(channel_type, plugin_runtime)
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    config = await storage.get_config(user.sub, channel_type, instance_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="Channel instance is disabled")

    # Check if connected; if not, attempt to start the channel
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            connected = await _is_manager_connected(manager, user.sub, instance_id)

            if not connected:
                await manager.reload_user(user.sub, instance_id)
                connected = await _is_manager_connected(manager, user.sub, instance_id)

            if connected:
                return {
                    "success": True,
                    "message": f"{channel_type} channel is connected",
                }
            else:
                return {
                    "success": False,
                    "message": f"{channel_type} channel is not connected. Check logs for errors.",
                }
        except Exception as e:
            return {"success": False, "message": str(e)}

    return {"success": False, "message": "Channel manager not available"}

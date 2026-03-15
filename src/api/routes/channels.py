"""Generic channel configuration API router.

Provides endpoints for managing per-user channel configurations.
Supports multiple channel types and multiple instances per channel type.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user_required, require_permissions
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.registry import get_registry
from src.infra.role.storage import RoleStorage
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

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_channel_storage() -> ChannelStorage:
    """Dependency to get ChannelStorage"""
    return ChannelStorage()


@router.get("/types", response_model=ChannelTypeListResponse)
async def get_channel_types():
    """Get all available channel types with metadata"""
    registry = get_registry()
    metadata_list = registry.get_channel_metadata()
    return ChannelTypeListResponse(types=metadata_list)


@router.get(
    "/",
    response_model=ChannelListResponse,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def list_user_channels(
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """List all configured channel instances for current user"""
    registry = get_registry()
    configs = await storage.list_user_configs(user.sub)

    responses = []
    for config in configs:
        try:
            channel_type = ChannelType(config.get("channel_type"))
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
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """List all instances of a specific channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    # Get all configs for this user and channel type
    all_configs = await storage.list_user_configs(user.sub)
    configs = [c for c in all_configs if c.get("channel_type") == channel_type.value]

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
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get a specific channel instance"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    config = await storage.get_config(user.sub, channel_type, instance_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    metadata = channel_class.get_metadata()
    return await storage.get_response(user.sub, channel_type, instance_id, metadata)


@router.post(
    "/{channel_type}",
    response_model=ChannelConfigResponse,
    status_code=201,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_WRITE))],
)
async def create_channel_instance(
    channel_type: ChannelType,
    data: ChannelConfigCreate,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Create a new channel instance"""
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
        for role_name in user.roles:
            role = await role_storage.get_by_name(role_name)
            if role and role.limits and role.limits.max_channels is not None:
                # Get the minimum limit among all roles (most restrictive)
                if max_channels is None or role.limits.max_channels < max_channels:
                    max_channels = role.limits.max_channels

    if max_channels is not None and max_channels >= 0:
        existing_channels = await storage.list_user_configs(user.sub)
        if len(existing_channels) >= max_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum channel limit ({max_channels}) reached. Please delete an existing channel before creating a new one.",
            )

    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()

    try:
        config = await storage.create_config(
            user_id=user.sub,
            channel_type=channel_type,
            config=data.config,
            name=data.name.strip(),
        )

        # Reload the channel client if manager exists
        manager_class = registry.get_manager_class(channel_type)
        if manager_class:
            try:
                manager = manager_class.get_instance()
                await manager.reload_user(user.sub)
            except Exception as e:
                logger.warning(f"Failed to reload {channel_type} client: {e}")

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
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Update a specific channel instance"""
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

    config = await storage.update_config(
        user_id=user.sub,
        channel_type=channel_type,
        config=merged_config,
        instance_id=instance_id,
        enabled=data.enabled,
    )

    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Reload the channel client
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub)
        except Exception as e:
            logger.warning(f"Failed to reload {channel_type} client: {e}")

    return await storage.get_response(user.sub, channel_type, instance_id, metadata)


@router.delete(
    "/{channel_type}/{instance_id}",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_DELETE))],
)
async def delete_channel_instance(
    channel_type: ChannelType,
    instance_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Delete a specific channel instance"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    # Check if instance exists
    existing = await storage.get_config(user.sub, channel_type, instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    # Stop the channel client first
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub, instance_id)  # Stop specific instance
        except Exception as e:
            logger.warning(f"Failed to stop {channel_type} client: {e}")

    deleted = await storage.delete_config(user.sub, channel_type, instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    return {"message": "Channel instance deleted successfully"}


@router.get(
    "/{channel_type}/{instance_id}/status",
    response_model=ChannelConfigStatus,
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def get_channel_instance_status(
    channel_type: ChannelType,
    instance_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get connection status for a specific channel instance"""
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
            status.connected = manager.is_connected(user.sub, instance_id)
        except Exception:
            pass

    return status


@router.post(
    "/{channel_type}/{instance_id}/test",
    dependencies=[Depends(require_permissions(Permission.CHANNEL_READ))],
)
async def test_channel_instance_connection(
    channel_type: ChannelType,
    instance_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Test connection for a specific channel instance"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    config = await storage.get_config(user.sub, channel_type, instance_id)
    if not config:
        raise HTTPException(status_code=404, detail="Channel instance not found")

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="Channel instance is disabled")

    # Check if connected
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            connected = manager.is_connected(user.sub, instance_id)

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

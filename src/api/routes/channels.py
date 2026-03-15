"""Generic channel configuration API router.

Provides endpoints for managing per-user channel configurations.
Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user_required
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.registry import get_registry
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


@router.get("/", response_model=ChannelListResponse)
async def list_user_channels(
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """List all configured channels for current user"""
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
                        channel_type=channel_type,
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


@router.get("/{channel_type}", response_model=Optional[ChannelConfigResponse])
async def get_channel_config(
    channel_type: ChannelType,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get configuration for a specific channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)

    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()
    return await storage.get_response(user.sub, channel_type, metadata)


@router.post("/{channel_type}", response_model=ChannelConfigResponse, status_code=201)
async def create_channel_config(
    channel_type: ChannelType,
    data: ChannelConfigCreate,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Create configuration for a channel type"""
    if data.channel_type != channel_type:
        raise HTTPException(
            status_code=400,
            detail=f"Channel type mismatch: expected {channel_type}, got {data.channel_type}",
        )

    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()

    try:
        await storage.create_config(
            user_id=user.sub,
            channel_type=channel_type,
            config=data.config,
        )

        # Reload the channel client if manager exists
        manager_class = registry.get_manager_class(channel_type)
        if manager_class:
            try:
                manager = manager_class.get_instance()
                await manager.reload_user(user.sub)
            except Exception as e:
                logger.warning(f"Failed to reload {channel_type} client: {e}")

        return await storage.get_response(user.sub, channel_type, metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{channel_type}", response_model=ChannelConfigResponse)
async def update_channel_config(
    channel_type: ChannelType,
    data: ChannelConfigUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Update configuration for a channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    metadata = channel_class.get_metadata()

    # Get existing config to merge with updates
    existing = await storage.get_config(user.sub, channel_type)
    if not existing:
        raise HTTPException(status_code=404, detail=f"{channel_type} configuration not found")

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
        enabled=data.enabled,
    )

    if not config:
        raise HTTPException(status_code=404, detail=f"{channel_type} configuration not found")

    # Reload the channel client
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub)
        except Exception as e:
            logger.warning(f"Failed to reload {channel_type} client: {e}")

    return await storage.get_response(user.sub, channel_type, metadata)


@router.delete("/{channel_type}")
async def delete_channel_config(
    channel_type: ChannelType,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Delete configuration for a channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    # Stop the channel client first
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            await manager.reload_user(user.sub)  # This will stop since config is deleted
        except Exception as e:
            logger.warning(f"Failed to stop {channel_type} client: {e}")

    deleted = await storage.delete_config(user.sub, channel_type)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"{channel_type} configuration not found")

    return {"message": f"{channel_type} configuration deleted successfully"}


@router.get("/{channel_type}/status", response_model=ChannelConfigStatus)
async def get_channel_status(
    channel_type: ChannelType,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Get connection status for a channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    status = await storage.get_status(user.sub, channel_type)

    # Update connection status from channel manager
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            status.connected = manager.is_connected(user.sub)
        except Exception:
            pass

    return status


@router.post("/{channel_type}/test")
async def test_channel_connection(
    channel_type: ChannelType,
    user: TokenPayload = Depends(get_current_user_required),
    storage: ChannelStorage = Depends(get_channel_storage),
):
    """Test connection for a channel type"""
    registry = get_registry()
    channel_class = registry.get_channel_class(channel_type)
    if not channel_class:
        raise HTTPException(status_code=404, detail=f"Unknown channel type: {channel_type}")

    config = await storage.get_config(user.sub, channel_type)
    if not config:
        raise HTTPException(status_code=404, detail=f"{channel_type} configuration not found")

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail=f"{channel_type} channel is disabled")

    # Check if connected
    manager_class = registry.get_manager_class(channel_type)
    if manager_class:
        try:
            manager = manager_class.get_instance()
            connected = manager.is_connected(user.sub)

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

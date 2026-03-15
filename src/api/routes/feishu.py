"""
Feishu/Lark channel configuration API router

Provides endpoints for managing per-user Feishu bot configurations.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user_required
from src.infra.channel.feishu_channel import get_feishu_channel_manager
from src.infra.channel.feishu_storage import FeishuStorage
from src.kernel.schemas.feishu import (
    FeishuConfigCreate,
    FeishuConfigResponse,
    FeishuConfigStatus,
    FeishuConfigUpdate,
)
from src.kernel.schemas.user import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_feishu_storage() -> FeishuStorage:
    """Dependency to get FeishuStorage"""
    return FeishuStorage()


@router.get("/", response_model=FeishuConfigResponse | None)
async def get_feishu_config(
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Get current user's Feishu configuration (sensitive fields masked)"""
    config = await storage.get_response(user.sub)
    return config


@router.post("/", response_model=FeishuConfigResponse, status_code=201)
async def create_feishu_config(
    data: FeishuConfigCreate,
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Create Feishu configuration for current user"""
    try:
        config = await storage.create_config(data, user.sub)

        # Start the Feishu client if enabled
        if config.enabled:
            try:
                manager = get_feishu_channel_manager()
                await manager.reload_user(user.sub)
            except Exception as e:
                logger.warning(f"Failed to start Feishu client: {e}")

        return await storage.get_response(user.sub)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/", response_model=FeishuConfigResponse)
async def update_feishu_config(
    data: FeishuConfigUpdate,
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Update Feishu configuration for current user"""
    config = await storage.update_config(user.sub, data)
    if not config:
        raise HTTPException(status_code=404, detail="Feishu configuration not found")

    # Reload the Feishu client
    try:
        manager = get_feishu_channel_manager()
        await manager.reload_user(user.sub)
    except Exception as e:
        logger.warning(f"Failed to reload Feishu client: {e}")

    return await storage.get_response(user.sub)


@router.delete("/")
async def delete_feishu_config(
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Delete Feishu configuration for current user"""
    # Stop the Feishu client first
    try:
        manager = get_feishu_channel_manager()
        await manager.reload_user(user.sub)  # This will stop the client since config is deleted
    except Exception as e:
        logger.warning(f"Failed to stop Feishu client: {e}")

    deleted = await storage.delete_config(user.sub)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feishu configuration not found")

    return {"message": "Feishu configuration deleted successfully"}


@router.get("/status", response_model=FeishuConfigStatus)
async def get_feishu_status(
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Get Feishu connection status for current user"""
    status = await storage.get_status(user.sub)

    # Update connection status from channel manager
    try:
        manager = get_feishu_channel_manager()
        status.connected = manager.is_connected(user.sub)
    except Exception:
        pass

    return status


@router.post("/test")
async def test_feishu_connection(
    user: TokenPayload = Depends(get_current_user_required),
    storage: FeishuStorage = Depends(get_feishu_storage),
):
    """Test Feishu connection for current user"""
    config = await storage.get_config(user.sub)
    if not config:
        raise HTTPException(status_code=404, detail="Feishu configuration not found")

    if not config.enabled:
        raise HTTPException(status_code=400, detail="Feishu channel is disabled")

    # Check if connected
    manager = get_feishu_channel_manager()
    connected = manager.is_connected(user.sub)

    if connected:
        return {"success": True, "message": "Feishu bot is connected"}
    else:
        return {"success": False, "message": "Feishu bot is not connected. Check logs for errors."}

"""
WebSocket 路由

提供 WebSocket 连接用于实时任务通知。
"""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.deps import get_current_user_from_websocket
from src.infra.websocket import get_connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token for authentication"),
):
    """
    WebSocket 连接端点

    用于接收任务完成等实时通知。
    连接成功后需要保持，服务器会主动推送通知消息。

    查询参数:
        token: JWT 认证 token

    消息格式:
    - task:complete: 任务完成通知
        {
            "type": "task:complete",
            "data": {
                "session_id": "xxx",
                "run_id": "xxx",
                "status": "completed" | "failed",
                "message": "可选的完成消息"
            }
        }
    """
    logger.info("[WebSocket] New connection attempt with token")

    # 验证 token 并获取用户
    try:
        user = await get_current_user_from_websocket(token)
        logger.info(f"[WebSocket] Auth successful: user_id={user.sub}")
    except Exception as e:
        logger.warning(f"[WebSocket] Auth failed: {e}")
        await websocket.close(code=4001, reason="Unauthorized")
        return

    manager = get_connection_manager()
    user_id = user.sub

    await manager.connect(websocket, user_id)
    logger.info(f"[WebSocket] Connected: user_id={user_id}")

    try:
        # 保持连接，持续接收消息（目前主要是心跳）
        while True:
            # 等待客户端消息，可以用于心跳检测
            data = await websocket.receive_text()
            # 可以在这里处理客户端的心跳消息
            logger.debug(f"[WebSocket] Received from client: {data}")

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"[WebSocket] Error: {e}")
    finally:
        await manager.disconnect(websocket, user_id)
        logger.info(f"[WebSocket] Cleaned up: user_id={user_id}")

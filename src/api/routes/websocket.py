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
    token: str | None = Query(
        None, description="JWT token for authentication (optional if using Sec-WebSocket-Protocol)"
    ),
):
    """
    WebSocket 连接端点

    用于接收任务完成等实时通知。
    连接成功后需要保持，服务器会主动推送通知消息。

    认证方式（优先级）:
    1. Sec-WebSocket-Protocol: 推荐，格式 "bearer <token>"
    2. URL query参数: token=<token>

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
    logger.info("[WebSocket] New connection attempt")

    # 认证方式（按优先级）:
    # 1. URL query参数: /ws?token=xxx
    # 2. 连接后首条消息: {"type": "auth", "token": "xxx"}
    auth_token = token
    needs_accept = False

    # 验证 token 并获取用户
    try:
        if not auth_token:
            # 先接受WebSocket连接
            await websocket.accept()
            needs_accept = True
            # 等待客户端发送首条认证消息
            logger.info("[WebSocket] Waiting for auth message from client")
            try:
                auth_message = await websocket.receive_text()
                import json

                auth_data = json.loads(auth_message)
                if auth_data.get("type") == "auth":
                    auth_token = auth_data.get("token")
                    logger.debug("[WebSocket] Received auth from message")
            except Exception as e:
                logger.warning(f"[WebSocket] Failed to receive auth: {e}")
                raise ValueError("Authentication required")

        if not auth_token:
            raise ValueError("No token provided")

        user = await get_current_user_from_websocket(auth_token)
        logger.info(f"[WebSocket] Auth successful: user_id={user.sub}")

        # 如果还没有accept（URL有token的情况），现在accept
        if not needs_accept:
            await websocket.accept()
    except Exception as e:
        logger.warning(f"[WebSocket] Auth failed: {e}")
        await websocket.close(code=4001, reason="Unauthorized")
        return

    manager = get_connection_manager()
    user_id = user.sub

    await manager.connect(websocket, user_id, accept=False)
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

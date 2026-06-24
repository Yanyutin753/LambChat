"""Client sandbox device, binding, and WebSocket routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from src.api.deps import get_current_user_from_websocket, get_current_user_required
from src.infra.async_utils import run_blocking_io
from src.infra.client_sandbox.models import (
    ClientSandboxBindingCreate,
    ClientSandboxDeviceRegister,
    ClientSandboxPreferenceUpdate,
    ClientSandboxRpcResponse,
)
from src.infra.client_sandbox.router import get_client_sandbox_router
from src.infra.client_sandbox.storage import ClientSandboxStorage
from src.infra.logging import get_logger
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)


@router.get("/devices")
async def list_devices(user: TokenPayload = Depends(get_current_user_required)):
    storage = ClientSandboxStorage()
    devices = await storage.list_devices(user.sub)
    return {"devices": [device.model_dump(mode="json") for device in devices]}


@router.get("/preference")
async def get_preference(user: TokenPayload = Depends(get_current_user_required)):
    storage = ClientSandboxStorage()
    preference = await storage.get_preference(user.sub)
    return {"preference": preference.model_dump(mode="json") if preference else None}


@router.post("/preference")
async def set_preference(
    preference: ClientSandboxPreferenceUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = ClientSandboxStorage()
    saved = await storage.set_preference(user.sub, preference)
    return {"preference": saved.model_dump(mode="json")}


@router.post("/session-bindings")
async def create_session_binding(
    binding: ClientSandboxBindingCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = ClientSandboxStorage()
    saved = await storage.create_or_refresh_binding(user.sub, binding)
    return {"binding": saved.model_dump(mode="json")}


@router.get("/session-bindings/{session_id}")
async def get_session_binding(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = ClientSandboxStorage()
    binding = await storage.get_active_binding(user.sub, session_id)
    return {"binding": binding.model_dump(mode="json") if binding else None}


@router.delete("/session-bindings/{session_id}")
async def delete_session_binding(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    storage = ClientSandboxStorage()
    ended = await storage.end_binding(user.sub, session_id)
    return {"ended": ended}


@router.websocket("/ws/client-sandbox")
async def client_sandbox_websocket(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    await websocket.accept()
    user_id: str | None = None
    device_id: str | None = None
    router_instance = get_client_sandbox_router()

    try:
        auth_token = token
        if not auth_token:
            auth_message = await websocket.receive_text()
            auth_data = await run_blocking_io(json.loads, auth_message)
            if auth_data.get("type") != "auth" or not auth_data.get("token"):
                raise HTTPException(status_code=401, detail="Authentication required")
            auth_token = auth_data["token"]

        user = await get_current_user_from_websocket(auth_token)
        user_id = user.sub
        await websocket.send_text(json.dumps({"type": "auth:ok"}))

        register_message = await websocket.receive_text()
        register_data = await run_blocking_io(json.loads, register_message)
        if register_data.get("type") == "auth":
            register_message = await websocket.receive_text()
            register_data = await run_blocking_io(json.loads, register_message)
        if register_data.get("type") != "client_sandbox:register":
            raise HTTPException(status_code=400, detail="Client sandbox registration required")

        registration = ClientSandboxDeviceRegister(**register_data)
        device_id = registration.device_id
        storage = ClientSandboxStorage()
        await storage.upsert_device(user_id, registration)
        await router_instance.register_connection(user_id, device_id, websocket)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "client_sandbox:registered",
                    "device_id": device_id,
                }
            )
        )

        while True:
            raw_message = await websocket.receive_text()
            message = await run_blocking_io(json.loads, raw_message)
            if message.get("type") == "client_sandbox:response":
                await router_instance.handle_response(
                    user_id,
                    device_id,
                    ClientSandboxRpcResponse(**message),
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[ClientSandbox] WebSocket connection failed: %s", e)
        try:
            await websocket.close(code=4001, reason="Unauthorized")
        except Exception:
            pass
    finally:
        if user_id and device_id:
            await router_instance.disconnect(user_id, device_id, websocket)

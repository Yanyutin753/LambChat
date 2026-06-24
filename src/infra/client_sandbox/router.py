"""In-memory RPC router for connected desktop client sandboxes."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from src.infra.client_sandbox.models import (
    ClientSandboxRpcRequest,
    ClientSandboxRpcResponse,
)


class SendTextWebSocket(Protocol):
    async def send_text(self, value: str) -> None: ...


class ClientSandboxRouterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ClientSandboxConnection:
    user_id: str
    device_id: str
    websocket: SendTextWebSocket


@dataclass
class _PendingRequest:
    user_id: str
    device_id: str
    future: asyncio.Future[ClientSandboxRpcResponse]


class ClientSandboxRouter:
    def __init__(self) -> None:
        self._connections: dict[tuple[str, str], ClientSandboxConnection] = {}
        self._pending: dict[str, _PendingRequest] = {}
        self._lock = asyncio.Lock()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def register_connection(
        self,
        user_id: str,
        device_id: str,
        websocket: SendTextWebSocket,
    ) -> None:
        async with self._lock:
            self._connections[(user_id, device_id)] = ClientSandboxConnection(
                user_id=user_id,
                device_id=device_id,
                websocket=websocket,
            )

    async def list_connected_device_ids(self, user_id: str) -> list[str]:
        async with self._lock:
            return sorted(
                device_id
                for existing_user_id, device_id in self._connections
                if existing_user_id == user_id
            )

    async def disconnect(self, user_id: str, device_id: str, websocket: SendTextWebSocket) -> None:
        async with self._lock:
            key = (user_id, device_id)
            existing = self._connections.get(key)
            if existing and existing.websocket is websocket:
                self._connections.pop(key, None)
            for request_id, pending in list(self._pending.items()):
                if pending.user_id == user_id and pending.device_id == device_id:
                    if not pending.future.done():
                        pending.future.set_exception(
                            ClientSandboxRouterError(
                                "client_disconnected",
                                "Desktop sandbox disconnected during request",
                            )
                        )
                    self._pending.pop(request_id, None)

    async def call(
        self,
        *,
        user_id: str,
        device_id: str,
        session_id: str,
        operation: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> ClientSandboxRpcResponse:
        request_id = f"rpc_{uuid.uuid4().hex}"
        request = ClientSandboxRpcRequest(
            request_id=request_id,
            session_id=session_id,
            operation=operation,
            timeout_seconds=max(1, int(timeout_seconds)),
            payload=payload,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ClientSandboxRpcResponse] = loop.create_future()

        async with self._lock:
            connection = self._connections.get((user_id, device_id))
            if connection is None:
                raise ClientSandboxRouterError(
                    "device_offline",
                    "Desktop sandbox device is not connected",
                )
            self._pending[request_id] = _PendingRequest(
                user_id=user_id,
                device_id=device_id,
                future=future,
            )

        try:
            await connection.websocket.send_text(
                json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
            )
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise ClientSandboxRouterError(
                "timeout",
                f"Desktop sandbox request timed out after {timeout_seconds} seconds",
            ) from exc
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    async def handle_response(
        self,
        user_id: str,
        device_id: str,
        response: ClientSandboxRpcResponse,
    ) -> bool:
        async with self._lock:
            pending = self._pending.get(response.request_id)
            if pending is None:
                return False
            if pending.user_id != user_id or pending.device_id != device_id:
                return False
            if not pending.future.done():
                pending.future.set_result(response)
            return True


_router: ClientSandboxRouter | None = None


def get_client_sandbox_router() -> ClientSandboxRouter:
    global _router
    if _router is None:
        _router = ClientSandboxRouter()
    return _router

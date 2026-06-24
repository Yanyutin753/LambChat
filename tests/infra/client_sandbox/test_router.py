from __future__ import annotations

import asyncio
import json

import pytest

from src.infra.client_sandbox.models import ClientSandboxRpcResponse
from src.infra.client_sandbox.router import (
    ClientSandboxRouter,
    ClientSandboxRouterError,
)


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, value: str) -> None:
        self.sent.append(json.loads(value))


@pytest.mark.asyncio
async def test_call_sends_rpc_and_returns_matching_response() -> None:
    router = ClientSandboxRouter()
    websocket = FakeWebSocket()
    await router.register_connection("user-1", "device-1", websocket)

    call_task = asyncio.create_task(
        router.call(
            user_id="user-1",
            device_id="device-1",
            session_id="session-1",
            operation="execute",
            payload={"command": "echo hi"},
            timeout_seconds=1,
        )
    )

    await asyncio.sleep(0)
    assert websocket.sent[0]["type"] == "client_sandbox:request"
    assert websocket.sent[0]["operation"] == "execute"

    await router.handle_response(
        "user-1",
        "device-1",
        ClientSandboxRpcResponse(
            request_id=websocket.sent[0]["request_id"],
            ok=True,
            result={"output": "hi\n", "exit_code": 0, "truncated": False},
        ),
    )

    response = await call_task
    assert response.result == {"output": "hi\n", "exit_code": 0, "truncated": False}


@pytest.mark.asyncio
async def test_call_fails_when_device_offline() -> None:
    router = ClientSandboxRouter()

    with pytest.raises(ClientSandboxRouterError) as exc:
        await router.call(
            user_id="user-1",
            device_id="missing",
            session_id="session-1",
            operation="execute",
            payload={},
            timeout_seconds=1,
        )

    assert exc.value.code == "device_offline"


@pytest.mark.asyncio
async def test_list_connected_device_ids_for_user() -> None:
    router = ClientSandboxRouter()
    await router.register_connection("user-1", "device-1", FakeWebSocket())
    await router.register_connection("user-1", "device-2", FakeWebSocket())
    await router.register_connection("user-2", "device-3", FakeWebSocket())

    assert await router.list_connected_device_ids("user-1") == ["device-1", "device-2"]


@pytest.mark.asyncio
async def test_call_timeout_removes_pending_request() -> None:
    router = ClientSandboxRouter()
    websocket = FakeWebSocket()
    await router.register_connection("user-1", "device-1", websocket)

    with pytest.raises(ClientSandboxRouterError) as exc:
        await router.call(
            user_id="user-1",
            device_id="device-1",
            session_id="session-1",
            operation="execute",
            payload={},
            timeout_seconds=0.01,
        )

    assert exc.value.code == "timeout"
    assert router.pending_count == 0


@pytest.mark.asyncio
async def test_unknown_response_is_ignored() -> None:
    router = ClientSandboxRouter()

    handled = await router.handle_response(
        "user-1",
        "device-1",
        ClientSandboxRpcResponse(
            request_id="unknown",
            ok=True,
            result={"value": 1},
        ),
    )

    assert handled is False

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes import client_sandbox as client_sandbox_route


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accept_calls = 0
        self.sent_texts: list[str] = []
        self.closed: list[tuple[int, str]] = []
        self._messages = [
            json.dumps(
                {
                    "type": "client_sandbox:register",
                    "device_id": "device-1",
                    "name": "LambChat Desktop",
                    "platform": "tauri",
                    "os": "linux",
                    "app_version": "2.5.3",
                    "workspace_root": "~/LambChatWorkspace",
                    "capabilities": {
                        "execute": True,
                        "read_file": True,
                        "write_file": True,
                        "list": True,
                    },
                }
            )
        ]

    async def accept(self) -> None:
        self.accept_calls += 1

    async def receive_text(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise client_sandbox_route.WebSocketDisconnect()

    async def send_text(self, value: str) -> None:
        self.sent_texts.append(value)

    async def close(self, code: int, reason: str) -> None:
        self.closed.append((code, reason))


class _Storage:
    def __init__(self) -> None:
        self.devices: list[tuple[str, Any]] = []

    async def upsert_device(self, user_id: str, registration: Any) -> Any:
        self.devices.append((user_id, registration))
        return registration


class _Router:
    def __init__(self) -> None:
        self.connections: list[tuple[str, str, Any]] = []
        self.disconnections: list[tuple[str, str, Any]] = []

    async def register_connection(self, user_id: str, device_id: str, websocket: Any) -> None:
        self.connections.append((user_id, device_id, websocket))

    async def disconnect(self, user_id: str, device_id: str, websocket: Any) -> None:
        self.disconnections.append((user_id, device_id, websocket))


@pytest.mark.asyncio
async def test_client_sandbox_websocket_accepts_query_token_and_registers_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _Storage()
    router = _Router()

    async def fake_current_user(token: str):
        assert token == "token-1"
        return SimpleNamespace(sub="user-1")

    monkeypatch.setattr(
        client_sandbox_route,
        "get_current_user_from_websocket",
        fake_current_user,
    )
    monkeypatch.setattr(client_sandbox_route, "ClientSandboxStorage", lambda: storage)
    monkeypatch.setattr(client_sandbox_route, "get_client_sandbox_router", lambda: router)

    websocket = _FakeWebSocket()
    await client_sandbox_route.client_sandbox_websocket(websocket, token="token-1")

    assert websocket.accept_calls == 1
    assert [json.loads(item)["type"] for item in websocket.sent_texts] == [
        "auth:ok",
        "client_sandbox:registered",
    ]
    assert storage.devices[0][0] == "user-1"
    assert storage.devices[0][1].device_id == "device-1"
    assert router.connections == [("user-1", "device-1", websocket)]
    assert router.disconnections == [("user-1", "device-1", websocket)]


@pytest.mark.asyncio
async def test_client_sandbox_websocket_ignores_legacy_auth_message_after_query_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _Storage()
    router = _Router()

    async def fake_current_user(token: str):
        assert token == "token-1"
        return SimpleNamespace(sub="user-1")

    monkeypatch.setattr(
        client_sandbox_route,
        "get_current_user_from_websocket",
        fake_current_user,
    )
    monkeypatch.setattr(client_sandbox_route, "ClientSandboxStorage", lambda: storage)
    monkeypatch.setattr(client_sandbox_route, "get_client_sandbox_router", lambda: router)

    websocket = _FakeWebSocket()
    websocket._messages.insert(0, json.dumps({"type": "auth", "token": "token-1"}))

    await client_sandbox_route.client_sandbox_websocket(websocket, token="token-1")

    assert [json.loads(item)["type"] for item in websocket.sent_texts] == [
        "auth:ok",
        "client_sandbox:registered",
    ]
    assert router.connections == [("user-1", "device-1", websocket)]

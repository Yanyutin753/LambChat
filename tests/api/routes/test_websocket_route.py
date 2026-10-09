from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes import websocket as websocket_route


class _FakeWebSocket:
    def __init__(self) -> None:
        self.client = SimpleNamespace(host="127.0.0.1")
        self.accept_calls = 0
        self.sent_texts: list[str] = []
        self.closed: list[tuple[int, str]] = []
        self._messages = ['{"type": "auth", "token": "token-1"}']

    async def accept(self) -> None:
        self.accept_calls += 1

    async def receive_text(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise websocket_route.WebSocketDisconnect()

    async def send_text(self, value: str) -> None:
        self.sent_texts.append(value)

    async def close(self, code: int, reason: str) -> None:
        self.closed.append((code, reason))


class _RateLimiter:
    async def check(self, _client_ip: str):
        return True, 0

    async def reset(self, _client_ip: str) -> None:
        return None

    async def record_failure(self, _client_ip: str):
        return False, 0


class _Manager:
    def __init__(self) -> None:
        self.connected: list[tuple[Any, str, bool]] = []
        self.disconnected: list[tuple[Any, str]] = []

    async def connect(self, websocket: Any, user_id: str, accept: bool = True) -> None:
        self.connected.append((websocket, user_id, accept))

    async def disconnect(self, websocket: Any, user_id: str) -> None:
        self.disconnected.append((websocket, user_id))


@pytest.mark.asyncio
async def test_websocket_auth_message_offloads_json_parse_and_auth_ok_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    manager = _Manager()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    async def fake_current_user(token: str):
        assert token == "token-1"
        return SimpleNamespace(sub="user-1")

    monkeypatch.setattr(websocket_route, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(websocket_route, "get_ws_rate_limiter", lambda: _RateLimiter())
    monkeypatch.setattr(websocket_route, "get_current_user_from_websocket", fake_current_user)
    monkeypatch.setattr(websocket_route, "get_connection_manager", lambda: manager)

    websocket = _FakeWebSocket()
    await websocket_route.websocket_endpoint(websocket, token=None)

    assert calls == [json.loads, json.dumps]
    assert websocket.sent_texts == ['{"type": "auth:ok"}']
    assert manager.connected == [(websocket, "user-1", False)]


@pytest.mark.parametrize("idle", [False, True])
async def test_established_socket_closes_when_authority_is_revoked(monkeypatch, idle):
    from unittest.mock import AsyncMock

    from src.kernel.errors import AppError, ErrorCode

    clock = iter([0, 0, 15])
    monkeypatch.setattr(websocket_route, "monotonic", lambda: next(clock))
    manager = _Manager()
    socket = _FakeWebSocket()
    socket.receive_text = AsyncMock(
        side_effect=TimeoutError() if idle else ["heartbeat", websocket_route.WebSocketDisconnect()]
    )
    monkeypatch.setattr(websocket_route, "get_ws_rate_limiter", lambda: _RateLimiter())
    monkeypatch.setattr(websocket_route, "get_connection_manager", lambda: manager)
    auth = AsyncMock(
        side_effect=[SimpleNamespace(sub="user-1"), AppError(ErrorCode.ACCOUNT_NOT_ACTIVE)]
    )
    monkeypatch.setattr(websocket_route, "get_current_user_from_websocket", auth)
    await websocket_route.websocket_endpoint(socket, token="token")
    assert socket.closed == [(4001, "unauthorized")]
    assert manager.disconnected == [(socket, "user-1")]
    assert auth.await_count == 2


async def test_client_messages_do_not_amplify_or_delay_auth_rechecks(monkeypatch):
    from unittest.mock import AsyncMock

    from src.kernel.errors import AppError, ErrorCode

    manager = _Manager()
    socket = _FakeWebSocket()
    socket.receive_text = AsyncMock(
        side_effect=["one", "two", "three", websocket_route.WebSocketDisconnect()]
    )
    clock = iter([0, 0, 1, 1, 2, 2, 15])
    monkeypatch.setattr(websocket_route, "monotonic", lambda: next(clock), raising=False)
    monkeypatch.setattr(websocket_route, "get_ws_rate_limiter", lambda: _RateLimiter())
    monkeypatch.setattr(websocket_route, "get_connection_manager", lambda: manager)
    auth = AsyncMock(
        side_effect=[SimpleNamespace(sub="user-1"), AppError(ErrorCode.ACCOUNT_NOT_ACTIVE)]
    )
    monkeypatch.setattr(websocket_route, "get_current_user_from_websocket", auth)
    await websocket_route.websocket_endpoint(socket, token="token")
    assert socket.receive_text.await_count == 3
    assert auth.await_count == 2
    assert socket.closed == [(4001, "unauthorized")]

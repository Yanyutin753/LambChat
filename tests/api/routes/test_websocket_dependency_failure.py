"""WebSocket authority outages must not look like rejected credentials on the wire."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import websocket as route
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("phase", ["initial", "recheck"])
@pytest.mark.parametrize(
    "error_code,close_code",
    [(ErrorCode.SERVICE_UNAVAILABLE, 1013), (ErrorCode.INVALID_TOKEN, 4001)],
)
async def test_websocket_authority_failure_close_classification(
    monkeypatch, phase, error_code, close_code
):
    socket = SimpleNamespace(
        client=SimpleNamespace(host="owned-peer"),
        accept=AsyncMock(),
        close=AsyncMock(),
        send_text=AsyncMock(),
        receive_text=AsyncMock(side_effect=TimeoutError()),
    )
    limiter = SimpleNamespace(
        check=AsyncMock(return_value=(True, 0)),
        reset=AsyncMock(),
        record_failure=AsyncMock(return_value=(False, 0)),
    )
    manager = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(route, "get_ws_rate_limiter", lambda: limiter)
    monkeypatch.setattr(route, "get_connection_manager", lambda: manager)
    failures = (
        [AppError(error_code)]
        if phase == "initial"
        else [TokenPayload(sub="owner", username="owner"), AppError(error_code)]
    )
    monkeypatch.setattr(route, "get_current_user_from_websocket", AsyncMock(side_effect=failures))
    ticks = iter([0, 16, 16])
    monkeypatch.setattr(route, "monotonic", lambda: next(ticks))

    await route.websocket_endpoint(socket, "synthetic")

    assert socket.close.await_args.kwargs["code"] == close_code
    if error_code is ErrorCode.SERVICE_UNAVAILABLE:
        assert socket.close.await_args.kwargs["reason"] == "service_unavailable"
        limiter.record_failure.assert_not_awaited()

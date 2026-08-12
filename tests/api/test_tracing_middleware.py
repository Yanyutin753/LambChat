from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.middleware.tracing import TracingMiddleware
from src.api.server_timing import timed_server_phase


@pytest.mark.asyncio
async def test_tracing_middleware_emits_phase_and_process_timing_headers() -> None:
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/timed")
    async def timed_route():
        async with timed_server_phase("session_detail"):
            pass
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/timed")

    assert response.status_code == 200
    assert response.headers["Server-Timing"].startswith("session_detail;dur=")
    assert "X-Process-Time" in response.headers
    assert "timed" not in response.headers["Server-Timing"]


@pytest.mark.asyncio
async def test_tracing_middleware_does_not_leak_metrics_between_requests() -> None:
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/timed")
    async def timed_route():
        async with timed_server_phase("history"):
            pass
        return {"ok": True}

    @app.get("/plain")
    async def plain_route():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        timed_response = await client.get("/timed")
        plain_response = await client.get("/plain")

    assert "history;dur=" in timed_response.headers["Server-Timing"]
    assert "Server-Timing" not in plain_response.headers

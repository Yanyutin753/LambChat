"""响应 gzip 压缩：大 JSON 压缩、SSE 与小响应不压缩。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from src.api.middleware.compression import add_compression_middleware

MAIN_PY = Path(__file__).resolve().parents[2] / "src" / "api" / "main.py"


def _build_app() -> TestClient:
    app = FastAPI()

    @app.get("/api/big")
    async def big() -> dict:
        return {"events": [{"data": {"content": "x" * 64}} for _ in range(64)]}

    @app.get("/api/small")
    async def small() -> dict:
        return {"ok": True}

    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        async def gen():
            yield b"data: hello\n\n"
            yield b"data: world\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    add_compression_middleware(app)
    return TestClient(app)


def test_large_json_response_is_gzipped() -> None:
    with _build_app() as client:
        response = client.get("/api/big", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert len(response.headers.get("content-length", "")) > 0
    assert response.json()["events"][0]["data"]["content"] == "x" * 64


def test_small_response_is_not_gzipped() -> None:
    with _build_app() as client:
        response = client.get("/api/small", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None


def test_sse_stream_is_never_gzipped() -> None:
    """SSE 逐块冲刷语义不能被压缩缓冲破坏——必须原样透传。"""
    with _build_app() as client:
        response = client.get("/api/stream", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None
    assert b"data: hello" in response.content


def test_without_gzip_acceptance_response_stays_plain() -> None:
    with _build_app() as client:
        response = client.get("/api/big", headers={"Accept-Encoding": "identity"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None


def test_main_app_registers_compression_middleware() -> None:
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "add_compression_middleware(app)" in source, (
        "src/api/main.py 必须注册 gzip 压缩中间件（历史事件等大 JSON 响应 20MB+ 不压缩会卡 UI）"
    )

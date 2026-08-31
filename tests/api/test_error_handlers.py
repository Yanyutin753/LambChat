"""全局异常处理器：统一错误响应契约 {"detail": {code, message, args}}。"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.error_handlers import register_error_handlers
from src.kernel.errors import AppError, ErrorCode


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/app-error")
    async def app_error():
        raise AppError(ErrorCode.SESSION_NOT_FOUND, args={"session_id": "s1"})

    @app.get("/kernel-error")
    async def kernel_error():
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=404, detail="legacy message")

    @app.get("/validate")
    async def validate(q: int):
        return {"q": q}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret stack")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_shape():
    resp = _client().get("/app-error")
    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["code"] == "session_not_found"
    assert body["message"] == "Session not found"
    assert body["args"] == {"session_id": "s1"}


def test_kernel_error_bubbles_to_handler():
    resp = _client().get("/kernel-error")
    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["code"] == "message_not_found"


def test_http_exception_fallback():
    resp = _client().get("/http-error")
    assert resp.status_code == 404
    body = resp.json()["detail"]
    assert body["code"] == "not_found"
    assert body["message"] == "legacy message"


def test_validation_error_shape():
    resp = _client().get("/validate")
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["code"] == "validation_error"
    assert "q" in str(body["args"])


def test_unhandled_error_shape():
    resp = _client().get("/boom")
    assert resp.status_code == 500
    body = resp.json()["detail"]
    assert body["code"] == "internal_error"
    assert "secret" not in body["message"]


def test_args_omitted_when_empty():
    resp = _client().get("/kernel-error")
    assert "args" not in resp.json()["detail"]

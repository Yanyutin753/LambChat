"""
全局异常处理器：统一错误响应契约。

所有错误响应序列化为::

    {"detail": {"code": "<snake_case>", "message": "<英文兜底>", "args": {...}}}

``args`` 仅在非空时出现。SSE 侧错误事件的 payload 构造复用 ``error_payload``。
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.kernel.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

_STATUS_FALLBACK_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.TOO_MANY_REQUESTS,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def error_payload(code: str, message: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造统一错误 detail 对象；args 为空时省略。"""
    payload: dict[str, Any] = {"code": code, "message": message}
    if args:
        payload["args"] = args
    return payload


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": error_payload(exc.error_code.code, exc.message, exc.args_data)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_FALLBACK_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else code.default_message
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": error_payload(code.code, message)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": error_payload(
                    "validation_error", "Request validation failed", {"fields": fields}
                )
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": error_payload("internal_error", "Internal server error")},
        )

from __future__ import annotations

import logging

import httpx
import openai as openai_module
import pytest

from src.infra.llm.retry import ainvoke_with_retry, is_auth_model_error, is_retryable_model_error


def _openai_status_error(error_cls, status_code: int):

    response = httpx.Response(
        status_code=status_code, request=httpx.Request("POST", "http://test/v1/chat")
    )
    body = {"error": {"message": "Invalid token", "type": "new_api_error"}}
    return error_cls(f"Error code: {status_code} - {body}", response=response, body=body)


def _anthropic_status_error(error_cls, status_code: int):

    response = httpx.Response(
        status_code=status_code, request=httpx.Request("POST", "http://test/v1/messages")
    )
    body = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "invalid x-api-key"},
    }
    return error_cls(f"Error code: {status_code} - {body}", response=response, body=body)


class _Model:
    def __init__(self, failures: list[Exception], result: object = "ok") -> None:
        self.failures = failures
        self.result = result
        self.calls = 0

    async def ainvoke(self, prompt, **kwargs):
        del prompt, kwargs
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.result


async def test_ainvoke_retries_three_times_after_initial_timeout() -> None:
    model = _Model([httpx.ReadTimeout("secret-url") for _ in range(3)])

    result = await ainvoke_with_retry(model, "prompt", max_retries=3, retry_delay=0)

    assert result == "ok"
    assert model.calls == 4


async def test_ainvoke_does_not_retry_permanent_error() -> None:
    model = _Model([ValueError("bad request")])

    with pytest.raises(ValueError, match="bad request"):
        await ainvoke_with_retry(model, "prompt", max_retries=3, retry_delay=0)

    assert model.calls == 1


def test_retryable_error_follows_wrapped_timeout_cause() -> None:
    try:
        try:
            raise httpx.ConnectTimeout("provider secret")
        except httpx.ConnectTimeout as exc:
            raise RuntimeError("wrapper secret") from exc
    except RuntimeError as wrapped:
        assert is_retryable_model_error(wrapped) is True


async def test_retry_log_does_not_include_exception_text(caplog) -> None:
    model = _Model([httpx.ReadTimeout("https://secret.example/api?key=abc")])

    with caplog.at_level(logging.WARNING):
        await ainvoke_with_retry(
            model,
            "prompt",
            max_retries=1,
            retry_delay=0,
            operation="session-title",
        )

    assert "ReadTimeout" in caplog.text
    assert "session-title" in caplog.text
    assert "secret.example" not in caplog.text
    assert "key=abc" not in caplog.text


def test_auth_error_detects_openai_401() -> None:
    import openai

    exc = _openai_status_error(openai.AuthenticationError, 401)

    assert is_auth_model_error(exc) is True
    # 401 不是同模型可重试错误：重试同一把 key 没有意义
    assert is_retryable_model_error(exc) is False


def test_auth_error_detects_openai_403() -> None:
    import openai

    exc = _openai_status_error(openai.PermissionDeniedError, 403)

    assert is_auth_model_error(exc) is True


def test_auth_error_detects_anthropic_401() -> None:
    import anthropic

    exc = _anthropic_status_error(anthropic.AuthenticationError, 401)

    assert is_auth_model_error(exc) is True
    assert is_retryable_model_error(exc) is False


def test_auth_error_follows_wrapped_exception_chain() -> None:
    import openai

    inner = _openai_status_error(openai.AuthenticationError, 401)
    try:
        try:
            raise inner
        except openai.AuthenticationError as exc:
            raise RuntimeError("summary call failed") from exc
    except RuntimeError as wrapped:
        assert is_auth_model_error(wrapped) is True


def test_auth_error_detects_proxy_rewritten_message() -> None:
    # 部分中转把上游 401 重写成普通异常，仅保留 "Error code: 401 - ..." 文案
    exc = ValueError("Error code: 401 - {'error': {'message': 'Invalid token'}}")

    assert is_auth_model_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        _openai_status_error(openai_module.RateLimitError, 429),
        _openai_status_error(openai_module.InternalServerError, 500),
        ValueError("Error code: 429 - rate limited"),
        ValueError("boom"),
        httpx.ConnectTimeout("connection reset"),
    ],
    ids=["rate-limit-429", "server-error-500", "429-message", "generic", "transport"],
)
def test_auth_error_ignores_non_auth_failures(exc) -> None:
    assert is_auth_model_error(exc) is False

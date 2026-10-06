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


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504])
def test_retryable_http_status_is_protocol_independent(status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://model.invalid"))
    assert is_retryable_model_error(
        httpx.HTTPStatusError("upstream", request=response.request, response=response)
    )


async def test_direct_call_switches_to_fallback_after_primary_retries(monkeypatch):
    from src.infra.llm.client import LLMClient

    primary = _Model([TimeoutError()] * 2)
    backup = _Model([], result="backup answer")

    async def get_model(**kwargs):
        assert kwargs["model"] == "backup-model"
        return backup

    monkeypatch.setattr(LLMClient, "get_model", get_model)
    assert (
        await ainvoke_with_retry(
            primary, "prompt", max_retries=1, retry_delay=0, fallback_model="backup-model"
        )
        == "backup answer"
    )
    assert primary.calls == 2


async def test_direct_call_switches_auth_failure_without_retrying_same_key(monkeypatch):
    from src.infra.llm.client import LLMClient

    primary = _Model([_openai_status_error(openai_module.AuthenticationError, 401)])

    async def get_model(**kwargs):
        return _Model([], result="backup answer")

    monkeypatch.setattr(LLMClient, "get_model", get_model)
    assert (
        await ainvoke_with_retry(
            primary, "prompt", max_retries=3, retry_delay=0, fallback_model="backup-model"
        )
        == "backup answer"
    )
    assert primary.calls == 1


async def test_streamed_output_is_not_replayed_on_later_failure():
    class StreamingModel(_Model):
        async def ainvoke(self, prompt, **kwargs):
            self.calls += 1
            for callback in kwargs["config"]["callbacks"]:
                await callback.on_llm_new_token("already delivered", run_id=None)
            raise TimeoutError("stream interrupted")

    model = StreamingModel([])
    with pytest.raises(TimeoutError):
        await ainvoke_with_retry(
            model, "prompt", max_retries=3, retry_delay=0, fallback_model="backup-model", config={}
        )
    assert model.calls == 1


async def test_empty_answer_retries_before_fallback(monkeypatch):
    from langchain_core.messages import AIMessage

    from src.infra.llm.client import LLMClient

    primary = _Model([], result=AIMessage(content=""))

    async def get_model(**kwargs):
        return _Model([], result=AIMessage(content="backup answer"))

    monkeypatch.setattr(LLMClient, "get_model", get_model)
    result = await ainvoke_with_retry(
        primary, "prompt", max_retries=1, retry_delay=0, fallback_model="backup-model"
    )
    assert result.content == "backup answer"
    assert primary.calls == 2


async def test_cancelled_direct_call_never_retries_or_falls_back():
    import asyncio

    model = _Model([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await ainvoke_with_retry(
            model, "prompt", max_retries=3, retry_delay=0, fallback_model="backup"
        )
    assert model.calls == 1


async def test_failed_fallback_has_bounded_retries_and_never_cycles(monkeypatch):
    from src.infra.llm.client import LLMClient

    primary = _Model([TimeoutError()] * 2)
    fallback = _Model([TimeoutError()] * 2)

    async def get_model(**kwargs):
        return fallback

    monkeypatch.setattr(LLMClient, "get_model", get_model)
    with pytest.raises(TimeoutError):
        await ainvoke_with_retry(
            primary, "prompt", max_retries=1, retry_delay=0, fallback_model="backup"
        )
    assert primary.calls == fallback.calls == 2


async def test_existing_callbacks_and_call_metadata_survive_retries():
    from langchain_core.callbacks import AsyncCallbackHandler

    callback = AsyncCallbackHandler()
    original = {
        "callbacks": [callback],
        "metadata": {"task": "one"},
        "configurable": {"thread_id": "session"},
    }

    class RecordingModel(_Model):
        async def ainvoke(self, prompt, **kwargs):
            assert callback in kwargs["config"]["callbacks"]
            assert kwargs["config"]["metadata"]["task"] == "one"
            assert kwargs["config"]["configurable"]["thread_id"] == "session"
            return await super().ainvoke(prompt, **kwargs)

    model = RecordingModel([TimeoutError()])
    assert (
        await ainvoke_with_retry(model, "prompt", max_retries=1, retry_delay=0, config=original)
        == "ok"
    )
    assert original["callbacks"] == [callback]


async def test_direct_retry_preserves_simple_ainvoke_interface_without_config():
    class SimpleModel:
        async def ainvoke(self, prompt):
            return "answer"

    assert await ainvoke_with_retry(SimpleModel(), "question") == "answer"

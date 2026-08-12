from __future__ import annotations

import logging

import httpx
import pytest

from src.infra.llm.retry import ainvoke_with_retry, is_retryable_model_error


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

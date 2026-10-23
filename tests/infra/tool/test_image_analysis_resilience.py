import asyncio
import logging

import httpx
import pytest

from src.infra.tool import image_analysis_tool as module


async def test_permanent_vision_error_is_not_retried_and_logs_safe_status(monkeypatch, caplog):
    monkeypatch.setattr(module.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(module.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
    calls = 0

    class Model:
        async def ainvoke(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise httpx.HTTPStatusError(
                "secret data:image/png;base64,PRIVATE",
                request=httpx.Request("POST", "https://provider"),
                response=httpx.Response(400),
            )

    with caplog.at_level(logging.WARNING), pytest.raises(httpx.HTTPStatusError):
        await module._call_with_retries(Model(), [])
    assert calls == 1
    assert "status_code=400" in caplog.text
    assert "PRIVATE" not in caplog.text


async def test_vision_call_has_a_bounded_deadline_and_cancels_provider(monkeypatch):
    monkeypatch.setattr(module, "_MODEL_CALL_TIMEOUT_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(module.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 1)
    cancelled = False

    class Model:
        async def ainvoke(self, *args, **kwargs):
            nonlocal cancelled
            try:
                await asyncio.sleep(0.03)
                return "late"
            finally:
                cancelled = True

    with pytest.raises(TimeoutError):
        await module._call_with_retries(Model(), [])
    assert cancelled


def test_provider_diagnostics_include_safe_error_code_without_response_content():
    error = httpx.HTTPStatusError(
        "PRIVATE",
        request=httpx.Request("POST", "https://provider"),
        response=httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_image",
                    "message": "PRIVATE data:image/png;base64,IMAGE",
                }
            },
        ),
    )
    details = module._model_error_details(error)
    assert details == {"status_code": 400, "provider_error": "invalid_image"}
    assert "PRIVATE" not in str(details) and "IMAGE" not in str(details)

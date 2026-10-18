"""Paid tools must check settled spending before sending a vendor request."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.infra.llm import quota
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode


@pytest.fixture
def finite_budget(monkeypatch):
    monkeypatch.setattr(quota, "quota_user_id", lambda: "budget-owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1.0, None)))
    ledger = SimpleNamespace(
        reserve=AsyncMock(side_effect=AppError(ErrorCode.USAGE_QUOTA_EXCEEDED)),
        cancel_unstarted=AsyncMock(),
    )
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)


@pytest.mark.parametrize("provider", ["tavily", "brave"])
async def test_search_denial_sends_no_vendor_request(finite_budget, provider):
    from src.infra.tool import web_search_providers

    client = AsyncMock()
    with pytest.raises(AppError) as error:
        await web_search_providers.PROVIDER_FUNCS[provider](client, "key", "query", 5, None)
    assert error.value.error_code == ErrorCode.USAGE_QUOTA_EXCEEDED
    client.post.assert_not_awaited()
    client.get.assert_not_awaited()


@pytest.mark.parametrize("provider", ["firecrawl", "exa", "tavily", "jina"])
async def test_fetch_denial_sends_no_vendor_request(monkeypatch, finite_budget, provider):
    from src.infra.tool import web_fetch_providers

    monkeypatch.setattr(
        web_fetch_providers, "validate_public_http_url", AsyncMock(return_value=(True, None))
    )
    request = AsyncMock()
    monkeypatch.setattr(web_fetch_providers, "_request_no_redirect", request)
    fetcher = {
        "firecrawl": web_fetch_providers.firecrawl_fetch,
        "exa": web_fetch_providers.exa_fetch,
        "tavily": web_fetch_providers.tavily_extract,
        "jina": web_fetch_providers.jina_fetch,
    }[provider]
    with pytest.raises(AppError) as error:
        await fetcher(AsyncMock(), "https://example.com", "key", 1000)
    assert error.value.error_code == ErrorCode.USAGE_QUOTA_EXCEEDED
    request.assert_not_awaited()


async def test_systemone_denial_is_not_a_fallback(monkeypatch, finite_budget):
    from src.infra.decision import client

    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", "https://example.com")
    calls = []
    transport = httpx.MockTransport(
        lambda request: calls.append(request) or httpx.Response(200, json={})
    )
    with pytest.raises(AppError) as error:
        await client.system_one("state", {}, transport=transport)
    assert error.value.error_code == ErrorCode.USAGE_QUOTA_EXCEEDED
    assert calls == []


async def test_image_generation_denial_sends_no_request(finite_budget):
    from src.infra.tool import image_generation_tool

    client = AsyncMock()
    with pytest.raises(AppError):
        await image_generation_tool._post_image_api_with_retries(
            client, "https://example.com", operation="generate"
        )
    client.post.assert_not_awaited()


@pytest.mark.parametrize("media", ["image", "video"])
async def test_media_analysis_quota_denial_is_never_retried(monkeypatch, media):
    from src.infra.tool import image_analysis_tool, video_analysis_tool

    module = image_analysis_tool if media == "image" else video_analysis_tool
    monkeypatch.setattr(settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3)
    denied = AppError(ErrorCode.USAGE_QUOTA_EXCEEDED)
    llm = AsyncMock()
    llm.ainvoke.side_effect = denied
    with pytest.raises(AppError) as error:
        await module._call_with_retries(llm, [])
    assert error.value is denied
    llm.ainvoke.assert_awaited_once()


async def test_embedding_quota_denial_is_not_silenced():
    from src.infra.memory.client.native.backend import NativeMemoryBackend

    backend = NativeMemoryBackend()
    denied = AppError(ErrorCode.USAGE_QUOTA_UNPRICED)
    backend._embedding_fn = AsyncMock(side_effect=denied)
    with pytest.raises(AppError) as error:
        await backend._maybe_embed("text")
    assert error.value is denied


async def test_configured_embedding_denial_sends_no_request(monkeypatch, finite_budget):
    from src.infra.memory.client.native.backend import NativeMemoryBackend

    monkeypatch.setattr(settings, "NATIVE_MEMORY_EMBEDDING_API_BASE", "https://example.com")
    monkeypatch.setattr(settings, "NATIVE_MEMORY_EMBEDDING_API_KEY", "key")
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    backend = NativeMemoryBackend()
    backend._setup_embedding_fn()
    try:
        with pytest.raises(AppError):
            await backend._maybe_embed("text")
        post.assert_not_awaited()
    finally:
        await backend._httpx_client.aclose()


async def test_rerank_denial_is_not_a_local_fallback(monkeypatch, finite_budget):
    from src.infra.memory.client.native import search

    for name, value in {
        "NATIVE_MEMORY_RERANK_MODEL": "rerank",
        "NATIVE_MEMORY_RERANK_API_BASE": "https://example.com",
        "NATIVE_MEMORY_RERANK_API_KEY": "key",
    }.items():
        monkeypatch.setattr(settings, name, value)
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(AppError):
        await search.rerank_candidates("query", [{"text": "one"}, {"text": "two"}], 2)
    post.assert_not_awaited()


@pytest.mark.parametrize("provider", ["mistral", "mineru", "azure", "paddleocr_vl"])
async def test_ocr_denial_sends_no_vendor_request(monkeypatch, finite_budget, provider):
    from src.infra.tool import document_parse_providers

    configured = {
        "DOCUMENT_PARSE_MISTRAL_API_KEY": "key",
        "DOCUMENT_PARSE_MINERU_API_KEY": "key",
        "DOCUMENT_PARSE_AZURE_ENDPOINT": "https://example.com",
        "DOCUMENT_PARSE_AZURE_KEY": "key",
        "DOCUMENT_PARSE_PADDLEOCR_URL": "https://example.com",
        "DOCUMENT_PARSE_PADDLEOCR_TOKEN": "key",
    }
    for name, value in configured.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(document_parse_providers, "_mineru_mode", lambda: "cloud")
    client = AsyncMock()
    with pytest.raises(AppError) as error:
        await document_parse_providers.PROVIDER_FUNCS[provider](
            client,
            data=b"pdf",
            filename="file.pdf",
            include_images=False,
            pages=None,
            image_limit=0,
        )
    assert error.value.error_code == ErrorCode.USAGE_QUOTA_EXCEEDED
    client.post.assert_not_awaited()
    client.put.assert_not_awaited()


async def test_audio_denial_closes_client_without_transcription(monkeypatch, finite_budget):
    from src.infra.tool import audio_transcribe_tool

    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=AsyncMock())),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(audio_transcribe_tool, "_build_client", lambda: client)
    http_client = httpx.AsyncClient
    monkeypatch.setattr(
        audio_transcribe_tool.httpx,
        "AsyncClient",
        lambda **kwargs: http_client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"audio")),
        ),
    )
    with pytest.raises(AppError):
        await audio_transcribe_tool.audio_transcribe.coroutine(url="https://example.com/audio.wav")
    client.audio.transcriptions.create.assert_not_awaited()
    client.aclose.assert_awaited_once()


@pytest.mark.parametrize("media", ["image", "video"])
async def test_media_outer_handler_propagates_quota_error(monkeypatch, media):
    from src.infra.tool import image_analysis_tool, video_analysis_tool

    monkeypatch.setattr(settings, "IMAGE_ANALYSIS_MODEL_ID", "vision")
    denied = AppError(ErrorCode.USAGE_QUOTA_EXCEEDED)
    monkeypatch.setattr(image_analysis_tool, "_resolve_model_config", AsyncMock(side_effect=denied))
    with pytest.raises(AppError) as error:
        if media == "image":
            await image_analysis_tool.image_analyze.coroutine(
                image_urls=["https://example.com/image.png"]
            )
        else:
            await video_analysis_tool.video_analyze.coroutine(video_urls=["/workspace/video.mp4"])
    assert error.value is denied


@pytest.mark.parametrize("provider", ["firecrawl", "jina"])
async def test_keyless_free_fetch_still_works(monkeypatch, finite_budget, provider):
    from src.infra.tool import web_fetch_providers

    monkeypatch.setattr(
        web_fetch_providers, "validate_public_http_url", AsyncMock(return_value=(True, None))
    )
    response = httpx.Response(200, json={"success": True, "data": {"markdown": "content"}})
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(web_fetch_providers, "_request_no_redirect", request)
    fetcher = (
        web_fetch_providers.firecrawl_fetch
        if provider == "firecrawl"
        else web_fetch_providers.jina_fetch
    )
    result = await fetcher(AsyncMock(), "https://example.com", "", 1000)
    assert result["success"] is True
    request.assert_awaited_once()


async def test_quota_denial_stops_search_key_rotation_and_fallback(monkeypatch):
    from src.infra.tool import web_search_providers

    denied = AppError(ErrorCode.USAGE_QUOTA_UNPRICED)
    tavily, brave = AsyncMock(side_effect=denied), AsyncMock()
    monkeypatch.setattr(web_search_providers, "resolve_provider_chain", lambda: ["tavily", "brave"])
    monkeypatch.setattr(
        web_search_providers,
        "_get_pool",
        lambda provider: web_search_providers.ApiKeyPool(["one", "two"]),
    )
    monkeypatch.setitem(web_search_providers.PROVIDER_FUNCS, "tavily", tavily)
    monkeypatch.setitem(web_search_providers.PROVIDER_FUNCS, "brave", brave)
    with pytest.raises(AppError) as error:
        await web_search_providers.execute_web_search("query", 5)
    assert error.value is denied
    tavily.assert_awaited_once()
    brave.assert_not_awaited()


async def test_memory_retry_does_not_retry_quota_denial():
    from src.infra.memory.client.base import with_retry

    denied = AppError(ErrorCode.USAGE_QUOTA_UNPRICED)
    operation = AsyncMock(side_effect=denied)
    with pytest.raises(AppError) as error:
        await with_retry(operation, semaphore=asyncio.Semaphore(1))
    assert error.value is denied
    operation.assert_awaited_once()

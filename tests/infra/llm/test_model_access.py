from __future__ import annotations

import asyncio
import warnings

import pytest

from src.infra.llm.client import LLMClient
from src.infra.llm.models_service import clear_api_key_cache, set_cached_api_key
from src.kernel.exceptions import AuthorizationError
from src.kernel.schemas.model import ModelConfig


class _ModelStorage:
    def __init__(self, model: ModelConfig | None) -> None:
        self.model = model

    async def get(self, model_id: str) -> ModelConfig | None:
        return self.model if self.model and self.model.id == model_id else None

    async def get_by_value(self, value: str) -> ModelConfig | None:
        return self.model if self.model and self.model.value == value else None


@pytest.mark.asyncio
async def test_clear_cache_by_model_tracks_and_drains_async_client_close() -> None:
    close_started = False
    close_finished = False

    class _FakeAsyncClient:
        async def aclose(self) -> None:
            nonlocal close_started, close_finished
            close_started = True
            await asyncio.sleep(0.01)
            close_finished = True

    class _FakeModel:
        async_client = _FakeAsyncClient()

    LLMClient._model_cache.clear()
    LLMClient._model_cache[
        (
            "openai",
            "gpt-test",
            0.7,
            None,
            "sk-test",
            None,
            None,
            None,
            3,
        )
    ] = _FakeModel()  # type: ignore[assignment]

    assert LLMClient.clear_cache_by_model() == 1
    assert close_started is False

    await LLMClient.drain_close_tasks(timeout=1)

    assert close_started is True
    assert close_finished is True


@pytest.mark.asyncio
async def test_clear_cache_by_model_accepts_future_returned_by_async_client_close() -> None:
    loop = asyncio.get_running_loop()
    close_future = loop.create_future()
    loop.call_later(0.01, close_future.set_result, None)

    class _FakeAsyncClient:
        def aclose(self):
            return close_future

    class _FakeModel:
        async_client = _FakeAsyncClient()

    LLMClient._model_cache.clear()
    LLMClient._model_cache[
        (
            "openai",
            "gpt-test",
            0.7,
            None,
            "sk-test",
            None,
            None,
            None,
            3,
        )
    ] = _FakeModel()  # type: ignore[assignment]

    assert LLMClient.clear_cache_by_model() == 1
    await LLMClient.drain_close_tasks(timeout=1)

    assert close_future.done() is True


@pytest.mark.asyncio
async def test_close_cached_models_closes_and_clears_all_model_instances() -> None:
    closed: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, name: str) -> None:
            self.name = name

        async def aclose(self) -> None:
            closed.append(self.name)

    class _FakeModel:
        def __init__(self, name: str) -> None:
            self.async_client = _FakeAsyncClient(name)

    LLMClient._model_cache.clear()
    LLMClient._model_cache[
        (
            "openai",
            "gpt-a",
            0.7,
            None,
            "sk-test-a",
            None,
            None,
            None,
            3,
        )
    ] = _FakeModel("a")  # type: ignore[assignment]
    LLMClient._model_cache[
        (
            "openai",
            "gpt-b",
            0.7,
            None,
            "sk-test-b",
            None,
            None,
            None,
            3,
        )
    ] = _FakeModel("b")  # type: ignore[assignment]

    assert LLMClient.close_cached_models() == 2
    await LLMClient.drain_close_tasks(timeout=1)

    assert sorted(closed) == ["a", "b"]
    assert LLMClient._model_cache == {}


@pytest.mark.asyncio
async def test_get_model_rejects_disabled_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled_model = ModelConfig(
        id="disabled-model",
        value="openai/gpt-disabled",
        label="Disabled",
        enabled=False,
    )
    storage = _ModelStorage(disabled_model)

    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: storage,
    )

    with pytest.raises(AuthorizationError, match="model_disabled"):
        await LLMClient.get_model(model_id="disabled-model")


@pytest.mark.asyncio
async def test_get_model_rejects_unknown_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _ModelStorage(None)

    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: storage,
    )

    with pytest.raises(AuthorizationError, match="model_not_found"):
        await LLMClient.get_model(model_id="missing-model")


@pytest.mark.asyncio
async def test_get_model_uses_cached_key_for_sanitized_google_model_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_api_key_cache()
    LLMClient.clear_cache_by_model()
    set_cached_api_key("gemini-3.1-pro-preview", "gemini-secret")

    captured: dict = {}

    class FakeChatGoogleGenerativeAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "src.infra.llm.client.ChatGoogleGenerativeAI",
        FakeChatGoogleGenerativeAI,
    )

    await LLMClient.get_model(
        model_config={
            "id": "google-model",
            "value": "gemini-3.1-pro-preview",
            "provider": "gemini",
            "label": "Gemini",
            "api_key": None,
            "api_base": "https://example.test",
            "enabled": True,
        },
    )

    assert captured["google_api_key"].get_secret_value() == "gemini-secret"
    assert captured["base_url"] == "https://example.test"

    clear_api_key_cache()
    LLMClient.clear_cache_by_model()


@pytest.mark.asyncio
async def test_get_model_rehydrates_key_for_sanitized_anthropic_model_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_api_key_cache()
    LLMClient.clear_cache_by_model()

    stored_model = ModelConfig(
        id="anthropic-model",
        value="anthropic/claude-3-5-sonnet-latest",
        provider="anthropic",
        label="Claude",
        api_key="anthropic-secret",
        api_base="https://example.test",
        enabled=True,
    )
    storage = _ModelStorage(stored_model)
    captured: dict = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.llm.client.ChatAnthropic",
        FakeChatAnthropic,
    )

    await LLMClient.get_model(
        model_config={
            "id": "anthropic-model",
            "value": "anthropic/claude-3-5-sonnet-latest",
            "provider": "anthropic",
            "label": "Claude",
            "api_key": None,
            "api_base": "https://example.test",
            "enabled": True,
        },
    )

    assert captured["api_key"].get_secret_value() == "anthropic-secret"
    assert captured["base_url"] == "https://example.test"

    clear_api_key_cache()
    LLMClient.clear_cache_by_model()


@pytest.mark.asyncio
async def test_get_model_rejects_sanitized_anthropic_config_when_key_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_api_key_cache()
    LLMClient.clear_cache_by_model()
    storage = _ModelStorage(None)

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: storage,
    )

    with pytest.raises(AuthorizationError, match="model_api_key_missing"):
        await LLMClient.get_model(
            model_config={
                "id": "anthropic-model",
                "value": "anthropic/claude-3-5-sonnet-latest",
                "provider": "anthropic",
                "label": "Claude",
                "api_key": None,
                "enabled": True,
            },
        )

    clear_api_key_cache()
    LLMClient.clear_cache_by_model()


def test_create_model_does_not_forward_app_only_profile_keys() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        model = LLMClient._create_model(
            "openai",
            "gpt-4.1",
            temperature=0.7,
            api_key="sk-test",
            profile={
                "max_input_tokens": 128000,
                "supports_vision": True,
                "image_url_to_base64": True,
            },
        )

    assert model.profile == {"max_input_tokens": 128000}
    assert not [
        warning
        for warning in caught
        if "Unrecognized keys in model profile" in str(warning.message)
    ]


@pytest.mark.asyncio
async def test_get_model_preserves_inferred_provider_for_known_unprefixed_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_api_key_cache()
    LLMClient.clear_cache_by_model()

    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.profile = kwargs.get("profile")

    monkeypatch.setattr(
        "src.infra.llm.client.ChatOpenAI",
        FakeChatOpenAI,
    )

    async def fake_get_default_model() -> str:
        return "openai/gpt-4.1"

    async def fake_get_available_models() -> list[dict]:
        return []

    monkeypatch.setattr(
        "src.infra.llm.models_service.get_default_model",
        fake_get_default_model,
    )
    monkeypatch.setattr(
        "src.infra.llm.models_service.get_available_models",
        fake_get_available_models,
    )

    await LLMClient.get_model(model="deepseek-v4-flash", api_key="sk-test")

    assert captured["model"] == "deepseek-v4-flash"
    assert "model_kwargs" not in captured

    clear_api_key_cache()
    LLMClient.clear_cache_by_model()


@pytest.mark.asyncio
async def test_get_model_caches_streaming_and_non_streaming_instances_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_api_key_cache()
    LLMClient.clear_cache_by_model()

    created: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = dict(kwargs)
            created.append(self.kwargs)

    monkeypatch.setattr("src.infra.llm.client.ChatOpenAI", FakeChatOpenAI)

    streaming_model = await LLMClient.get_model(
        model="openai/gpt-4.1",
        api_key="sk-test",
        use_model_config=False,
    )
    non_streaming_model = await LLMClient.get_model(
        model="openai/gpt-4.1",
        api_key="sk-test",
        streaming=False,
        use_model_config=False,
    )
    cached_non_streaming_model = await LLMClient.get_model(
        model="openai/gpt-4.1",
        api_key="sk-test",
        streaming=False,
        use_model_config=False,
    )

    assert streaming_model is not non_streaming_model
    assert cached_non_streaming_model is non_streaming_model
    assert [item["streaming"] for item in created] == [True, False]

    clear_api_key_cache()
    LLMClient.clear_cache_by_model()

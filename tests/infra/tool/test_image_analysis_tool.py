import base64
import json
import logging
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.kernel.schemas.model import ModelConfig, ModelProfile


class _Runtime:
    def __init__(
        self,
        user_id: str | None = "user-1",
        base_url: str = "https://app.example.com",
        backend: object | None = None,
    ):
        context = SimpleNamespace(user_id=user_id) if user_id else None
        configurable = {"context": context, "base_url": base_url}
        if backend is not None:
            configurable["backend"] = backend
        self.config = {"configurable": configurable}


class _FakeStorage:
    def __init__(self, model: ModelConfig | None):
        self.model = model
        self.requested: list[str] = []

    async def get(self, model_id: str):
        self.requested.append(model_id)
        return self.model if self.model and self.model.id == model_id else None

    async def get_by_value(self, value: str):
        self.requested.append(value)
        return self.model if self.model and self.model.value == value else None


def test_validate_image_data_url_returns_safe_metadata() -> None:
    from src.infra.tool import image_analysis_tool

    mime_type, decoded_size, digest = image_analysis_tool._validate_image_data_url(
        "data:image/png;base64,iVBORw0KGgo="
    )

    assert mime_type == "image/png"
    assert decoded_size == 8
    assert digest == "4c4b6a3be131"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_ref",
    [
        "data:text/plain;base64,aGVsbG8=",
        "data:image/png;base64,not-valid***",
        "data:image/png;base64,",
        "DATA:image/png;base64,not-valid***",
    ],
)
async def test_image_analyze_rejects_invalid_data_url_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
    image_ref: str,
) -> None:
    from src.infra.tool import image_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    calls = 0

    class _FailIfInvoked:
        async def ainvoke(self, _messages, config=None):
            nonlocal calls
            calls += 1
            raise AssertionError("invalid input reached model")

    async def fake_get_model(**_kwargs):
        return _FailIfInvoked()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=[image_ref],
            prompt="Describe",
            runtime=_Runtime(),
        )
    )

    assert result == {"error": "Invalid image data URL"}
    assert calls == 0


@pytest.mark.asyncio
async def test_image_analyze_emits_decodable_provider_payload_and_safe_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.tool import image_analysis_tool

    data_url = "data:image/png;base64,iVBORw0KGgo="
    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    captured: dict[str, object] = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = messages
            return SimpleNamespace(content="valid image")

    async def fake_get_model(**_kwargs):
        return _FakeLLM()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    with caplog.at_level(logging.DEBUG, logger=image_analysis_tool.__name__):
        result = json.loads(
            await image_analysis_tool.image_analyze.coroutine(
                image_urls=[data_url],
                prompt="Describe",
                runtime=_Runtime(),
            )
        )

    assert result["success"] is True
    request_payload = ChatOpenAI(api_key="test")._get_request_payload(captured["messages"])
    emitted_data_url = request_payload["messages"][0]["content"][1]["image_url"]["url"]
    header, encoded = emitted_data_url.split(",", 1)
    assert header == "data:image/png;base64"
    assert base64.b64decode(encoded, validate=True) == b"\x89PNG\r\n\x1a\n"
    assert data_url not in caplog.text
    assert "4c4b6a3be131" in caplog.text


@pytest.mark.asyncio
async def test_image_analyze_model_error_omits_request_content(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.tool import image_analysis_tool

    data_url = "data:image/png;base64,iVBORw0KGgo="
    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )

    class _FailingLLM:
        async def ainvoke(self, _messages, config=None):
            raise RuntimeError(f"gateway rejected payload={data_url}")

    async def fake_get_model(**_kwargs):
        return _FailingLLM()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    with caplog.at_level(logging.WARNING):
        result = json.loads(
            await image_analysis_tool.image_analyze.coroutine(
                image_urls=[data_url],
                prompt="Describe",
                runtime=_Runtime(),
            )
        )

    assert result == {"error": "Image analysis failed"}
    assert data_url not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_image_analyze_uses_configured_vlm_model_and_prompt(monkeypatch):
    from src.infra.tool import image_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        provider="openai",
        label="Vision",
        api_key="sk-test",
        api_base="https://api.example.com/v1",
        profile=ModelProfile(supports_vision=True),
    )
    storage = _FakeStorage(model)
    captured: dict[str, object] = {}

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = messages
            captured["config"] = config
            return SimpleNamespace(content="The image shows a lamb.")

    async def fake_get_model(**kwargs):
        captured["model_kwargs"] = kwargs
        return _FakeLLM()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr("src.infra.agent.model_storage.get_model_storage", lambda: storage)
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=["/api/upload/file/uploads/lamb.png"],
            prompt="Describe the animal.",
            runtime=_Runtime(),
        )
    )

    assert result == {
        "success": True,
        "analysis": "The image shows a lamb.",
        "model_id": "vision-id",
    }
    assert captured["model_kwargs"]["model_config"] == model
    assert captured["config"] == {
        "metadata": {"lc_source": "image_analysis_tool", "internal_tool_call": True},
        "tags": ["internal_tool_call", "image_analysis_tool"],
    }
    assert len(captured["messages"]) == 1
    assert isinstance(captured["messages"][0], HumanMessage)
    assert captured["messages"][0].content == [
        {"type": "text", "text": "Describe the animal."},
        {"type": "image_url", "image_url": {"url": "/api/upload/file/uploads/lamb.png"}},
    ]


@pytest.mark.asyncio
async def test_image_analyze_retries_failed_model_calls(monkeypatch):
    from src.infra.tool import image_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    attempts = 0

    class _FakeLLM:
        async def ainvoke(self, _messages, config=None):
            nonlocal attempts
            assert config == image_analysis_tool.IMAGE_ANALYSIS_INTERNAL_RUN_CONFIG
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporary")
            return SimpleNamespace(content="ok")

    async def fake_get_model(**_kwargs):
        return _FakeLLM()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=["https://cdn.example.com/a.png"],
            prompt="What is this?",
            runtime=_Runtime(),
        )
    )

    assert result["success"] is True
    assert result["analysis"] == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_image_analyze_supports_backend_file_paths(monkeypatch):
    from src.infra.tool import image_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/gpt-4o-mini",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    captured: dict[str, object] = {}

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            return [
                SimpleNamespace(
                    path="/workspace/chart.png",
                    content=b"\x89PNG\r\n\x1a\npng-bytes",
                    error=None,
                )
            ]

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = messages
            return SimpleNamespace(content="It is a chart.")

    async def fake_get_model(**_kwargs):
        return _FakeLLM()

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=["/workspace/chart.png"],
            prompt="Analyze this chart.",
            runtime=_Runtime(backend=_FakeBackend()),
        )
    )

    assert result["success"] is True
    message = captured["messages"][0]
    assert message.content[0] == {"type": "text", "text": "Analyze this chart."}
    image_url = message.content[1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_image_analyze_compresses_oversized_backend_file_before_data_url(monkeypatch):
    from src.infra.tool import image_analysis_tool

    original = b"x" * (5 * 1024 * 1024 + 1)
    compressed = b"compressed-jpeg"
    captured: dict[str, object] = {}

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(path=paths[0], content=original, error=None)]

    def fake_compress(content: bytes, mime_type: str):
        captured["compress_input"] = (content, mime_type)
        return compressed, "image/jpeg"

    monkeypatch.setattr(
        image_analysis_tool, "get_image_download_max_bytes", lambda: 10 * 1024 * 1024
    )
    monkeypatch.setattr(
        image_analysis_tool,
        "compress_image_bytes_if_needed",
        fake_compress,
        raising=False,
    )

    attachments = await image_analysis_tool._inline_backend_image_paths(
        [{"type": "image", "url": "/workspace/chart.png"}],
        _Runtime(backend=_FakeBackend()),
    )

    assert captured["compress_input"] == (original, "image/png")
    assert attachments[0]["mime_type"] == "image/jpeg"
    assert attachments[0]["data_url"] == "data:image/jpeg;base64,Y29tcHJlc3NlZC1qcGVn"


@pytest.mark.asyncio
async def test_image_analyze_rejects_non_vision_model(monkeypatch):
    from src.infra.tool import image_analysis_tool

    model = ModelConfig(
        id="text-id",
        value="openai/gpt-4o-mini",
        label="Text",
        profile=ModelProfile(supports_vision=False),
    )

    async def fail_get_model(**_kwargs):
        raise AssertionError("non-vision models should not be invoked")

    monkeypatch.setattr(image_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "text-id")
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    monkeypatch.setattr(image_analysis_tool.LLMClient, "get_model", fail_get_model)

    result = json.loads(
        await image_analysis_tool.image_analyze.coroutine(
            image_urls=["https://cdn.example.com/a.png"],
            prompt="What is this?",
            runtime=_Runtime(),
        )
    )

    assert result == {"error": "Configured IMAGE_ANALYSIS_MODEL_ID does not support vision"}


def test_get_image_analysis_tool_returns_expected_tool():
    from src.infra.tool.image_analysis_tool import get_image_analysis_tool

    tool = get_image_analysis_tool()

    assert tool.name == "image_analyze"


def test_internal_registry_includes_image_analysis_when_enabled(monkeypatch):
    from src.infra.tool import internal_registry

    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_ANALYSIS", True, raising=False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_GENERATION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_SCHEDULED_TASK", False)
    monkeypatch.setattr(internal_registry, "get_env_var_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_persona_preset_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_team_tools", lambda: [])

    names = {tool.name for tool in internal_registry.build_internal_tools()}

    assert "image_analyze" in names

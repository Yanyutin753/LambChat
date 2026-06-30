import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

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

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class _Runtime:
    def __init__(self, user_id: str | None, base_url: str = "https://app.example.com") -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context, "base_url": base_url}}


def _load_module_from_path(module_name: str, relative_path: str):
    path = Path(__file__).parents[3] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stub_context_tool_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    def tool(name: str):
        return SimpleNamespace(name=name)

    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.human_tool",
        SimpleNamespace(get_human_tool=lambda session_id=None: tool("ask_human")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.reveal_file_tool",
        SimpleNamespace(get_reveal_file_tool=lambda: tool("reveal_file")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.reveal_project_tool",
        SimpleNamespace(get_reveal_project_tool=lambda: tool("reveal_project")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.transfer_file_tool",
        SimpleNamespace(
            get_transfer_file_tool=lambda: tool("transfer_file"),
            get_transfer_path_tool=lambda: tool("transfer_path"),
        ),
    )


def test_get_audio_transcribe_tool_returns_expected_tool() -> None:
    from src.infra.tool.audio_transcribe_tool import get_audio_transcribe_tool

    tool = get_audio_transcribe_tool()

    assert tool.name == "audio_transcribe"


@pytest.mark.asyncio
async def test_audio_transcribe_transcribes_audio_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import audio_transcribe_tool

    captured: dict[str, object] = {}

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="hello world", language="en", duration=1.25)

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    class _FakeResponse:
        content = b"fake-audio"

        def raise_for_status(self) -> None:
            return None

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, request_url: str):
            captured["download_url"] = request_url
            return _FakeResponse()

    monkeypatch.setattr(audio_transcribe_tool, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(audio_transcribe_tool.settings, "AUDIO_TRANSCRIPTION_API_KEY", "sk-test")
    monkeypatch.setattr(
        audio_transcribe_tool.settings,
        "AUDIO_TRANSCRIPTION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(
        audio_transcribe_tool.settings,
        "AUDIO_TRANSCRIPTION_MODEL",
        "gpt-4o-mini-transcribe",
    )

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="/api/upload/file/audio/demo.wav",
            model="FunAudioLLM/SenseVoiceSmall",
            language="en",
            prompt="clean punctuation",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["text"] == "hello world"
    assert result["filename"] == "demo.wav"
    assert result["model"] == "FunAudioLLM/SenseVoiceSmall"
    assert result["url"] == "https://app.example.com/api/upload/file/audio/demo.wav"
    assert captured["download_url"] == "https://app.example.com/api/upload/file/audio/demo.wav"
    assert captured["model"] == "FunAudioLLM/SenseVoiceSmall"
    assert captured["language"] == "en"
    assert captured["prompt"] == "clean punctuation"
    assert captured["client_kwargs"] == {
        "api_key": "sk-test",
        "base_url": "https://api.example.com/v1",
    }


@pytest.mark.asyncio
async def test_audio_transcribe_returns_error_when_download_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import audio_transcribe_tool

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, request_url: str):
            raise RuntimeError(f"failed to fetch {request_url}")

    monkeypatch.setattr(
        audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(audio_transcribe_tool.settings, "AUDIO_TRANSCRIPTION_API_KEY", "sk-test")

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/demo.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert "Audio transcription failed:" in result["error"]


@pytest.mark.asyncio
async def test_search_agent_context_includes_audio_transcribe_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    search_context = _load_module_from_path(
        "search_context_with_audio_tool_under_test",
        "src/agents/search_agent/context.py",
    )

    monkeypatch.setattr(search_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SKILLS", False)

    ctx = search_context.SearchAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "audio_transcribe" in names


@pytest.mark.asyncio
async def test_fast_agent_context_includes_audio_transcribe_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    fast_context = _load_module_from_path(
        "fast_context_with_audio_tool_under_test",
        "src/agents/fast_agent/context.py",
    )

    monkeypatch.setattr(fast_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SKILLS", False)

    ctx = fast_context.FastAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "audio_transcribe" in names

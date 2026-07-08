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


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def write(self, chunk: bytes) -> int:
        if not getattr(
            sys.modules["src.infra.tool.audio_transcribe_tool"], "_inside_fake_blocking_io", False
        ):
            raise AssertionError("audio spool writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(
            sys.modules["src.infra.tool.audio_transcribe_tool"], "_inside_fake_blocking_io", False
        ):
            raise AssertionError("audio spool seek must run in blocking IO executor")
        self.position = position
        return position


def _set_audio_plugin_settings(
    monkeypatch: pytest.MonkeyPatch,
    module,
    *,
    api_key: str = "sk-test",
    base_url: str = "https://api.example.com/v1",
    model: str = "gpt-4o-mini-transcribe",
    max_download_bytes: int = 50 * 1024 * 1024,
) -> None:
    class _Resolver:
        async def get_secret(self, key: str) -> str:
            assert key == "API_KEY"
            return api_key

        async def get_str(self, key: str, default: str = "") -> str:
            if key == "BASE_URL":
                return base_url
            if key == "MODEL":
                return model
            return default

        async def get_int(self, key: str, default: int = 0) -> int:
            assert key == "MAX_DOWNLOAD_BYTES"
            return max_download_bytes or default

    monkeypatch.setattr(module, "_settings_resolver", lambda: _Resolver())


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
async def test_audio_transcribe_offloads_config_error_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import audio_transcribe_tool

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(audio_transcribe_tool, "run_blocking_io", fake_run_blocking_io)
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool, api_key="")

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/demo.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"error": "AUDIO_TRANSCRIPTION_API_KEY is not configured"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_audio_transcribe_transcribes_audio_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import audio_transcribe_tool

    captured: dict[str, object] = {}
    close_calls = 0

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="hello world", language="en", duration=1.25)

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"] = kwargs
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

        async def aclose(self) -> None:
            nonlocal close_calls
            close_calls += 1

    class _FakeResponse:
        @property
        def content(self):
            raise AssertionError("audio downloads should stream into a file")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"fake-"
            yield b"audio"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            captured["download_url"] = request_url
            return _FakeResponse()

    monkeypatch.setattr(audio_transcribe_tool, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool)

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
    assert close_calls == 1


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
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool)

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/demo.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert "Audio transcription failed:" in result["error"]


@pytest.mark.asyncio
async def test_audio_transcribe_rejects_audio_downloads_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import audio_transcribe_tool

    transcribe_called = False

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            nonlocal transcribe_called
            transcribe_called = True
            return SimpleNamespace(text="should not happen")

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    class _FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"a" * 6
            yield b"b" * 6

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    monkeypatch.setattr(audio_transcribe_tool, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool, max_download_bytes=10)

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/huge.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["error"] == "Audio download exceeds 10 bytes"
    assert transcribe_called is False


@pytest.mark.asyncio
async def test_audio_transcribe_rejects_known_oversize_download_before_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import audio_transcribe_tool

    transcribe_called = False

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            nonlocal transcribe_called
            transcribe_called = True
            return SimpleNamespace(text="should not happen")

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    class _FakeResponse:
        headers = {"content-length": "11"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            raise AssertionError("known oversized audio should not be streamed")

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    monkeypatch.setattr(audio_transcribe_tool, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool, max_download_bytes=10)

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/huge.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["error"] == "Audio download exceeds 10 bytes"
    assert transcribe_called is False


@pytest.mark.asyncio
async def test_audio_transcribe_offloads_spooled_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import audio_transcribe_tool

    calls: list[str] = []

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            file_tuple = kwargs["file"]
            assert file_tuple[1].data == bytearray(b"fake-audio")
            return SimpleNamespace(text="hello")

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    class _FakeResponse:
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"fake-"
            yield b"audio"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            return _FakeResponse()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        monkeypatch.setattr(audio_transcribe_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(
                audio_transcribe_tool,
                "_inside_fake_blocking_io",
                False,
                raising=False,
            )

    monkeypatch.setattr(audio_transcribe_tool, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        audio_transcribe_tool.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeHttpClient(),
    )
    monkeypatch.setattr(audio_transcribe_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(
        audio_transcribe_tool, "run_blocking_io", fake_run_blocking_io, raising=False
    )
    monkeypatch.setattr(audio_transcribe_tool, "_inside_fake_blocking_io", False, raising=False)
    _set_audio_plugin_settings(monkeypatch, audio_transcribe_tool)

    result = json.loads(
        await audio_transcribe_tool.audio_transcribe.coroutine(
            url="https://files.example.com/demo.wav",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert calls == ["write", "write", "seek", "dumps"]


@pytest.mark.asyncio
async def test_search_agent_context_includes_audio_transcribe_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    from src.infra.tool import internal_registry

    async def no_internal_tool_policies():
        return {}

    monkeypatch.setattr(
        internal_registry,
        "get_internal_tool_policies",
        no_internal_tool_policies,
    )
    search_context = _load_module_from_path(
        "search_context_with_audio_tool_under_test",
        "src/agents/search_agent/context.py",
    )
    from src.kernel.extensions import PluginRuntime, build_audio_transcription_plugin_manifest

    monkeypatch.setattr(search_context.settings, "ENABLE_AUDIO_TRANSCRIPTION", True)
    monkeypatch.setattr(search_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SKILLS", False)
    runtime = PluginRuntime([build_audio_transcription_plugin_manifest()])
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    ctx = search_context.SearchAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "audio_transcribe" in names


@pytest.mark.asyncio
async def test_fast_agent_context_includes_audio_transcribe_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    from src.infra.tool import internal_registry

    async def no_internal_tool_policies():
        return {}

    monkeypatch.setattr(
        internal_registry,
        "get_internal_tool_policies",
        no_internal_tool_policies,
    )
    fast_context = _load_module_from_path(
        "fast_context_with_audio_tool_under_test",
        "src/agents/fast_agent/context.py",
    )
    from src.kernel.extensions import PluginRuntime, build_audio_transcription_plugin_manifest

    monkeypatch.setattr(fast_context.settings, "ENABLE_AUDIO_TRANSCRIPTION", True)
    monkeypatch.setattr(fast_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SKILLS", False)
    runtime = PluginRuntime([build_audio_transcription_plugin_manifest()])
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    ctx = fast_context.FastAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "audio_transcribe" in names

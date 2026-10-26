"""video_analyze 内置工具测试：MIME 魔数、字节上限硬限、video_url 消息形态。"""

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.schemas.model import ModelConfig, ModelProfile


class _Runtime:
    def __init__(self, backend: object | None = None):
        configurable: dict[str, object] = {
            "context": SimpleNamespace(user_id="user-1"),
            "base_url": "https://app.example.com",
        }
        if backend is not None:
            configurable["backend"] = backend
        self.config = {"configurable": configurable}


class _FakeStorage:
    def __init__(self, model: ModelConfig | None):
        self.model = model

    async def get(self, model_id: str):
        return self.model if self.model and self.model.id == model_id else None

    async def get_by_value(self, value: str):
        return self.model if self.model and self.model.value == value else None


@pytest.fixture
def video_model(monkeypatch):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=True)
    )
    model = ModelConfig(
        id="vision-id",
        value="google/gemini-test",
        label="Video",
        profile=ModelProfile(supports_vision=True),
    )
    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage", lambda: _FakeStorage(model)
    )
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="A cat.")))
    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", AsyncMock(return_value=llm))
    return model, llm


async def test_uploaded_video_is_authorized_and_reaches_google_wire(monkeypatch, video_model):
    from langchain_google_genai.chat_models import _convert_to_parts

    from src.infra.tool import video_analysis_tool as module
    from src.infra.upload.file_record import FileRecordStorage

    lookup = AsyncMock(return_value={"uploaded_by": "user-1"})
    monkeypatch.setattr(FileRecordStorage, "find_by_key", lookup)
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=False))

    async def stream(key):
        assert key == "videos/clip.mp4"
        yield _mp4_bytes()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        AsyncMock(return_value=SimpleNamespace(download_stream=stream)),
    )
    result = json.loads(
        await module.video_analyze.coroutine(
            video_urls=["https://app.example.com/api/upload/file/videos/clip.mp4"],
            runtime=_Runtime(),
        )
    )
    assert result["success"] is True
    lookup.assert_awaited_once_with("videos/clip.mp4", "user-1")
    message = video_model[1].ainvoke.call_args.args[0][0]
    parts = _convert_to_parts(message.content)
    assert parts[1].inline_data.data == _mp4_bytes()
    assert parts[1].inline_data.mime_type == "video/mp4"


async def test_anthropic_image_model_is_rejected_before_video_download(monkeypatch, video_model):
    from src.infra.tool import video_analysis_tool as module

    video_model[0].provider = "zai"
    result = json.loads(
        await module.video_analyze.coroutine(video_urls=["/workspace/a.mp4"], runtime=_Runtime())
    )
    assert result["error"] == "video_model_protocol_unsupported"
    video_model[1].ainvoke.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\reader\Videos\12月5日 (1).mp4",
        "d:/Videos/clip.mp4",
        r"\\server\share\clip.mp4",
        r"\\?\C:\Videos\clip.mp4",
        "/Users/reader/Movies/视频 (1).mp4",
        "/home/reader/Videos/视频 (1).mp4",
        "/workspace/session/clip.mp4",
        "clip.mp4",
    ],
)
async def test_native_video_path_reaches_backend_and_model(video_model, path):
    from src.infra.tool import video_analysis_tool as module

    class Backend:
        async def adownload_files(self, paths):
            assert paths == [path]
            return [SimpleNamespace(path=path, content=_mp4_bytes(), error=None)]

    result = json.loads(
        await module.video_analyze.coroutine(video_urls=[path], runtime=_Runtime(Backend()))
    )
    assert result["success"] is True
    assert result["analysis"] == "A cat."
    message = video_model[1].ainvoke.call_args.args[0][0]
    assert base64.b64decode(message.content[1]["base64"]) == _mp4_bytes()


async def test_backend_video_download_uses_configured_video_deadline(monkeypatch, video_model):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(module, "_DOWNLOAD_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_TIMEOUT_SECONDS", 1)

    class Backend:
        async def adownload_files(self, paths):
            await asyncio.sleep(0.02)
            return [SimpleNamespace(path=paths[0], content=_mp4_bytes(), error=None)]

    result = json.loads(
        await module.video_analyze.coroutine(
            video_urls=[r"C:\Videos\clip.mp4"], runtime=_Runtime(Backend())
        )
    )
    assert result["success"] is True


async def test_native_video_preview_reuses_analysis_bytes_and_registers_owner(
    monkeypatch, video_model
):
    from src.infra.logging.context import TraceContext
    from src.infra.storage.s3.service import S3StorageService
    from src.infra.storage.s3.types import S3Config, S3Provider
    from src.infra.tool import video_analysis_tool as module

    content = _mp4_bytes()
    original = content + b"large" * 100
    backend = SimpleNamespace(
        adownload_files=AsyncMock(return_value=[SimpleNamespace(content=original, error=None)])
    )
    runtime = _Runtime(backend)
    runtime.config["configurable"]["session_id"] = "session-1"
    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(user_id="user-1", session_id="session-1"),
    )
    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_INLINE_MAX_BYTES", len(content))
    monkeypatch.setattr(module, "compress_video", AsyncMock(return_value=content))
    storage = S3StorageService(S3Config(provider=S3Provider.LOCAL))
    uploaded = None

    async def upload(file, key, content_type, metadata):
        nonlocal uploaded
        assert file.read() == content
        assert key.startswith("revealed_files/") and content_type == "video/mp4"
        uploaded = SimpleNamespace(key=key, content_type=content_type, size=len(content))
        return uploaded

    storage._backend = SimpleNamespace(upload=upload, exists=AsyncMock(return_value=False))
    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage", AsyncMock(return_value=storage)
    )
    register = AsyncMock()
    monkeypatch.setattr(
        "src.infra.upload.file_record.get_file_record_storage",
        lambda: SimpleNamespace(register_generated=register),
    )
    path = r"C:\Users\yangyang\Videos\12月5日(1).mp4"
    result = json.loads(await module.video_analyze.coroutine(video_urls=[path], runtime=runtime))
    assert result["success"] is True
    preview_url = result["videos"][0]["preview_url"]
    assert preview_url == f"https://app.example.com/api/upload/file/{uploaded.key}"
    register.assert_awaited_once_with(uploaded, "user-1", "session-1")
    backend.adownload_files.assert_awaited_once_with([path])


@pytest.mark.parametrize("failure", [RuntimeError("provider failed"), TimeoutError(), ""])
async def test_unsuccessful_analysis_never_persists_a_preview(monkeypatch, video_model, failure):
    from src.infra.tool import video_analysis_tool as module

    runtime = _Runtime(
        SimpleNamespace(
            adownload_files=AsyncMock(
                return_value=[SimpleNamespace(content=_mp4_bytes(), error=None)]
            )
        )
    )
    upload = AsyncMock(return_value="https://app.example.com/api/upload/file/preview.mp4")
    monkeypatch.setattr(module, "_upload_video_preview", upload)
    call = (
        AsyncMock(side_effect=failure)
        if isinstance(failure, Exception)
        else AsyncMock(return_value=SimpleNamespace(content=failure))
    )
    monkeypatch.setattr(module, "_call_with_retries", call)
    result = json.loads(
        await module.video_analyze.coroutine(video_urls=[r"C:\Videos\clip.mp4"], runtime=runtime)
    )
    assert result["success"] is False
    upload.assert_not_awaited()


async def test_preview_upload_failure_does_not_fail_analysis(monkeypatch, video_model):
    from src.infra.logging.context import TraceContext
    from src.infra.tool import video_analysis_tool as module

    runtime = _Runtime(
        SimpleNamespace(
            adownload_files=AsyncMock(
                return_value=[SimpleNamespace(content=_mp4_bytes(), error=None)]
            )
        )
    )
    runtime.config["configurable"]["session_id"] = "session-1"
    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(user_id="user-1", session_id="session-1"),
    )
    get_storage = AsyncMock(side_effect=OSError("storage unavailable"))
    monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", get_storage)
    result = json.loads(
        await module.video_analyze.coroutine(video_urls=[r"C:\Videos\clip.mp4"], runtime=runtime)
    )
    assert result["success"] is True
    assert "preview_url" not in result["videos"][0]
    get_storage.assert_awaited_once()


@pytest.mark.parametrize(
    "owner,session", [("other", "session-1"), ("user-1", "other"), (None, None)]
)
async def test_preview_never_uses_another_request_owner(monkeypatch, video_model, owner, session):
    from src.infra.logging.context import TraceContext
    from src.infra.tool import video_analysis_tool as module

    runtime = _Runtime(
        SimpleNamespace(
            adownload_files=AsyncMock(
                return_value=[SimpleNamespace(content=_mp4_bytes(), error=None)]
            )
        )
    )
    runtime.config["configurable"]["session_id"] = "session-1"
    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(user_id=owner, session_id=session),
    )
    get_storage = AsyncMock()
    monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", get_storage)
    result = json.loads(
        await module.video_analyze.coroutine(video_urls=[r"C:\Videos\clip.mp4"], runtime=runtime)
    )
    assert result["success"] is True
    assert "preview_url" not in result["videos"][0]
    get_storage.assert_not_awaited()


async def test_stalled_preview_is_bounded_without_losing_analysis(monkeypatch, video_model):
    from src.infra.logging.context import TraceContext
    from src.infra.tool import video_analysis_tool as module

    runtime = _Runtime(
        SimpleNamespace(
            adownload_files=AsyncMock(
                return_value=[SimpleNamespace(content=_mp4_bytes(), error=None)]
            )
        )
    )
    runtime.config["configurable"]["session_id"] = "session-1"
    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(user_id="user-1", session_id="session-1"),
    )
    monkeypatch.setattr(module, "_DOWNLOAD_TIMEOUT_SECONDS", 0.01)
    cancelled = asyncio.Event()

    async def hang():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", hang)
    async with asyncio.timeout(1):
        result = json.loads(
            await module.video_analyze.coroutine(
                video_urls=[r"C:\Videos\clip.mp4"], runtime=runtime
            )
        )
    assert result["success"] is True
    assert cancelled.is_set()


@pytest.mark.parametrize("uploaded", [False, True])
async def test_stalled_video_download_is_cancelled(monkeypatch, video_model, uploaded):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(module, "_DOWNLOAD_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_TIMEOUT_SECONDS", 0.01)
    cancelled = asyncio.Event()

    async def hang(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(module, "_download_uploaded_video", hang)
    ref = "/api/upload/file/videos/clip.mp4" if uploaded else r"C:\Videos\clip.mp4"
    async with asyncio.timeout(1):
        result = json.loads(
            await module.video_analyze.coroutine(
                video_urls=[ref], runtime=_Runtime(SimpleNamespace(adownload_files=hang))
            )
        )
    assert result == {
        "success": False,
        "errors": [{"url": ref, "error": "video_download_timeout"}],
    }
    assert cancelled.is_set()
    video_model[1].ainvoke.assert_not_called()


async def test_video_permanent_model_error_is_not_retried(monkeypatch):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_RETRY_DELAY", 0)
    llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=ValueError("bad video format")))
    with pytest.raises(ValueError):
        await module._call_with_retries(llm, [])
    assert llm.ainvoke.await_count == 1


async def test_video_model_total_deadline(monkeypatch):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_TIMEOUT_SECONDS", 0.01, raising=False)

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    async with asyncio.timeout(0.2):
        with pytest.raises(TimeoutError):
            await module._call_with_retries(SimpleNamespace(ainvoke=hang), [])


@pytest.mark.parametrize(
    "reference",
    [
        "https://foreign.example/api/upload/file/videos/clip.mp4",
        "https://app.example.com/api/upload/file/videos/%2e%2e/clip.mp4",
        "https://app.example.com/api/upload/file/videos%5cclip.mp4",
        "https://v.douyin.com/page/",
    ],
)
async def test_untrusted_video_url_never_reads_storage(monkeypatch, video_model, reference):
    from src.infra.tool import video_analysis_tool as module

    storage = AsyncMock(side_effect=AssertionError("untrusted URL reached storage"))
    monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", storage)
    result = json.loads(
        await module.video_analyze.coroutine(video_urls=[reference], runtime=_Runtime())
    )
    assert result["success"] is False
    storage.assert_not_called()
    video_model[1].ainvoke.assert_not_called()


@pytest.mark.parametrize(
    "owned,private,oversized",
    [(False, False, False), (True, True, False), (True, False, True), (True, False, False)],
)
async def test_revealed_video_access_and_streaming_size_limit(
    monkeypatch, video_model, owned, private, oversized
):
    from src.infra.tool import video_analysis_tool as module
    from src.infra.upload.file_record import FileRecordStorage
    from src.kernel.errors import AppError, ErrorCode

    monkeypatch.setattr(FileRecordStorage, "find_by_key", AsyncMock(return_value=None))
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=private))
    private_access = AsyncMock(side_effect=AppError(ErrorCode.FILE_NOT_FOUND))
    monkeypatch.setattr(FileRecordStorage, "require_private_access", private_access)
    lookup = AsyncMock(return_value={"file_key": "revealed_files/clip.mp4"} if owned else None)
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: SimpleNamespace(find_by_file_key=lookup),
    )
    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_MAX_BYTES", 40)
    chunks = []

    async def stream(key):
        assert key == "revealed_files/clip.mp4"
        for chunk in [_mp4_bytes(), b"x" * 30, b"must not read"] if oversized else [_mp4_bytes()]:
            chunks.append(chunk)
            yield chunk

    storage = AsyncMock(return_value=SimpleNamespace(download_stream=stream))
    monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", storage)
    result = json.loads(
        await module.video_analyze.coroutine(
            video_urls=["/api/upload/file/revealed_files/clip.mp4"], runtime=_Runtime()
        )
    )
    assert result["success"] is (owned and not private and not oversized)
    if not owned or private:
        storage.assert_not_called()
    elif oversized:
        assert result["errors"][0]["error"] == "video_too_large"
        assert len(chunks) == 2
    else:
        lookup.assert_awaited_once_with("user-1", "revealed_files/clip.mp4")
    if private:
        private_access.assert_awaited_once()


async def test_video_transient_retry_preserves_messages(monkeypatch):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(module.settings, "VIDEO_ANALYSIS_RETRY_DELAY", 0)
    llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=[TimeoutError(), "ok"]))
    assert await module._call_with_retries(llm, ["video"]) == "ok"
    assert llm.ainvoke.await_count == 2
    assert llm.ainvoke.call_args.args == (["video"],)


def _mp4_bytes(payload: bytes = b"video-payload") -> bytes:
    # 12 字节 ftyp box 头（brand isom）+ 任意负载
    return b"\x00\x00\x00\x20ftypisom" + payload


# ---------------------------------------------------------------------------
# MIME 魔数识别
# ---------------------------------------------------------------------------


def test_guess_video_mime_type_by_magic_bytes() -> None:
    from src.infra.tool.video_analysis_tool import _guess_video_mime_type

    assert _guess_video_mime_type("clip.bin", _mp4_bytes()) == "video/mp4"
    assert _guess_video_mime_type("clip.bin", b"\x00\x00\x00\x14ftypqt  " + b"x") == (
        "video/quicktime"
    )
    assert _guess_video_mime_type("clip.bin", b"\x1a\x45\xdf\xa3webm-data") == "video/webm"
    # 扩展名兜底
    assert _guess_video_mime_type("movie.mp4", b"whatever") == "video/mp4"
    # 非视频内容（含图片魔数）不得误判
    assert _guess_video_mime_type("chart.png", b"\x89PNG\r\n\x1a\n") is None
    assert _guess_video_mime_type("note.txt", b"hello") is None


def test_video_analysis_max_bytes_defaults_and_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import video_analysis_tool

    # 0/负值视为未配置 → 回落默认 200MB（pydantic v2 字段删不得：类上无兜底属性）
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_BYTES", 0)
    assert video_analysis_tool.get_video_analysis_max_bytes() == (200 * 1024 * 1024)

    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_BYTES", 1024 * 1024)
    assert video_analysis_tool.get_video_analysis_max_bytes() == 1024 * 1024


# ---------------------------------------------------------------------------
# build_human_message：video_url 块形态
# ---------------------------------------------------------------------------


def test_build_human_message_inlines_video_data_url_as_video_url_part() -> None:
    from src.agents.core.node_utils import build_human_message

    message = build_human_message(
        "描述这段视频",
        [
            {
                "type": "video",
                "mime_type": "video/mp4",
                "url": "/workspace/clip.mp4",
                "data_url": "data:video/mp4;base64,AAAA",
            }
        ],
        supports_vision=True,
    )

    parts = message.content
    assert parts[0]["type"] == "text"
    video_part = parts[1]
    assert video_part == {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAA"}}
    # 文本摘要保留原始路径：模型读不出 video 块里的 URL
    assert "/workspace/clip.mp4" in parts[0]["text"]


def test_build_human_message_orders_image_parts_before_video_parts() -> None:
    from src.agents.core.node_utils import build_human_message

    message = build_human_message(
        "对比",
        [
            {"type": "video", "url": "/w/a.mp4", "data_url": "data:video/mp4;base64,AAA"},
            {"type": "image", "url": "/w/a.png", "data_url": "data:image/png;base64,AAA"},
        ],
        supports_vision=True,
    )

    assert [part["type"] for part in message.content[1:]] == ["image_url", "video_url"]


# ---------------------------------------------------------------------------
# 工具主流程：成功 / 超限拒绝 / 注册暴露
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_video_analyze_success_builds_video_url_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import video_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/glm-4.5v",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    captured: dict[str, object] = {}

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(path=paths[0], content=_mp4_bytes(), error=None)]

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = messages
            return SimpleNamespace(content="A cat is jumping.")

    # 视频专用模型优先于图片分析的模型
    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "image-model")
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    from src.infra.llm.client import LLMClient

    async def fake_get_model(**_kwargs):
        return _FakeLLM()

    monkeypatch.setattr(LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await video_analysis_tool.video_analyze.coroutine(
            video_urls=["/workspace/clip.mp4"],
            prompt="视频里发生了什么？",
            runtime=_Runtime(backend=_FakeBackend()),
        )
    )

    assert result["success"] is True
    assert result["analysis"] == "A cat is jumping."
    assert result["videos"][0]["mime_type"] == "video/mp4"
    message = captured["messages"][0]
    video_url = message.content[1]["video_url"]["url"]
    expected_prefix = "data:video/mp4;base64,"
    assert video_url.startswith(expected_prefix)
    assert base64.b64decode(video_url[len(expected_prefix) :]) == _mp4_bytes()


@pytest.mark.asyncio
async def test_video_analyze_rejects_oversized_video_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import video_analysis_tool

    model = ModelConfig(
        id="vision-id",
        value="openai/glm-4.5v",
        label="Vision",
        profile=ModelProfile(supports_vision=True),
    )
    calls = 0

    class _FailIfInvoked:
        async def ainvoke(self, _messages, config=None):
            nonlocal calls
            calls += 1
            raise AssertionError("oversized video reached model")

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [
                SimpleNamespace(
                    path=paths[0], content=_mp4_bytes(b"x" * (2 * 1024 * 1024)), error=None
                )
            ]

    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_RETRY_DELAY", 0)
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_BYTES", 1024 * 1024)
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _FakeStorage(model),
    )
    from src.infra.llm.client import LLMClient

    async def fake_get_model(**_kwargs):
        return _FailIfInvoked()

    monkeypatch.setattr(LLMClient, "get_model", fake_get_model)

    result = json.loads(
        await video_analysis_tool.video_analyze.coroutine(
            video_urls=["/workspace/big.mp4"],
            prompt="过大的视频",
            runtime=_Runtime(backend=_FakeBackend()),
        )
    )

    assert result["success"] is False
    assert result["errors"][0]["error"] == "video_too_large"
    assert result["errors"][0]["max_bytes"] == 1024 * 1024
    assert calls == 0


@pytest.mark.asyncio
async def test_internal_registry_exposes_video_analyze_with_image_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry

    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_ANALYSIS", True)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_GENERATION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_SCHEDULED_TASK", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_SEARCH", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_FETCH", False)

    async def no_policies():
        return {}

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_policies)

    from src.kernel.schemas.user import TokenPayload

    monkeypatch.setattr(
        internal_registry,
        "resolve_tool_user",
        AsyncMock(return_value=TokenPayload(sub="user-1", username="user")),
    )
    tools = await internal_registry.get_internal_tools_for_user(
        user_id="user-1", user_roles=[], is_admin=False
    )
    names = {getattr(tool, "name", None) for tool in tools}
    assert "image_analyze" in names
    assert "video_analyze" in names


@pytest.mark.asyncio
async def test_video_analyze_falls_back_to_image_model_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配 VIDEO_ANALYSIS_MODEL_ID 时回落 IMAGE_ANALYSIS_MODEL_ID。"""
    from src.infra.tool import video_analysis_tool

    requested: list[str] = []

    class _FakeStorage:
        async def get(self, model_id: str):
            requested.append(model_id)
            if model_id != "image-model":
                return None
            return ModelConfig(
                id="image-model",
                value="openai/glm-4.5v",
                label="Vision",
                profile=ModelProfile(supports_vision=True),
            )

        async def get_by_value(self, value: str):
            requested.append(value)
            return None

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            return SimpleNamespace(content="fallback ok")

    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "image-model")
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MODEL_ID", "")
    monkeypatch.setattr("src.infra.agent.model_storage.get_model_storage", lambda: _FakeStorage())
    from src.infra.llm.client import LLMClient

    async def fake_get_model(**_kwargs):
        return _FakeLLM()

    monkeypatch.setattr(LLMClient, "get_model", fake_get_model)

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(path=paths[0], content=_mp4_bytes(), error=None)]

    result = json.loads(
        await video_analysis_tool.video_analyze.coroutine(
            video_urls=["/workspace/clip.mp4"],
            runtime=_Runtime(backend=_FakeBackend()),
        )
    )
    assert result["success"] is True
    assert result["model_id"] == "image-model"
    assert "image-model" in requested


@pytest.mark.asyncio
async def test_video_analyze_errors_when_neither_model_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import video_analysis_tool

    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "")
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MODEL_ID", "")

    result = json.loads(
        await video_analysis_tool.video_analyze.coroutine(
            video_urls=["/workspace/clip.mp4"],
            runtime=_Runtime(),
        )
    )
    assert "Neither VIDEO_ANALYSIS_MODEL_ID nor IMAGE_ANALYSIS_MODEL_ID" in result["error"]


async def test_uploaded_video_rechecks_file_read_before_storage(monkeypatch):
    from src.infra.tool import video_analysis_tool as module
    from src.infra.upload.file_record import FileRecordStorage
    from src.kernel.errors import AppError

    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=False)
    )
    lookup = AsyncMock(return_value={"uploaded_by": "user-1"})
    monkeypatch.setattr(FileRecordStorage, "is_private_key", lookup)
    with pytest.raises(AppError):
        await module._download_uploaded_video("/api/upload/file/videos/clip.mp4", _Runtime(), 100)
    lookup.assert_not_awaited()


@pytest.mark.parametrize("count", [1, 2])
async def test_large_video_is_compacted_before_native_model_request(
    monkeypatch, video_model, count
):
    from src.infra.tool import video_analysis_tool as module

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(**{**module.settings.model_dump(), "VIDEO_ANALYSIS_INLINE_MAX_BYTES": 64}),
    )
    original = _mp4_bytes() + b"x" * 100
    backend = SimpleNamespace(
        adownload_files=AsyncMock(return_value=[SimpleNamespace(content=original, error=None)])
    )
    compact = AsyncMock(return_value=_mp4_bytes())
    monkeypatch.setattr(module, "compress_video", compact, raising=False)
    result = json.loads(
        await module.video_analyze.coroutine(
            video_urls=["/workspace/a.mp4"] * count, runtime=_Runtime(backend)
        )
    )
    assert result["success"] is True
    assert compact.await_count == count
    assert compact.call_args.args[1] == 64 // count
    assert result["videos"][0]["compressed"] is True
    assert result["videos"][0]["size_bytes"] == len(original)
    assert result["videos"][0]["analysis_size_bytes"] == len(_mp4_bytes())
    sent = video_model[1].ainvoke.call_args.args[0][0].content
    assert base64.b64decode(sent[1]["base64"]) == _mp4_bytes()

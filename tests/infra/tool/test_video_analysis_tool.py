"""video_analyze 内置工具测试：MIME 魔数、字节上限硬限、video_url 消息形态。"""

import base64
import json
from types import SimpleNamespace

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

    # 0/负值视为未配置 → 回落默认 50MB（pydantic v2 字段删不得：类上无兜底属性）
    monkeypatch.setattr(video_analysis_tool.settings, "VIDEO_ANALYSIS_MAX_BYTES", 0)
    assert video_analysis_tool.get_video_analysis_max_bytes() == (50 * 1024 * 1024)

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

    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MODEL_ID", "vision-id")
    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
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
    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(video_analysis_tool.settings, "IMAGE_ANALYSIS_RETRY_DELAY", 0)
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

    tools = await internal_registry.get_internal_tools_for_user(
        user_id="user-1", user_roles=[], is_admin=False
    )
    names = {getattr(tool, "name", None) for tool in tools}
    assert "image_analyze" in names
    assert "video_analyze" in names

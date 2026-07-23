import asyncio
import base64
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace

import pytest

from src.infra.tool import image_generation_tool


@pytest.fixture(autouse=True)
def _reset_image_http_clients():
    """每个测试前重置复用的 httpx client，避免缓存污染并让 monkeypatch 生效。"""
    image_generation_tool._image_api_client = None
    image_generation_tool._download_client = None
    yield
    image_generation_tool._image_api_client = None
    image_generation_tool._download_client = None


class _Runtime:
    def __init__(
        self,
        user_id: str | None,
        base_url: str = "https://app.example.com",
        backend=None,
    ) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {
            "configurable": {"context": context, "base_url": base_url, "backend": backend}
        }


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0
        self.closed = False

    def write(self, chunk: bytes) -> int:
        from src.infra.tool import image_generation_tool

        if not getattr(image_generation_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("image download spool writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int, whence: int = 0) -> int:
        from src.infra.tool import image_generation_tool

        if not getattr(image_generation_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("image download spool seek must run in blocking IO executor")
        if whence == 2:
            self.position = len(self.data) + position
        else:
            self.position = position
        return self.position

    def tell(self) -> int:
        return self.position

    def read(self) -> bytes:
        return bytes(self.data)

    def close(self) -> None:
        self.closed = True


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


def test_get_image_generation_tool_returns_expected_tool() -> None:
    from src.infra.tool.image_generation_tool import get_image_generation_tool

    tool = get_image_generation_tool()

    assert tool.name == "image_generate"


@pytest.mark.asyncio
async def test_image_generate_calls_images_api_and_uploads_base64_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    image_bytes = b"fake-png"
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            captured["request_url"] = request_url
            captured["kwargs"] = kwargs
            return _FakeResponse({"data": [{"b64_json": b64_image, "revised_prompt": "a cat"}]})

    class _FakeStorage:
        is_local = False

        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("generated images should use upload_file")

        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            captured["upload"] = {
                "data": file.read(),
                "folder": folder,
                "filename": filename,
                "content_type": content_type,
            }
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url="https://oss.example.com/generated-images%2Fuser-1%2Fcat.png?Signature=secret",
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool,
        "utc_now",
        lambda: datetime(2026, 5, 23, 12, 34, 56, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_TIMEOUT", 123)

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            size="1024x1024",
            quality="high",
            output_format="png",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert set(result.keys()) == {"success", "images"}
    assert result["images"][0] == {
        "url": "https://app.example.com/api/upload/file/generated-images/user-1/generated-20260523_123456-1.png",
        "key": "generated-images/user-1/generated-20260523_123456-1.png",
        "content_type": "image/png",
        "revised_prompt": "a cat",
    }
    assert result["images"][0]["revised_prompt"] == "a cat"
    assert captured["request_url"] == "https://api.example.com/v1/images/generations"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["kwargs"]["json"] == {
        "model": "gpt-image-2",
        "prompt": "draw a cat",
        "background": "auto",
        "size": "1024x1024",
        "quality": "high",
        "n": 1,
        "output_format": "png",
    }
    assert captured["upload"]["data"] == image_bytes
    assert captured["upload"]["folder"] == "generated-images/user-1"
    assert captured["upload"]["filename"] == "generated-20260523_123456-1.png"
    assert captured["upload"]["content_type"] == "image/png"


def test_image_generate_schema_describes_supported_parameters() -> None:
    from src.infra.tool.image_generation_tool import get_image_generation_tool

    tool = get_image_generation_tool()
    fields = set(tool.args_schema.model_fields)

    supported_fields = {
        "prompt",
        "input_images",
        "background",
        "input_fidelity",
        "size",
        "quality",
        "output_format",
    }
    assert supported_fields.issubset(fields)
    assert "mask_url" not in fields
    for field_name in supported_fields:
        assert tool.args_schema.model_fields[field_name].description


def test_image_generate_description_mentions_reference_image_workflows() -> None:
    from src.infra.tool.image_generation_tool import get_image_generation_tool

    tool = get_image_generation_tool()
    description = tool.description

    for keyword in ("图生图", "参考图", "照着这张", "基于这张", "input_images"):
        assert keyword in description


def test_reference_image_generation_tool_requires_input_images() -> None:
    from src.infra.tool.image_generation_tool import get_reference_image_generation_tool

    tool = get_reference_image_generation_tool()
    fields = tool.args_schema.model_fields

    assert tool.name == "image_edit_with_references"
    assert fields["input_images"].is_required()
    assert "图生图" in tool.description
    assert "参考图" in tool.description
    assert "照着这张" in tool.description


def test_decode_base64_to_spooled_file_rejects_oversized_payload_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    monkeypatch.setattr(image_generation_tool, "_IMAGE_DOWNLOAD_MAX_BYTES", 4)

    def fail_b64decode(*args, **kwargs):
        raise AssertionError("oversized image payload should be rejected before decoding")

    monkeypatch.setattr(image_generation_tool.base64, "b64decode", fail_b64decode)

    oversized = base64.b64encode(b"image-data").decode("ascii")
    with pytest.raises(ValueError, match="Image download too large"):
        image_generation_tool._decode_base64_to_spooled_file(oversized)


@pytest.mark.asyncio
async def test_download_image_source_rejects_oversized_remote_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    monkeypatch.setattr(image_generation_tool, "_IMAGE_DOWNLOAD_MAX_BYTES", 5)

    class _FakeStreamResponse:
        headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"abc"
            yield b"def"

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, url: str):
            assert method == "GET"
            assert url == "https://example.com/image.png"
            return _FakeStreamResponse()

    monkeypatch.setattr(image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeClient())

    with pytest.raises(ValueError, match="Image download too large"):
        await image_generation_tool._download_image_source("https://example.com/image.png", None)


@pytest.mark.asyncio
async def test_download_image_source_offloads_spooled_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    calls: list[str] = []

    class _FakeStreamResponse:
        headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"abc"
            yield b"def"

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, url: str):
            return _FakeStreamResponse()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        monkeypatch.setattr(image_generation_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(
                image_generation_tool,
                "_inside_fake_blocking_io",
                False,
                raising=False,
            )

    monkeypatch.setattr(image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeClient())
    monkeypatch.setattr(image_generation_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(image_generation_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(image_generation_tool, "_inside_fake_blocking_io", False, raising=False)

    image_file, content_type, filename = await image_generation_tool._download_image_source(
        "https://example.com/image.png",
        None,
    )

    try:
        assert bytes(image_file.data) == b"abcdef"
        assert content_type == "image/png"
        assert filename == "image.png"
        assert calls == ["write", "write", "seek"]
    finally:
        image_file.close()


@pytest.mark.asyncio
async def test_image_generate_returns_error_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(image_generation_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"error": "IMAGE_GENERATION_API_KEY is not configured"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_image_generate_offloads_exception_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    async def fake_call_generation_api(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(image_generation_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(image_generation_tool, "_call_generation_api", fake_call_generation_api)

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"error": "Image generation failed: boom"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_image_generate_normalizes_unsupported_portrait_size_for_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    b64_image = base64.b64encode(b"fake-png").decode("ascii")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse({"data": [{"b64_json": b64_image}]})

    class _FakeStorage:
        is_local = False

        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("generated images should use upload_file")

        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/gen.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    await image_generation_tool.image_generate.coroutine(
        prompt="draw a cat",
        size="768x1024",
        runtime=_Runtime("user-1"),
    )

    assert captured["kwargs"]["json"]["size"] == "768x1024"


@pytest.mark.asyncio
async def test_image_generate_normalizes_unsupported_portrait_size_for_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    image_bytes = b"edit-source"
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield image_bytes

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            return _FakeResponse({})

        async def post(self, request_url: str, **kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse({"data": [{"b64_json": b64_image}]})

    class _FakeStorage:
        is_local = False

        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("generated images should use upload_file")

        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/edit.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    await image_generation_tool.image_generate.coroutine(
        prompt="make it brighter",
        input_images=["/api/upload/file/generated-images/user-1/source.png"],
        size="768x1024",
        runtime=_Runtime("user-1"),
    )

    assert captured["kwargs"]["data"]["size"] == "768x1024"


async def test_image_generate_with_input_images_uses_edits_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    image_bytes = b"edit-source"
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield image_bytes

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            captured.setdefault("download_urls", []).append(request_url)
            return _FakeResponse({})

        async def post(self, request_url: str, **kwargs):
            captured["request_url"] = request_url
            captured["kwargs"] = kwargs
            return _FakeResponse({"data": [{"b64_json": b64_image}]})

    class _FakeStorage:
        is_local = False

        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("generated images should use upload_file")

        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            captured["upload"] = {
                "data": file.read(),
                "folder": folder,
                "filename": filename,
                "content_type": content_type,
            }
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url="https://oss.example.com/edit.png",
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool,
        "utc_now",
        lambda: datetime(2026, 5, 23, 12, 34, 56, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="make it brighter",
            input_images=["/api/upload/file/generated-images/user-1/source.png"],
            runtime=_Runtime("user-1"),
        )
    )

    assert captured["request_url"] == "https://api.example.com/v1/images/edits"
    assert captured["download_urls"] == [
        "https://app.example.com/api/upload/file/generated-images/user-1/source.png"
    ]
    assert captured["kwargs"]["data"]["prompt"] == "make it brighter"
    assert captured["kwargs"]["data"]["background"] == "auto"
    assert captured["kwargs"]["data"]["input_fidelity"] == "low"
    assert captured["kwargs"]["files"][0][0] == "image"
    assert (
        result["images"][0]["url"]
        == "https://app.example.com/api/upload/file/generated-images/user-1/generated-20260523_123456-1.png"
    )
    assert captured["upload"]["filename"] == "generated-20260523_123456-1.png"
    assert "mask_url" not in result


@pytest.mark.asyncio
async def test_image_generate_streams_input_image_downloads_for_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    image_bytes = b"streamed-edit-source"
    b64_image = base64.b64encode(b"fake-png").decode("ascii")

    class _FakeResponse:
        def __init__(self, payload: dict[str, object] | None = None) -> None:
            self._payload = payload or {}
            self.headers = {"content-type": "image/png"}

        @property
        def content(self):
            raise AssertionError("image downloads should stream into a file")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield image_bytes[:8]
            yield image_bytes[8:]

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            captured["download_url"] = request_url
            return _FakeResponse()

        async def post(self, request_url: str, **kwargs):
            captured["request_url"] = request_url
            captured["uploaded_source"] = kwargs["files"][0][1][1].read()
            return _FakeResponse({"data": [{"b64_json": b64_image}]})

    class _FakeStorage:
        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            captured["result_upload"] = file.read()
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/edit.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="make it brighter",
            input_images=["https://files.example.com/source.png"],
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert captured["download_url"] == "https://files.example.com/source.png"
    assert captured["request_url"] == "https://api.example.com/v1/images/edits"
    assert captured["uploaded_source"] == image_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_ref",
    [
        "https://files.example.com/reference.png",
        "data:image/png;base64,aW1hZ2U=",
        "/workspace/reference.png",
    ],
    ids=["url_compresses", "data_url_compresses", "backend_path_compresses"],
)
async def test_image_generate_compresses_oversized_input_images_before_edit_request(
    monkeypatch: pytest.MonkeyPatch,
    image_ref: str,
) -> None:
    from src.infra.tool import image_generation_tool

    original = b"x" * (5 * 1024 * 1024 + 1)
    compressed = b"compressed-jpeg"
    captured: dict[str, object] = {}

    async def fake_download(source: str, runtime, *, index: int = 0):
        assert source == image_ref
        image_file = SpooledTemporaryFile(mode="w+b")
        image_file.write(original)
        image_file.seek(0)
        return image_file, "image/png", "reference.png"

    def fake_compress(content: bytes, mime_type: str):
        captured["compress_input"] = (content, mime_type)
        return compressed, "image/jpeg"

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"b64_json": "unused"}]}

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            filename, image_file, content_type = kwargs["files"][0][1]
            captured["multipart"] = (filename, image_file.read(), content_type)
            return _FakeResponse()

    async def fake_convert_result_item(*args, **kwargs):
        return {"url": "/generated.png"}

    monkeypatch.setattr(image_generation_tool, "_download_image_source", fake_download)
    monkeypatch.setattr(
        image_generation_tool,
        "compress_image_bytes_if_needed",
        fake_compress,
        raising=False,
    )
    monkeypatch.setattr(image_generation_tool, "_convert_result_item", fake_convert_result_item)
    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")

    result = await image_generation_tool._call_edit_api(
        prompt="edit",
        input_images=[image_ref],
        background="auto",
        input_fidelity="low",
        size="1024x1024",
        quality="auto",
        output_format="png",
        runtime=_Runtime("user-1"),
    )

    assert result["success"] is True
    assert captured["compress_input"] == (original, "image/png")
    assert captured["multipart"] == ("reference.jpg", compressed, "image/jpeg")


@pytest.mark.asyncio
async def test_image_generate_keeps_original_edit_source_when_compression_is_not_smaller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    original = b"already-compact-image"
    captured: dict[str, object] = {}
    blocking_calls: list[str] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    async def fake_download(source: str, runtime, *, index: int = 0):
        image_file = SpooledTemporaryFile(mode="w+b")
        image_file.write(original)
        image_file.seek(0)
        return image_file, "image/png", "reference.png"

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"b64_json": "unused"}]}

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            filename, image_file, content_type = kwargs["files"][0][1]
            captured["multipart"] = (filename, image_file.read(), content_type)
            return _FakeResponse()

    async def fake_convert_result_item(*args, **kwargs):
        return {"url": "/generated.png"}

    monkeypatch.setattr(image_generation_tool, "_download_image_source", fake_download)
    monkeypatch.setattr(image_generation_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        image_generation_tool,
        "compress_image_bytes_if_needed",
        lambda content, mime_type: (content, mime_type),
    )
    monkeypatch.setattr(image_generation_tool, "_convert_result_item", fake_convert_result_item)
    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")

    result = await image_generation_tool._call_edit_api(
        prompt="edit",
        input_images=["/workspace/reference.png"],
        background="auto",
        input_fidelity="low",
        size="1024x1024",
        quality="auto",
        output_format="png",
        runtime=_Runtime("user-1"),
    )

    assert result["success"] is True
    assert captured["multipart"] == ("reference.png", original, "image/png")
    assert "close" in blocking_calls


@pytest.mark.asyncio
async def test_compressed_edit_source_files_close_when_a_later_download_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    originals: list[SpooledTemporaryFile] = []
    replacements: list[SpooledTemporaryFile] = []

    async def fake_download(source: str, runtime, *, index: int = 0):
        if index == 1:
            raise ValueError("second image failed")
        image_file = SpooledTemporaryFile(mode="w+b")
        image_file.write(b"oversized-image")
        image_file.seek(0)
        originals.append(image_file)
        return image_file, "image/png", "reference.png"

    def fake_spool(content: bytes):
        image_file = SpooledTemporaryFile(mode="w+b")
        image_file.write(content)
        image_file.seek(0)
        replacements.append(image_file)
        return image_file

    monkeypatch.setattr(image_generation_tool, "_download_image_source", fake_download)
    monkeypatch.setattr(
        image_generation_tool,
        "compress_image_bytes_if_needed",
        lambda content, mime_type: (b"compressed", "image/jpeg"),
    )
    monkeypatch.setattr(image_generation_tool, "_spool_backend_image", fake_spool)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")

    with pytest.raises(ValueError, match="second image failed"):
        await image_generation_tool._call_edit_api(
            prompt="edit",
            input_images=["/workspace/first.png", "/workspace/second.png"],
            background="auto",
            input_fidelity="low",
            size="1024x1024",
            quality="auto",
            output_format="png",
            runtime=_Runtime("user-1"),
        )

    assert originals and all(image_file.closed for image_file in originals)
    assert replacements and all(image_file.closed for image_file in replacements)


@pytest.mark.asyncio
async def test_edit_source_closes_when_compression_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    image_file = SpooledTemporaryFile(mode="w+b")
    image_file.write(b"oversized-image")
    image_file.seek(0)

    def cancel_compression(content: bytes, mime_type: str):
        raise asyncio.CancelledError

    monkeypatch.setattr(
        image_generation_tool,
        "compress_image_bytes_if_needed",
        cancel_compression,
    )

    with pytest.raises(asyncio.CancelledError):
        await image_generation_tool._compress_image_source_if_needed(
            image_file,
            "image/png",
            "reference.png",
        )

    assert image_file.closed


@pytest.mark.asyncio
async def test_close_image_files_attempts_every_close_after_one_fails() -> None:
    from src.infra.tool import image_generation_tool

    close_calls: list[str] = []

    class _File:
        def __init__(self, name: str, *, fail: bool = False) -> None:
            self.name = name
            self.fail = fail

        def close(self) -> None:
            close_calls.append(self.name)
            if self.fail:
                raise OSError(f"failed to close {self.name}")

    with pytest.raises(OSError, match="failed to close first"):
        await image_generation_tool._close_image_files(
            [_File("first", fail=True), _File("second")],
        )

    assert close_calls == ["first", "second"]


@pytest.mark.asyncio
async def test_image_generate_uses_backend_path_for_reference_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    source_bytes = b"\x89PNG\r\n\x1a\nbackend-image"
    generated_image = base64.b64encode(b"generated-image").decode("ascii")

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            captured["backend_paths"] = paths
            return [
                SimpleNamespace(
                    path="/workspace/reference.png",
                    content=source_bytes,
                    error=None,
                )
            ]

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            captured["request_url"] = request_url
            filename, image_file, content_type = kwargs["files"][0][1]
            captured["source_file"] = (filename, image_file.read(), content_type)
            return _FakeResponse({"data": [{"b64_json": generated_image}]})

    class _FakeStorage:
        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/generated.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="use this image as a reference",
            input_images=["/workspace/reference.png"],
            runtime=_Runtime("user-1", backend=_FakeBackend()),
        )
    )

    assert result["success"] is True
    assert captured["backend_paths"] == ["/workspace/reference.png"]
    assert captured["request_url"] == "https://api.example.com/v1/images/edits"
    filename, content, content_type = captured["source_file"]
    assert filename == "reference.png"
    assert content == source_bytes
    assert content_type == "image/png"


@pytest.mark.parametrize(
    ("image_ref", "expected_path"),
    [
        ("/workspace/reference.png", "/workspace/reference.png"),
        ("workspace/reference.png", "workspace/reference.png"),
    ],
)
def test_backend_path_classifier_accepts_sandbox_reference_paths(
    image_ref: str,
    expected_path: str,
) -> None:
    from src.infra.tool.image_generation_tool import _backend_path_from_image_reference

    assert _backend_path_from_image_reference(image_ref) == expected_path


def test_backend_path_classifier_rejects_file_uri_reference() -> None:
    from src.infra.tool.image_generation_tool import _backend_path_from_image_reference

    assert _backend_path_from_image_reference("file:///workspace/reference%20image.png") is None


def test_backend_path_classifier_rejects_protocol_relative_url() -> None:
    from src.infra.tool.image_generation_tool import _backend_path_from_image_reference

    assert _backend_path_from_image_reference("//cdn.example.com/reference.png") is None


@pytest.mark.asyncio
async def test_image_generation_preserves_root_relative_url_without_runtime_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}

    class _FakeResponse:
        headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"image"

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method: str, request_url: str):
            captured["request_url"] = request_url
            return _FakeResponse()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )

    image_file, content_type, filename = await image_generation_tool._download_image_source(
        "/images/reference.png",
        _Runtime("user-1", backend=None),
    )

    try:
        assert captured["request_url"] == "https://app.example.com/images/reference.png"
        assert content_type == "image/png"
        assert filename == "reference.png"
    finally:
        image_file.close()


@pytest.mark.asyncio
async def test_backend_reference_image_rejects_oversized_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(path=paths[0], content=b"oversized", error=None)]

    monkeypatch.setattr(image_generation_tool, "_IMAGE_DOWNLOAD_MAX_BYTES", 4)

    with pytest.raises(ValueError, match="Image download too large"):
        await image_generation_tool._download_image_source(
            "/workspace/reference.png",
            _Runtime("user-1", backend=_FakeBackend()),
        )


@pytest.mark.asyncio
async def test_image_generation_reads_reference_image_from_e2b_sandbox_backend() -> None:
    from src.infra.backend.e2b import E2BBackend
    from src.infra.tool.image_generation_tool import _download_image_source

    source_path = "/home/user/assets/reference.png"
    source_bytes = b"\x89PNG\r\n\x1a\nsandbox-image"

    class _FakeSandboxFiles:
        def __init__(self) -> None:
            self.read_calls: list[tuple[str, str]] = []

        def list(self, path: str):
            assert path == "/home/user/assets"
            return [SimpleNamespace(path=source_path, size=len(source_bytes))]

        def read(self, path: str, format: str):
            self.read_calls.append((path, format))
            return source_bytes

    files = _FakeSandboxFiles()
    backend = E2BBackend(
        sandbox=SimpleNamespace(sandbox_id="e2b-test", files=files),
        work_dir="/home/user",
    )

    image_file, content_type, filename = await _download_image_source(
        source_path,
        _Runtime("user-1", backend=backend),
    )

    try:
        assert files.read_calls == [(source_path, "bytes")]
        assert image_file.read() == source_bytes
        assert content_type == "image/png"
        assert filename == "reference.png"
    finally:
        image_file.close()


@pytest.mark.asyncio
async def test_image_generation_resolves_relative_reference_path_for_daytona_sandbox() -> None:
    from deepagents.backends import CompositeBackend

    from src.infra.backend.daytona import DaytonaBackend
    from src.infra.tool.image_generation_tool import _download_image_source

    source_bytes = b"\x89PNG\r\n\x1a\ndaytona-image"
    captured: dict[str, object] = {}

    class _FakeFilesystem:
        def download_files(self, requests):
            captured["sources"] = [request.source for request in requests]
            return [SimpleNamespace(source=requests[0].source, result=source_bytes)]

    backend = DaytonaBackend(
        sandbox=SimpleNamespace(id="daytona-test", fs=_FakeFilesystem()),
        work_dir="/home/daytona",
    )
    backend._file_size = lambda path: None
    runtime_backend = CompositeBackend(default=backend, routes={})

    image_file, content_type, filename = await _download_image_source(
        "assets/reference.png",
        _Runtime("user-1", backend=runtime_backend),
    )

    try:
        assert captured["sources"] == ["/home/daytona/assets/reference.png"]
        assert image_file.read() == source_bytes
        assert content_type == "image/png"
        assert filename == "reference.png"
    finally:
        image_file.close()


@pytest.mark.asyncio
async def test_image_generation_reads_relative_reference_image_from_cubesandbox() -> None:
    from src.infra.backend.cubesandbox import CubeSandboxBackend
    from src.infra.tool.image_generation_tool import _download_image_source

    source_path = "/home/cube/assets/reference.png"
    source_bytes = b"\x89PNG\r\n\x1a\ncube-image"

    class _FakeSandboxFiles:
        def __init__(self) -> None:
            self.read_calls: list[str] = []

        def read(self, path: str):
            self.read_calls.append(path)
            return source_bytes

    files = _FakeSandboxFiles()
    backend = CubeSandboxBackend(
        sandbox=SimpleNamespace(sandbox_id="cube-test", files=files),
        work_dir="/home/cube",
    )
    backend._file_size = lambda path: None

    image_file, content_type, filename = await _download_image_source(
        "assets/reference.png",
        _Runtime("user-1", backend=backend),
    )

    try:
        assert files.read_calls == [source_path]
        assert image_file.read() == source_bytes
        assert content_type == "image/png"
        assert filename == "reference.png"
    finally:
        image_file.close()


@pytest.mark.asyncio
async def test_image_generate_decodes_base64_result_in_chunks_before_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    captured: dict[str, object] = {}
    image_bytes = b"x" * (1024 * 1024)
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    real_b64decode = image_generation_tool.base64.b64decode

    def guarded_b64decode(data, *args, **kwargs):
        if isinstance(data, str) and len(data) == len(b64_image):
            raise AssertionError("generated image payload should not be decoded in one block")
        return real_b64decode(data, *args, **kwargs)

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"b64_json": b64_image}]}

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            return _FakeResponse()

    class _FakeStorage:
        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            captured["upload"] = file.read()
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/generated.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(image_generation_tool.base64, "b64decode", guarded_b64decode)
    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert captured["upload"] == image_bytes


@pytest.mark.asyncio
async def test_image_generate_offloads_base64_result_spooled_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    calls: list[str] = []
    b64_image = base64.b64encode(b"fake-png").decode("ascii")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": [{"b64_json": b64_image}]}

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            return _FakeResponse()

    class _FakeStorage:
        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            assert bytes(file.data) == b"fake-png"
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/generated.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        monkeypatch.setattr(image_generation_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(
                image_generation_tool,
                "_inside_fake_blocking_io",
                False,
                raising=False,
            )

    monkeypatch.setattr(
        image_generation_tool.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeHttpClient(),
    )
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(image_generation_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(image_generation_tool, "_inside_fake_blocking_io", False, raising=False)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert "_extract_image_payload" in calls
    assert "_file_size" in calls
    assert "seek" in calls
    assert "close" in calls
    assert "dumps" in calls


@pytest.mark.asyncio
async def test_image_generate_retries_retryable_api_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    attempts: list[str] = []
    image_bytes = b"fake-png"
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.request = image_generation_tool.httpx.Request(
                "POST",
                "https://api.example.com/v1/images/generations",
            )

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise image_generation_tool.httpx.HTTPStatusError(
                    f"status {self.status_code}",
                    request=self.request,
                    response=self,
                )

        def json(self) -> dict[str, object]:
            return self._payload

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            attempts.append(request_url)
            if len(attempts) == 1:
                return _FakeResponse(429, {"error": {"message": "rate limit"}})
            return _FakeResponse(200, {"data": [{"b64_json": b64_image}]})

    class _FakeStorage:
        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("generated images should use upload_file")

        async def upload_file(self, file, folder: str, filename: str, content_type: str, **kwargs):
            return SimpleNamespace(
                key=f"{folder}/{filename}", url="https://oss.example.com/gen.png"
            )

    async def fake_get_or_init_storage():
        return _FakeStorage()

    sleep_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(image_generation_tool, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_MODEL", "gpt-image-2")

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert len(attempts) == 2
    assert len(sleep_delays) == 1
    assert 1.0 <= sleep_delays[0] <= 1.5  # base 1.0s + jitter [0, 0.5]


@pytest.mark.asyncio
async def test_image_generate_does_not_retry_non_retryable_api_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import image_generation_tool

    attempts: list[str] = []

    class _FakeResponse:
        status_code = 400

        def __init__(self) -> None:
            self.request = image_generation_tool.httpx.Request(
                "POST",
                "https://api.example.com/v1/images/generations",
            )

        def raise_for_status(self) -> None:
            raise image_generation_tool.httpx.HTTPStatusError(
                "bad request",
                request=self.request,
                response=self,
            )

        def json(self) -> dict[str, object]:
            return {"error": {"message": "bad request"}}

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, request_url: str, **kwargs):
            attempts.append(request_url)
            return _FakeResponse()

    monkeypatch.setattr(
        image_generation_tool.httpx, "AsyncClient", lambda **kwargs: _FakeHttpClient()
    )
    monkeypatch.setattr(image_generation_tool.settings, "IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setattr(
        image_generation_tool.settings,
        "IMAGE_GENERATION_BASE_URL",
        "https://api.example.com/v1",
    )

    result = json.loads(
        await image_generation_tool.image_generate.coroutine(
            prompt="draw a cat",
            runtime=_Runtime("user-1"),
        )
    )

    assert len(attempts) == 1
    assert "400" in result["error"] or "bad request" in result["error"]


@pytest.mark.asyncio
async def test_search_agent_context_includes_image_generation_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    search_context = _load_module_from_path(
        "search_context_with_image_tool_under_test",
        "src/agents/search_agent/context.py",
    )

    monkeypatch.setattr(search_context.settings, "ENABLE_IMAGE_GENERATION", True)
    monkeypatch.setattr(search_context.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SKILLS", False)

    ctx = search_context.SearchAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "image_generate" in names


@pytest.mark.asyncio
async def test_fast_agent_context_includes_image_generation_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_context_tool_imports(monkeypatch)
    fast_context = _load_module_from_path(
        "fast_context_with_image_tool_under_test",
        "src/agents/fast_agent/context.py",
    )

    monkeypatch.setattr(fast_context.settings, "ENABLE_IMAGE_GENERATION", True)
    monkeypatch.setattr(fast_context.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SKILLS", False)

    ctx = fast_context.FastAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert "image_generate" in names

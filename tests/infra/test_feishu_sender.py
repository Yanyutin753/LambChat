from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from src.infra.channel.feishu import sender as feishu_sender
from src.infra.channel.feishu import sender_messages
from src.infra.channel.feishu.sender import FeishuSenderMixin


class _DummySender(FeishuSenderMixin):
    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self.config = SimpleNamespace(
            app_id="app-id",
            app_secret="app-secret",
            user_id="user-1",
        )


class _FakeHttpResponse:
    is_error = False
    status_code = 200
    text = ""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_feishu_rest_calls_reuse_one_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    created_clients = 0

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            nonlocal created_clients
            created_clients += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *_args: Any, **_kwargs: Any) -> _FakeHttpResponse:
            return _FakeHttpResponse(
                {"code": 0, "tenant_access_token": "tenant-token", "expire": 7200}
            )

        async def request(self, *_args: Any, **_kwargs: Any) -> _FakeHttpResponse:
            return _FakeHttpResponse({"code": 0, "data": {"ok": True}})

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(feishu_sender.httpx, "AsyncClient", _FakeAsyncClient)

    dummy = _DummySender()

    async def _run() -> None:
        assert await dummy._feishu_json("GET", "/one") == {"code": 0, "data": {"ok": True}}
        assert await dummy._feishu_json("GET", "/two") == {"code": 0, "data": {"ok": True}}

    import asyncio

    asyncio.run(_run())

    assert created_clients == 1


@pytest.mark.asyncio
async def test_feishu_json_offloads_request_body_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []
    captured: dict[str, Any] = {}

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    class _CaptureAsyncClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> _FakeHttpResponse:
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _FakeHttpResponse({"code": 0, "data": {"ok": True}})

    monkeypatch.setattr(sender_base, "run_long_blocking_io", fake_run_long_blocking_io)

    dummy = _DummySender()
    dummy._tenant_access_token = "tenant-token"
    dummy._tenant_access_token_expires_at = 9_999_999_999.0
    dummy._feishu_http_client = _CaptureAsyncClient()

    json_body = {"content": "长文本" * 5000, "sequence": 7}
    result = await dummy._feishu_json(
        "PUT",
        "/cardkit/v1/cards/card-1/elements/stream_md/content",
        json_body=json_body,
        params={"trace": "1"},
    )

    assert result == {"code": 0, "data": {"ok": True}}
    assert calls == [(json.dumps, (json_body,), {"ensure_ascii": False})]
    assert "json" not in captured["kwargs"]
    assert captured["kwargs"]["content"] == json.dumps(json_body, ensure_ascii=False)
    assert captured["kwargs"]["params"] == {"trace": "1"}


@pytest.mark.asyncio
async def test_create_stream_card_offloads_card_json_building(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    calls: list[str] = []
    captured_json_body: dict[str, Any] = {}

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    class _StreamDummySender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            assert method == "POST"
            assert path == "/cardkit/v1/cards"
            captured_json_body.update(kwargs["json_body"])
            return {"code": 0, "data": {"card_id": "card-1"}}

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    card_id = await _StreamDummySender().create_stream_card("x" * 20_000)

    assert card_id == "card-1"
    assert calls == ["_build_stream_card_json"]
    assert captured_json_body["type"] == "card_json"
    assert "x" * 100 in captured_json_body["data"]


@pytest.mark.asyncio
async def test_finalize_stream_card_offloads_card_json_building(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    calls: list[str] = []
    captured_json_body: dict[str, Any] = {}

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append(func.__name__)
        return func(*args, **kwargs)

    class _StreamDummySender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            assert method == "PUT"
            assert path == "/cardkit/v1/cards/card-1"
            captured_json_body.update(kwargs["json_body"])
            return {"code": 0}

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    result = await _StreamDummySender().finalize_stream_card("card-1", "x" * 20_000, 3)

    assert result is True
    assert calls == ["_build_stream_card_json"]
    assert captured_json_body["sequence"] == 3
    assert captured_json_body["card"]["type"] == "card_json"


@pytest.mark.asyncio
async def test_send_card_by_id_offloads_content_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    calls: list[str] = []
    captured_json_body: dict[str, Any] = {}

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append(getattr(func, "__name__", str(func)))
        return func(*args, **kwargs)

    class _StreamDummySender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            assert method == "POST"
            assert path == "/im/v1/messages"
            captured_json_body.update(kwargs["json_body"])
            return {"code": 0, "data": {"message_id": "message-1"}}

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    sent, message_id = await _StreamDummySender().send_card_by_id("oc_chat", "card-1")

    assert sent is True
    assert message_id == "message-1"
    assert calls == ["dumps"]
    assert json.loads(captured_json_body["content"]) == {
        "type": "card",
        "data": {"card_id": "card-1"},
    }


@pytest.mark.asyncio
async def test_send_card_by_id_retries_when_card_not_ready_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        return func(*args, **kwargs)

    payloads = [
        {"code": sender_base._FEISHU_CARD_NOT_READY_CODE},
        {"code": 0, "data": {"message_id": "message-1"}},
    ]
    feishu_calls: list[str] = []
    sleeps: list[float] = []

    class _RetrySender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            feishu_calls.append(path)
            return payloads.pop(0)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )
    monkeypatch.setattr(sender_base.asyncio, "sleep", fake_sleep)

    sent, message_id = await _RetrySender().send_card_by_id("oc_chat", "card-1")

    assert sent is True
    assert message_id == "message-1"
    assert len(feishu_calls) == 2  # first 230099, then success on retry
    assert sleeps == [sender_base._STREAM_CARD_SEND_RETRY_DELAY_SECONDS]


@pytest.mark.asyncio
async def test_send_card_by_id_gives_up_after_max_retries_when_card_still_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        return func(*args, **kwargs)

    feishu_calls: list[str] = []
    sleeps: list[float] = []

    class _AlwaysNotReadySender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            feishu_calls.append(path)
            return {"code": sender_base._FEISHU_CARD_NOT_READY_CODE}

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )
    monkeypatch.setattr(sender_base.asyncio, "sleep", fake_sleep)

    sent, message_id = await _AlwaysNotReadySender().send_card_by_id("oc_chat", "card-1")

    assert sent is False
    assert message_id is None
    # Attempted once per allowed try, backing off between retries.
    assert len(feishu_calls) == sender_base._STREAM_CARD_SEND_MAX_ATTEMPTS
    assert sleeps == [
        sender_base._STREAM_CARD_SEND_RETRY_DELAY_SECONDS * 1,
        sender_base._STREAM_CARD_SEND_RETRY_DELAY_SECONDS * 2,
    ]


@pytest.mark.asyncio
async def test_send_card_by_id_does_not_retry_on_other_error_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_base

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        return func(*args, **kwargs)

    feishu_calls: list[str] = []
    sleeps: list[float] = []

    class _OtherErrorSender(_DummySender):
        async def _feishu_json(self, method: str, path: str, **kwargs: Any):
            feishu_calls.append(path)
            return {"code": 230001}  # not the card-not-ready race

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        sender_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )
    monkeypatch.setattr(sender_base.asyncio, "sleep", fake_sleep)

    sent, message_id = await _OtherErrorSender().send_card_by_id("oc_chat", "card-1")

    assert sent is False
    assert message_id is None
    assert len(feishu_calls) == 1  # no retry for non-230099 codes
    assert sleeps == []


class _Builder:
    def __getattr__(self, _name: str):
        def _method(*_args: Any, **_kwargs: Any):
            return self

        return _method

    def build(self):
        return object()


class _Response:
    def __init__(self, code: int, success: bool) -> None:
        self.code = code
        self.msg = f"msg-{code}"
        self.data = SimpleNamespace(message_id=f"message-{code}")
        self._success = success

    def success(self) -> bool:
        return self._success


class _MessageApi:
    def __init__(self, reply_code: int) -> None:
        self.reply_code = reply_code
        self.create_calls = 0

    def reply(self, _request: Any) -> _Response:
        return _Response(self.reply_code, False)

    def create(self, _request: Any) -> _Response:
        self.create_calls += 1
        return _Response(0, True)


def _install_fake_lark_im_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("lark_oapi.api.im.v1")
    for name in (
        "CreateMessageRequest",
        "CreateMessageRequestBody",
        "ReplyMessageRequest",
        "ReplyMessageRequestBody",
    ):
        setattr(module, name, type(name, (), {"builder": staticmethod(lambda: _Builder())}))

    monkeypatch.setitem(sys.modules, "lark_oapi", ModuleType("lark_oapi"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api", ModuleType("lark_oapi.api"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im", ModuleType("lark_oapi.api.im"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im.v1", module)


def test_card_reply_does_not_fallback_for_unexpected_reply_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_lark_im_module(monkeypatch)
    message_api = _MessageApi(reply_code=999999)
    dummy = _DummySender(
        SimpleNamespace(im=SimpleNamespace(v1=SimpleNamespace(message=message_api)))
    )

    assert dummy._send_card_message_sync("chat_id", "oc_1", "{}", "om_1") == (False, None)
    assert message_api.create_calls == 0


def test_card_reply_falls_back_for_withdrawn_original_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_lark_im_module(monkeypatch)
    message_api = _MessageApi(reply_code=230011)
    dummy = _DummySender(
        SimpleNamespace(im=SimpleNamespace(v1=SimpleNamespace(message=message_api)))
    )

    assert dummy._send_card_message_sync("chat_id", "oc_1", "{}", "om_1") == (
        True,
        "message-0",
    )
    assert message_api.create_calls == 1


@pytest.mark.asyncio
async def test_send_message_offloads_text_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append(getattr(func, "__name__", str(func)))
        return func(*args, **kwargs)

    class _CaptureSender(_DummySender):
        def __init__(self) -> None:
            super().__init__(client=object())
            self.sent_content: str | None = None

        def _send_message_sync(
            self, receive_id_type: str, receive_id: str, msg_type: str, content: str
        ) -> bool:
            assert receive_id_type == "chat_id"
            assert receive_id == "oc_chat"
            assert msg_type == "text"
            self.sent_content = content
            return True

    monkeypatch.setattr(sender_messages, "run_long_blocking_io", fake_run_long_blocking_io)
    dummy = _CaptureSender()

    assert await dummy.send_message("oc_chat", "长文本消息")

    assert calls == ["dumps", "_send_message_sync"]
    assert json.loads(dummy.sent_content or "{}") == {"text": "长文本消息"}


@pytest.mark.asyncio
async def test_patch_message_offloads_fallback_json_only_after_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_long_blocking_io(func, *args: Any, **kwargs: Any):
        calls.append(getattr(func, "__name__", str(func)))
        return func(*args, **kwargs)

    class _CaptureSender(_DummySender):
        def __init__(self) -> None:
            super().__init__(client=object())
            self.patch_content: str | None = None

        def _update_text_message_sync(self, message_id: str, content: str) -> bool:
            assert message_id == "om_1"
            assert content == "长文本消息"
            return False

        def _patch_message_sync(self, message_id: str, content: str) -> bool:
            assert message_id == "om_1"
            self.patch_content = content
            return True

    monkeypatch.setattr(sender_messages, "run_long_blocking_io", fake_run_long_blocking_io)
    dummy = _CaptureSender()

    assert await dummy.patch_message("om_1", "长文本消息")

    assert calls == ["_update_text_message_sync", "dumps", "_patch_message_sync"]
    assert json.loads(dummy.patch_content or "{}") == {"text": "长文本消息"}


def test_send_file_by_key_passes_reply_to_id_to_file_sender() -> None:
    class _CaptureFileSender(_DummySender):
        def __init__(self) -> None:
            super().__init__(client=object())
            self.calls: list[tuple[str, str, str, str, str | None]] = []

        def _send_file_message_sync(
            self,
            chat_id: str,
            file_key: str,
            file_name: str,
            msg_type: str = "file",
            reply_to_id: str | None = None,
        ) -> bool:
            self.calls.append((chat_id, file_key, file_name, msg_type, reply_to_id))
            return True

    dummy = _CaptureFileSender()

    import asyncio

    assert asyncio.run(
        dummy.send_file_by_key(
            chat_id="oc_chat",
            file_key="file-key",
            file_name="doc.md",
            reply_to_id="om_original",
        )
    )
    assert dummy.calls == [
        ("oc_chat", "file-key", "doc.md", "file", "om_original"),
    ]


def test_send_image_by_key_passes_reply_to_id_to_image_sender() -> None:
    class _CaptureImageSender(_DummySender):
        def __init__(self) -> None:
            super().__init__(client=object())
            self.calls: list[tuple[str, str, str | None]] = []

        def _send_image_message_sync(
            self,
            chat_id: str,
            image_key: str,
            reply_to_id: str | None = None,
        ) -> bool:
            self.calls.append((chat_id, image_key, reply_to_id))
            return True

    dummy = _CaptureImageSender()

    import asyncio

    assert asyncio.run(
        dummy.send_image_by_key(
            chat_id="oc_chat",
            image_key="image-key",
            reply_to_id="om_original",
        )
    )
    assert dummy.calls == [
        ("oc_chat", "image-key", "om_original"),
    ]


def test_upload_bytes_rejects_payload_above_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_files

    class _CaptureUploadSender(_DummySender):
        def _upload_bytes_sync(self, *_args: Any, **_kwargs: Any) -> str | None:
            raise AssertionError("oversized bytes should be rejected before SDK upload")

    monkeypatch.setattr(
        sender_files,
        "settings",
        SimpleNamespace(FEISHU_UPLOAD_BYTES_MAX_SIZE=3),
    )
    dummy = _CaptureUploadSender(client=object())

    import asyncio

    assert asyncio.run(dummy.upload_bytes(b"too-large", "large.txt")) is None


def test_upload_image_rejects_payload_above_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_files

    class _CaptureUploadSender(_DummySender):
        def _upload_image_sync(self, *_args: Any, **_kwargs: Any) -> str | None:
            raise AssertionError("oversized image should be rejected before SDK upload")

    monkeypatch.setattr(
        sender_files,
        "settings",
        SimpleNamespace(FEISHU_UPLOAD_BYTES_MAX_SIZE=3),
    )
    dummy = _CaptureUploadSender(client=object())

    import asyncio

    assert asyncio.run(dummy.upload_image(b"too-large-image")) is None


def test_download_resource_sync_reads_response_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    read_sizes: list[int] = []

    class _FakeFile:
        def __init__(self) -> None:
            self.chunks = [b"ab", b"cd"]

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            if size == -1:
                raise AssertionError("Feishu resource download must not read all bytes at once")
            if not self.chunks:
                return b""
            return self.chunks.pop(0)

    class _FakeResourceResponse:
        code = 0
        msg = "ok"

        def __init__(self) -> None:
            self.file = _FakeFile()

        def success(self) -> bool:
            return True

    class _FakeResourceApi:
        def get(self, _request: Any) -> _FakeResourceResponse:
            return _FakeResourceResponse()

    module = ModuleType("lark_oapi.api.im.v1")
    module.GetMessageResourceRequest = type(
        "GetMessageResourceRequest",
        (),
        {"builder": staticmethod(lambda: _Builder())},
    )
    monkeypatch.setitem(sys.modules, "lark_oapi", ModuleType("lark_oapi"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api", ModuleType("lark_oapi.api"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im", ModuleType("lark_oapi.api.im"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im.v1", module)

    dummy = _DummySender(
        SimpleNamespace(im=SimpleNamespace(v1=SimpleNamespace(message_resource=_FakeResourceApi())))
    )

    assert dummy._download_resource_sync("file-key", "message-1", "file") == b"abcd"
    assert -1 not in read_sizes


def test_download_resource_sync_refuses_large_legacy_bytes_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_files

    class _LargeResourceSender(_DummySender):
        def _download_resource_to_file_sync(
            self,
            file_key: str,
            message_id: str,
            resource_type: str,
            file,
        ) -> int:
            assert (file_key, message_id, resource_type) == ("file-key", "message-1", "file")
            file.write(b"x" * 16)
            file.seek(0)
            return 16

    monkeypatch.setattr(sender_files, "_LEGACY_BYTES_DOWNLOAD_MAX_BYTES", 8)

    dummy = _LargeResourceSender(object())

    assert dummy._download_resource_sync("file-key", "message-1", "file") is None


def test_download_resource_sync_stops_when_legacy_bytes_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_files

    read_chunks: list[bytes] = []

    class _FakeFile:
        def __init__(self) -> None:
            self.chunks = [b"x" * 5, b"y" * 5, b"z" * 5]

        def read(self, size: int = -1) -> bytes:
            assert size != -1
            if not self.chunks:
                return b""
            chunk = self.chunks.pop(0)
            read_chunks.append(chunk)
            return chunk

    class _FakeResourceResponse:
        code = 0
        msg = "ok"

        def __init__(self) -> None:
            self.file = _FakeFile()

        def success(self) -> bool:
            return True

    class _FakeResourceApi:
        def get(self, _request: Any) -> _FakeResourceResponse:
            return _FakeResourceResponse()

    module = ModuleType("lark_oapi.api.im.v1")
    module.GetMessageResourceRequest = type(
        "GetMessageResourceRequest",
        (),
        {"builder": staticmethod(lambda: _Builder())},
    )
    monkeypatch.setitem(sys.modules, "lark_oapi", ModuleType("lark_oapi"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api", ModuleType("lark_oapi.api"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im", ModuleType("lark_oapi.api.im"))
    monkeypatch.setitem(sys.modules, "lark_oapi.api.im.v1", module)
    monkeypatch.setattr(sender_files, "_LEGACY_BYTES_DOWNLOAD_MAX_BYTES", 8)

    dummy = _DummySender(
        SimpleNamespace(im=SimpleNamespace(v1=SimpleNamespace(message_resource=_FakeResourceApi())))
    )

    assert dummy._download_resource_sync("file-key", "message-1", "file") is None
    assert read_chunks == [b"x" * 5, b"y" * 5]


@pytest.mark.asyncio
async def test_download_and_store_resource_streams_to_storage_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StreamingResourceSender(_DummySender):
        def _download_resource_to_file_sync(
            self,
            file_key: str,
            message_id: str,
            resource_type: str,
            file,
            *,
            max_bytes: int | None = None,
        ) -> int:
            del max_bytes
            assert (file_key, message_id, resource_type) == ("file-key", "message-1", "file")
            file.write(b"feishu-resource")
            file.seek(0)
            return len(b"feishu-resource")

    class _FakeStorage:
        def __init__(self) -> None:
            self.upload_file_calls: list[tuple[bytes, str, str, str | None]] = []

        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            metadata: dict[str, str] | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del metadata, skip_size_limit
            self.upload_file_calls.append((file.read(), folder, filename, content_type))
            return SimpleNamespace(
                key="feishu_file/uploaded.txt",
                url="/api/upload/file/feishu_file/uploaded.txt",
                content_type=content_type,
            )

        async def upload_bytes(self, *args: Any, **kwargs: Any):
            raise AssertionError("Feishu resource storage must not materialize bytes")

    storage = _FakeStorage()

    async def _fake_get_storage() -> _FakeStorage:
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )

    result = await _StreamingResourceSender()._download_and_store_resource(
        "file-key",
        "message-1",
        resource_type="file",
        file_name="uploaded.txt",
        attachment_type="file",
        content_type="text/plain",
    )

    assert storage.upload_file_calls == [
        (b"feishu-resource", "feishu_file", "uploaded.txt", "text/plain")
    ]
    assert result == {
        "key": "feishu_file/uploaded.txt",
        "name": "uploaded.txt",
        "type": "file",
        "mime_type": "text/plain",
        "size": len(b"feishu-resource"),
        "url": "/api/upload/file/feishu_file/uploaded.txt",
    }


@pytest.mark.asyncio
async def test_download_and_store_resource_passes_download_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import sender_files

    class _LimitedResourceSender(_DummySender):
        seen_max_bytes: int | None = None

        def _download_resource_to_file_sync(
            self,
            file_key: str,
            message_id: str,
            resource_type: str,
            file,
            *,
            max_bytes: int | None = None,
        ) -> int:
            del file
            assert (file_key, message_id, resource_type) == ("file-key", "message-1", "file")
            self.seen_max_bytes = max_bytes
            return 0

    class _FakeStorage:
        async def upload_file(self, *args: Any, **kwargs: Any):
            raise AssertionError("empty download should not upload")

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        sender_files,
        "settings",
        SimpleNamespace(FEISHU_UPLOAD_BYTES_MAX_SIZE=8),
    )

    sender = _LimitedResourceSender()
    assert (
        await sender._download_and_store_resource(
            "file-key",
            "message-1",
            resource_type="file",
            file_name="uploaded.txt",
            attachment_type="file",
            content_type="text/plain",
        )
        is None
    )
    assert sender.seen_max_bytes == 8

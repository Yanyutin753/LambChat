"""reveal_file 对本站上传代理 URL（/api/upload/file/<key>）的存在性校验。

背景：agent 常把 image_generate 返回的长 URL 重新抄写一遍再传给
reveal_file，24 位 hex user id 抄错一个字符就会把坏 URL 当成功结果
推给前端，渲染成裂图。这里强制：本站 key 必须在 storage 里真实存在，
否则返回结构化错误让 agent 自纠；外部 URL 保持透传不校验。
"""

from __future__ import annotations

import json

import pytest

from src.infra.tool import _reveal_file_support, reveal_file_tool

_SELF_UPLOAD_URL = (
    "https://app.example.com/api/upload/file/generated-images/"
    "69a77b14f5bc37143e7769f0/20260825_024036_60017aa8_generated.png"
)
_SELF_UPLOAD_KEY = (
    "generated-images/69a77b14f5bc37143e7769f0/20260825_024036_60017aa8_generated.png"
)


class _FakeStorage:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.checked_keys: list[str] = []
        self.size_checks: list[str] = []

    async def file_exists(self, key: str) -> bool:
        self.checked_keys.append(key)
        return self.exists

    async def get_size(self, key: str) -> int:
        self.size_checks.append(key)
        return 2097152


class _RecordingIndex:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upsert_by_name(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["cua_screenshots", "tool_binaries"])
@pytest.mark.parametrize("separator", ["/", "%2F"])
async def test_reveal_does_not_probe_private_capture_sizes(
    monkeypatch: pytest.MonkeyPatch, prefix: str, separator: str
) -> None:
    storage = _FakeStorage(exists=True)

    async def _fake_get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _RecordingIndex())
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            f"https://app.example.com/api/upload/file/{prefix}{separator}other-session/screenshot.png",
            runtime=object(),
        )
    )

    assert result["size"] is None
    assert storage.size_checks == []


@pytest.mark.asyncio
async def test_reveal_file_rejects_self_upload_url_with_missing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(exists=False)
    index = _RecordingIndex()

    async def _fake_get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            _SELF_UPLOAD_URL,
            description="broken portrait",
            runtime=object(),
        )
    )

    assert result["type"] == "file_reveal"
    assert result["file"]["path"] == _SELF_UPLOAD_URL
    assert result["file"]["error"] == "remote_url_not_found"
    assert storage.checked_keys == [_SELF_UPLOAD_KEY]
    assert index.calls == []


@pytest.mark.asyncio
async def test_reveal_file_passes_through_self_upload_url_with_existing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(exists=True)

    async def _fake_get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _RecordingIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            _SELF_UPLOAD_URL,
            description="generated portrait",
            runtime=object(),
        )
    )

    assert result["key"] == _SELF_UPLOAD_URL
    assert result["url"] == _SELF_UPLOAD_URL
    assert result["type"] == "image"
    assert result["size"] == 2097152
    assert result["_meta"]["source"] == "remote_url"
    assert storage.checked_keys == [_SELF_UPLOAD_KEY]


@pytest.mark.asyncio
async def test_reveal_file_urlencodes_key_before_existence_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(exists=False)

    async def _fake_get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _fake_get_storage)

    encoded_url = "https://app.example.com/api/upload/file/generated-images%2Fuser-1%2Fportrait.png"

    result = json.loads(await reveal_file_tool.reveal_file.coroutine(encoded_url, runtime=object()))

    assert result["file"]["error"] == "remote_url_not_found"
    assert storage.checked_keys == ["generated-images/user-1/portrait.png"]


@pytest.mark.asyncio
async def test_reveal_file_self_upload_existence_check_failure_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenStorage:
        async def file_exists(self, key: str) -> bool:
            raise RuntimeError("storage unavailable")

    async def _fake_get_storage():
        return _BrokenStorage()

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _fake_get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _RecordingIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(_SELF_UPLOAD_URL, runtime=object())
    )

    assert result["url"] == _SELF_UPLOAD_URL
    assert result["_meta"]["source"] == "remote_url"


@pytest.mark.asyncio
async def test_reveal_file_storage_init_failure_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """storage 初始化本身失败也必须走透传，不能让整个工具调用报错。"""

    async def _broken_get_storage():
        raise RuntimeError("storage init failed")

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _broken_get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _broken_get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _RecordingIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(_SELF_UPLOAD_URL, runtime=object())
    )

    assert result["url"] == _SELF_UPLOAD_URL
    assert result["_meta"]["source"] == "remote_url"


async def test_relative_upload_url_is_revealed_without_reading_sandbox(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(reveal_file_tool, "_self_upload_url_missing", AsyncMock(return_value=False))
    monkeypatch.setattr(reveal_file_tool, "_index_revealed_file", AsyncMock())
    runtime = SimpleNamespace(config={"configurable": {"base_url": "https://app.example.com"}})
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/api/upload/file/images/photo.png", runtime=runtime
        )
    )
    assert result["url"] == "https://app.example.com/api/upload/file/images/photo.png"
    assert result["type"] == "image"


async def test_own_capture_uses_authorized_record_size(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.upload import file_record

    records = type(
        "Records", (), {"require_private_access": AsyncMock(return_value={"size": 12345})}
    )()
    monkeypatch.setattr(file_record, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(reveal_file_tool, "_reveal_user_id", lambda runtime: "owner")
    monkeypatch.setattr(reveal_file_tool, "get_session_id_from_runtime", lambda runtime: "session")
    monkeypatch.setattr(reveal_file_tool, "_self_upload_url_missing", AsyncMock(return_value=False))
    monkeypatch.setattr(
        reveal_file_tool, "_reverse_map_self_upload_row", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(reveal_file_tool, "_index_revealed_file", AsyncMock())
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "https://app.example/api/upload/file/cua_screenshots/owner/session/a.png",
            runtime=object(),
        )
    )
    assert result["size"] == 12345
    records.require_private_access.assert_awaited_once_with(
        "cua_screenshots/owner/session/a.png", "owner", "session"
    )


@pytest.mark.parametrize("failure", ["denied", "offline"])
async def test_capture_size_denial_stays_unknown_without_storage_probe(monkeypatch, failure):
    from unittest.mock import AsyncMock

    from src.infra.upload import file_record
    from src.kernel.errors import AppError, ErrorCode

    records = type(
        "Records",
        (),
        {
            "require_private_access": AsyncMock(
                side_effect=AppError(ErrorCode.FILE_NOT_FOUND)
                if failure == "denied"
                else RuntimeError("offline")
            )
        },
    )()
    monkeypatch.setattr(file_record, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(reveal_file_tool, "_reveal_user_id", lambda runtime: "other")
    monkeypatch.setattr(
        reveal_file_tool, "get_session_id_from_runtime", lambda runtime: "other-session"
    )
    monkeypatch.setattr(reveal_file_tool, "_self_upload_url_missing", AsyncMock(return_value=False))
    monkeypatch.setattr(
        reveal_file_tool, "_reverse_map_self_upload_row", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(reveal_file_tool, "_index_revealed_file", AsyncMock())
    storage = AsyncMock()
    monkeypatch.setattr(reveal_file_tool, "_get_storage", AsyncMock(return_value=storage))
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "https://app.example/api/upload/file/cua_screenshots/owner/session/a.png",
            runtime=object(),
        )
    )
    assert result["size"] is None
    storage.get_size.assert_not_awaited()

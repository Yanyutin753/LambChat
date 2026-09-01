"""reveal_file 对本站上传代理 URL（/api/upload/file/<key>）的存在性校验。

背景：agent 常把 image_generate 返回的长 URL 重新抄写一遍再传给
reveal_file，24 位 hex user id 抄错一个字符就会把坏 URL 当成功结果
推给前端，渲染成裂图。这里强制：本站 key 必须在 storage 里真实存在，
否则返回结构化错误让 agent 自纠；外部 URL 保持透传不校验。
"""

from __future__ import annotations

import json

import pytest

from src.infra.tool import reveal_file_tool

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

    async def file_exists(self, key: str) -> bool:
        self.checked_keys.append(key)
        return self.exists


class _RecordingIndex:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upsert_by_name(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_reveal_file_rejects_self_upload_url_with_missing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(exists=False)
    index = _RecordingIndex()

    async def _fake_get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_get_storage)
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
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _RecordingIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(_SELF_UPLOAD_URL, runtime=object())
    )

    assert result["url"] == _SELF_UPLOAD_URL
    assert result["_meta"]["source"] == "remote_url"

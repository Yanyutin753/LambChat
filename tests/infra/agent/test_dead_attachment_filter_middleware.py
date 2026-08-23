"""DeadAttachmentFilterMiddleware — drop image blocks whose upload file no longer exists.

背景：模型请求历史携带所有历史轮次的 image_url；上游 new-api 计数 token 时会逐个下载
这些 URL，任何一个 404（文件已被清理）都会导致整个请求失败（count_token_failed）。
该中间件在每次模型调用前批量校验自有上传 URL 的存活性，剔除死链图片块。
"""

import pytest
from langchain_core.messages import HumanMessage

from src.infra.agent.middleware.dead_attachment import (
    DeadAttachmentFilterMiddleware,
)


def _upload_url(key: str) -> str:
    return f"https://lambchat.com/api/upload/file/{key}"


class _Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kwargs):
        return _Request(kwargs.get("messages", self.messages))


def _message_with_blocks(blocks):
    return HumanMessage(content=blocks)


async def _always_alive(keys):
    return set(keys)


@pytest.mark.asyncio
async def test_drops_image_block_whose_file_record_is_missing():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    async def exists(keys):
        assert keys == ["image/u1/dead.png"]
        return set()  # 数据库中没有该 key

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    message = _message_with_blocks(
        [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": _upload_url("image/u1/dead.png")}},
        ]
    )

    await middleware.awrap_model_call(_Request([message]), handler)

    blocks = seen["request"].messages[0].content
    assert [block["type"] for block in blocks] == ["text"]
    assert blocks[0]["text"] == "看这张图"


@pytest.mark.asyncio
async def test_keeps_image_block_when_file_record_exists():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    async def exists(keys):
        return {"image/u1/alive.png"}

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    message = _message_with_blocks(
        [
            {"type": "text", "text": "看这张图"},
            {"type": "image_url", "image_url": {"url": _upload_url("image/u1/alive.png")}},
        ]
    )

    await middleware.awrap_model_call(_Request([message]), handler)

    blocks = seen["request"].messages[0].content
    assert [block["type"] for block in blocks] == ["text", "image_url"]
    assert blocks[1]["image_url"]["url"] == _upload_url("image/u1/alive.png")


@pytest.mark.asyncio
async def test_replaces_image_only_message_with_text_note():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    async def exists(keys):
        return set()

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    message = _message_with_blocks(
        [{"type": "image_url", "image_url": {"url": _upload_url("image/u1/gone.png")}}]
    )

    await middleware.awrap_model_call(_Request([message]), handler)

    blocks = seen["request"].messages[0].content
    assert [block["type"] for block in blocks] == ["text"]
    assert blocks[0]["text"].strip() != ""


@pytest.mark.asyncio
async def test_ignores_data_urls_and_external_urls_without_db_check():
    seen = {}
    checked = []

    async def handler(request):
        seen["request"] = request
        return request

    async def exists(keys):
        checked.extend(keys)
        return set(keys)

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    external = "https://example.com/cat.png"
    message = _message_with_blocks(
        [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1n"}},
            {"type": "image_url", "image_url": {"url": external}},
        ]
    )

    await middleware.awrap_model_call(_Request([message]), handler)

    blocks = seen["request"].messages[0].content
    assert len(blocks) == 2
    assert blocks[1]["image_url"]["url"] == external
    assert checked == []  # 非自有上传 URL 不触发数据库查询


@pytest.mark.asyncio
async def test_anthropic_url_source_blocks_are_filtered_too():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    async def exists(keys):
        return set()

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    message = _message_with_blocks(
        [
            {
                "type": "image",
                "source": {"type": "url", "url": _upload_url("image/u1/gone.png")},
            }
        ]
    )

    await middleware.awrap_model_call(_Request([message]), handler)

    blocks = seen["request"].messages[0].content
    assert [block["type"] for block in blocks] == ["text"]


@pytest.mark.asyncio
async def test_passes_messages_through_when_db_check_fails():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    async def broken_exists(keys):
        raise RuntimeError("mongo down")

    middleware = DeadAttachmentFilterMiddleware(exists_checker=broken_exists)
    message = _message_with_blocks(
        [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": _upload_url("image/u1/maybe.png")}},
        ]
    )
    original = _Request([message])

    await middleware.awrap_model_call(original, handler)

    assert seen["request"].messages[0].content == message.content


@pytest.mark.asyncio
async def test_caches_existence_results_across_calls():
    calls = []

    async def handler(request):
        return request

    async def exists(keys):
        calls.append(list(keys))
        return set()

    middleware = DeadAttachmentFilterMiddleware(exists_checker=exists)
    message = _message_with_blocks(
        [{"type": "image_url", "image_url": {"url": _upload_url("image/u1/dead.png")}}]
    )

    await middleware.awrap_model_call(_Request([message]), handler)
    await middleware.awrap_model_call(_Request([message]), handler)

    assert len(calls) == 1  # 第二次调用复用缓存


@pytest.mark.asyncio
async def test_default_checker_uses_file_records_collection(monkeypatch):
    from src.infra.agent.middleware import dead_attachment

    queried = {}

    class _FakeCursor:
        def __init__(self, docs):
            self.docs = docs

        async def to_list(self, length=None):
            return self.docs

    class _FakeCollection:
        def find(self, query, projection=None):
            queried["query"] = query
            return _FakeCursor([{"key": "image/u1/alive.png"}])

    class _FakeStorage:
        collection = _FakeCollection()

    monkeypatch.setattr(dead_attachment, "FileRecordStorage", lambda: _FakeStorage())

    alive = await dead_attachment._default_exists_checker(["image/u1/alive.png", "image/u1/dead.png"])

    assert alive == {"image/u1/alive.png"}
    assert queried["query"] == {"key": {"$in": ["image/u1/alive.png", "image/u1/dead.png"]}}

"""HistoricalImageCapMiddleware — 超限历史图片替换为 URL 文本占位符。

约束（KV 缓存友好）：
- 迟滞触发：图片数超过 hard_limit 才淘汰一次，淘汰到 keep_limit；区间内不动作，
  保证两次淘汰之间请求前缀完全稳定（缓存不抖动）。
- 确定性：同样的历史 → 同样的替换结果，纯函数式，不落库。
- 永不触碰最后一条 HumanMessage（当前轮上下文）。
- 占位符保留原 URL（模型需要时可按链接取回），纯文本不触发上游图片下载。
"""

import pytest
from langchain_core.messages import HumanMessage

from src.infra.agent.middleware.dead_attachment import HistoricalImageCapMiddleware


def _upload_url(name: str) -> str:
    return f"https://lambchat.com/api/upload/file/image/u1/{name}.png"


class _Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kwargs):
        return _Request(kwargs.get("messages", self.messages))


def _image_message(names, text=None):
    blocks = []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.extend({"type": "image_url", "image_url": {"url": _upload_url(n)}} for n in names)
    return HumanMessage(content=blocks)


def _middleware(hard=10, keep=5):
    return HistoricalImageCapMiddleware(hard_limit=hard, keep_limit=keep)


@pytest.mark.asyncio
async def test_replaces_oldest_images_beyond_hard_limit_with_url_placeholders():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    # 12 条历史图片消息 + 1 条当前消息（当前消息无图片）
    messages = [_image_message([f"img{i}"], text=f"第{i}轮") for i in range(12)]
    messages.append(_image_message([], text="当前问题"))

    await _middleware(hard=10, keep=5).awrap_model_call(_Request(messages), handler)

    out = seen["request"].messages
    urls_in_blocks = []
    placeholder_texts = []
    for msg in out:
        for block in msg.content:
            if block.get("type") == "image_url":
                urls_in_blocks.append(block["image_url"]["url"])
            elif block.get("type") == "text" and "image omitted" in block.get("text", ""):
                placeholder_texts.append(block["text"])
    # 只保留最新 5 张图片块（img7..img11），其余 7 张变成占位符
    assert urls_in_blocks == [_upload_url(f"img{i}") for i in range(7, 12)]
    assert len(placeholder_texts) == 7
    assert all(_upload_url(f"img{i}") in t for i, t in zip(range(7), placeholder_texts))


@pytest.mark.asyncio
async def test_no_change_at_or_below_hard_limit_returns_identical_list():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    messages = [_image_message([f"img{i}"]) for i in range(8)]  # keep=5 < 8 < hard=10

    request = _Request(messages)
    await _middleware(hard=10, keep=5).awrap_model_call(request, handler)

    # 迟滞区间内原样透传（对象同一，零 token 漂移）
    assert seen["request"].messages is messages


@pytest.mark.asyncio
async def test_replacement_is_deterministic_across_calls():
    outputs = []

    async def handler(request):
        outputs.append([m.content for m in request.messages])
        return request

    messages = [_image_message([f"img{i}"]) for i in range(12)]

    middleware = _middleware(hard=10, keep=5)
    await middleware.awrap_model_call(_Request(list(messages)), handler)
    await middleware.awrap_model_call(_Request(list(messages)), handler)

    assert outputs[0] == outputs[1]


@pytest.mark.asyncio
async def test_last_human_message_images_are_never_touched():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    # 历史 12 张（超 hard=10）+ 当前消息 3 张
    history = [_image_message([f"old{i}"]) for i in range(12)]
    current = _image_message(["cur0", "cur1", "cur2"], text="看这些图")
    messages = history + [current]

    await _middleware(hard=10, keep=5).awrap_model_call(_Request(messages), handler)

    out = seen["request"].messages
    current_blocks = [
        b for b in out[-1].content if b.get("type") == "image_url"
    ]
    assert len(current_blocks) == 3  # 当前轮 3 张全保留
    # 历史只保留最新 keep=5 张（old7..old11）
    history_image_urls = [
        b["image_url"]["url"]
        for msg in out[:-1]
        for b in msg.content
        if b.get("type") == "image_url"
    ]
    assert history_image_urls == [_upload_url(f"old{i}") for i in range(7, 12)]


@pytest.mark.asyncio
async def test_current_message_images_do_not_count_toward_trigger():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    # 历史里 9 张（低于 hard=10），当前消息 3 张 —— 历史未超限则不淘汰
    history = [_image_message([f"old{i}"]) for i in range(9)]
    current = _image_message(["cur0", "cur1", "cur2"], text="看这些图")
    messages = history + [current]

    request = _Request(messages)
    await _middleware(hard=10, keep=5).awrap_model_call(request, handler)

    assert seen["request"].messages is messages


@pytest.mark.asyncio
async def test_data_url_images_get_placeholder_without_payload():
    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    data_url = "data:image/png;base64," + "A" * 500
    messages = [
        HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": data_url}},
                *(
                    {"type": "image_url", "image_url": {"url": _upload_url(f"u{i}")}}
                    for i in range(11)
                ),
            ]
        ),
        _image_message([], text="hi"),
    ]

    await _middleware(hard=10, keep=5).awrap_model_call(_Request(messages), handler)

    texts = [b["text"] for b in seen["request"].messages[0].content if b.get("type") == "text"]
    # base64 不得出现在请求里，占位符是纯文本
    assert any("image omitted" in t for t in texts)
    assert all("base64" not in t for t in texts)


def test_settings_defaults_are_hysteresis_safe():
    from src.kernel.config import settings

    # hard 必须 > keep，否则淘汰永不该发生
    assert settings.HISTORY_IMAGE_HARD_LIMIT > settings.HISTORY_IMAGE_KEEP_LIMIT
    assert settings.HISTORY_IMAGE_KEEP_LIMIT > 0


def test_retry_stack_registers_cap_after_dead_filter():
    from src.infra.agent.middleware.retry import create_retry_middleware

    stack = create_retry_middleware()
    names = [type(item).__name__ for item in stack]

    assert names[0] == "DeadAttachmentFilterMiddleware"
    assert names[1] == "HistoricalImageCapMiddleware"

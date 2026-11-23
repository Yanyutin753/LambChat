"""Bounding, deduplication and storage materialization for native image blocks."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage

# 与 tool_interception 的 _BINARY_BLOCK_UPLOAD_MAX_BLOCKS（单次模型请求 4 图上限）
# 保持同一口径；native 与附件路径的预算相互独立，互不挤占。
NATIVE_IMAGE_MAX_PER_REQUEST = 4

NATIVE_IMAGE_OMITTED_NOTE = "[image omitted: per-request native image limit]"


def bounded_native_image_messages(
    groups: list[list[Any]],
    *,
    max_images: int = NATIVE_IMAGE_MAX_PER_REQUEST,
) -> list[HumanMessage]:
    """按时间序限制单次模型请求携带的 native 图片总量并按 URL 去重。

    超限图片替换为文本占位、重复 URL 直接省略（同请求内模型已见过该图）。
    """
    seen: set[str] = set()
    kept = 0
    messages: list[HumanMessage] = []
    for blocks in groups:
        bounded: list[Any] = []
        for block in blocks:
            image_url = block.get("image_url") if isinstance(block, dict) else None
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str):
                bounded.append(block)
                continue
            if url in seen:
                continue
            if kept >= max_images:
                bounded.append({"type": "text", "text": NATIVE_IMAGE_OMITTED_NOTE})
                continue
            seen.add(url)
            kept += 1
            bounded.append(block)
        if bounded:
            messages.append(HumanMessage(content=bounded))
    return messages


def native_analysis_succeeded(analysis: str) -> bool:
    """只有成功分析才值得缓存；失败结果保留后续重试机会。"""
    try:
        payload = json.loads(analysis)
    except (ValueError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("success") is True


async def materialize_native_blocks(
    blocks: list[Any],
    upload_block: Callable[[dict[str, Any]], Awaitable[str | None]],
) -> list[Any]:
    """把 native 图片块中的 data URL 上传存储换成本站 URL。

    ToolMessage 的 artifact 会随 checkpoint 持久化，完整 base64 会让状态体积
    随图片数线性膨胀；换成 /api/upload/file/ URL 引用后由内层图片中间件在
    模型请求侧按模式做私钥授权与格式转换。上传失败时保留原 data URL
    （宁可状态膨胀也不丢图）。
    """
    materialized: list[Any] = []
    for block in blocks:
        image_url = block.get("image_url") if isinstance(block, dict) else None
        url = image_url.get("url") if isinstance(image_url, dict) else None
        if isinstance(url, str) and url.startswith("data:") and isinstance(image_url, dict):
            uploaded = await upload_data_url_image(url, upload_block)
            if uploaded:
                block = {**block, "image_url": {**image_url, "url": uploaded}}
        materialized.append(block)
    return materialized


async def upload_data_url_image(
    data_url: str,
    upload_block: Callable[[dict[str, Any]], Awaitable[str | None]],
) -> str | None:
    header, _, payload = data_url.partition(",")
    mime_type = (
        header[len("data:") :].split(";", 1)[0].lower() if header.startswith("data:") else ""
    )
    if not mime_type.startswith("image/") or not payload:
        return None
    return await upload_block({"base64": payload, "mime_type": mime_type})

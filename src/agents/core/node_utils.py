"""
Agent 节点共享工具函数

从 search_agent/nodes.py 和 fast_agent/nodes.py 中提取的公共逻辑。
"""

from __future__ import annotations

import base64
import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from tempfile import SpooledTemporaryFile
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import var_child_runnable_config
from langgraph.constants import CONFIG_KEY_CHECKPOINTER

from src.infra.agent import AgentEventProcessor
from src.infra.async_utils import run_blocking_io
from src.infra.image_utils import compress_image_bytes_if_needed
from src.infra.logging import get_logger

logger = get_logger(__name__)
DEFAULT_IMAGE_DOWNLOAD_MAX_BYTES = 25 * 1024 * 1024
IMAGE_DATA_URL_SPOOL_MAX_MEMORY_BYTES = 256 * 1024
IMAGE_DATA_URL_ENCODE_CHUNK_BYTES = 192 * 1024


def get_image_download_max_bytes() -> int:
    """Return the configured image upload limit in bytes."""
    try:
        from src.kernel.config import settings

        configured_mb = int(getattr(settings, "FILE_UPLOAD_MAX_SIZE_IMAGE", 0) or 0)
        if configured_mb > 0:
            return configured_mb * 1024 * 1024
    except Exception:
        pass
    return DEFAULT_IMAGE_DOWNLOAD_MAX_BYTES


def build_nested_graph_configurable(
    *,
    thread_id: str,
    checkpointer: Any,
    **values: Any,
) -> dict[str, Any]:
    """Build config for a graph invoked manually inside another LangGraph node."""
    return {
        "thread_id": thread_id,
        CONFIG_KEY_CHECKPOINTER: checkpointer,
        "checkpoint_ns": "",
        **values,
    }


@asynccontextmanager
async def isolated_nested_graph_run() -> AsyncIterator[None]:
    """Run a manually nested graph without inheriting the parent graph task config."""
    token = var_child_runnable_config.set(None)
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def resolve_auto_memory_capture_text(
    *,
    hitl_suspended: bool,
    user_input: str,
    recommendation_input: str | None = None,
) -> str | None:
    """解析本轮应捕获记忆的用户文本；无需捕获时返回 None。

    ask_human 挂起的 run（waiting_human）还没有最终回答，记忆捕获必须推迟到
    run 最终 finished 的那一轮，否则挂起瞬间会白发起一次记忆评估 LLM 调用，
    且 source_refs 指向没有最终回答的 run。恢复轮 state.input 为空，原始
    用户消息由 resume_context.recommendation_input 透传（infra/task/hitl.py）。
    """
    if hitl_suspended:
        return None
    text = (user_input or "").strip() or (recommendation_input or "").strip()
    return text or None


async def resolve_fallback_model(
    model_id: str | None,
    selected_model: str | None,
    *,
    log_prefix: str = "",
) -> str | None:
    """从 DB 解析 fallback_model ID 到实际的 model value。

    Args:
        model_id: 当前模型的 DB ID（优先）
        selected_model: 当前模型的 value 字符串（备选）
        log_prefix: 日志前缀，如 "[FastAgent]" 或 "[Agent]"

    Returns:
        fallback model 的 value 字符串，或 None（无 fallback / 查询失败）
    """
    from src.infra.agent.model_storage import get_model_storage

    storage = get_model_storage()
    db_model = None

    try:
        if model_id:
            db_model = await storage.get(model_id)
        elif selected_model:
            db_model = await storage.get_by_value(selected_model)
    except Exception as e:
        logger.warning("%s Failed to lookup model config: %s", log_prefix, e)
        return None

    if not db_model or not db_model.fallback_model:
        return await _global_fallback_model(selected_model, log_prefix)

    try:
        fallback_db = await storage.get(db_model.fallback_model)
    except Exception as e:
        logger.warning("%s Failed to lookup fallback model: %s", log_prefix, e)
        return None

    if fallback_db:
        logger.info(
            "%s Fallback model: %s (%s)",
            log_prefix,
            fallback_db.label,
            fallback_db.value,
        )
        return fallback_db.value

    return await _global_fallback_model(selected_model, log_prefix)


async def _global_fallback_model(selected_model: str | None, log_prefix: str = "") -> str | None:
    """全局兜底模型：DB 未配置 fallback_model 时使用 LLM_FALLBACK_MODEL。

    设置值可以是模型配置 UUID（设置面板下拉保存的 id）或旧的模型 value
    字符串；UUID 解析成 value，非 UUID / 查询失败按原始字符串处理。
    """
    from src.kernel.config import settings

    fallback = settings.LLM_FALLBACK_MODEL
    if not fallback or not fallback.strip():
        return None
    fallback = fallback.strip()

    resolved = await _resolve_fallback_reference(fallback, log_prefix)
    if not resolved:
        return None
    if selected_model and resolved == selected_model:
        logger.warning(
            "%s Global fallback model equals primary model (%s); skipping self-fallback",
            log_prefix,
            resolved,
        )
        return None
    logger.info("%s Using global fallback model: %s", log_prefix, resolved)
    return resolved


async def _resolve_fallback_reference(reference: str, log_prefix: str = "") -> str | None:
    """把 LLM_FALLBACK_MODEL 引用解析成模型 value（UUID → value，其余原样）。"""
    from src.infra.agent.model_storage import get_model_storage

    try:
        db_model = await get_model_storage().get(reference)
    except Exception as e:
        # 查询失败（如存储不可用）时保守地按原始字符串处理
        logger.debug("%s Fallback reference lookup failed: %s", log_prefix, e)
        return reference
    return db_model.value if db_model else reference


async def _resolve_model_profile_bool(
    attr_name: str,
    model_id: str | None,
    selected_model: str | None,
    *,
    log_prefix: str = "",
) -> bool:
    """Resolve a boolean flag from the model's profile.

    Shared lookup logic used by resolve_model_supports_vision and
    resolve_model_image_url_to_base64 to avoid duplicating the
    model-storage fetch boilerplate.
    """
    if not model_id and not selected_model:
        return False

    from src.infra.agent.model_storage import get_model_storage

    storage = get_model_storage()
    db_model = None

    try:
        if model_id:
            db_model = await storage.get(model_id)
        elif selected_model:
            db_model = await storage.get_by_value(selected_model)
    except Exception as e:
        logger.warning("%s Failed to lookup model profile (%s): %s", log_prefix, attr_name, e)
        return False

    if not db_model or not getattr(db_model, "profile", None):
        return False

    return bool(getattr(db_model.profile, attr_name, False))


async def resolve_model_supports_vision(
    model_id: str | None,
    selected_model: str | None,
    *,
    log_prefix: str = "",
) -> bool:
    """Resolve whether the selected model is configured for image input."""
    return await _resolve_model_profile_bool(
        "supports_vision", model_id, selected_model, log_prefix=log_prefix
    )


async def resolve_model_image_url_to_base64(
    model_id: str | None,
    selected_model: str | None,
    *,
    log_prefix: str = "",
) -> bool:
    """Resolve whether image_url blocks should be converted to base64 data URLs."""
    return await _resolve_model_profile_bool(
        "image_url_to_base64", model_id, selected_model, log_prefix=log_prefix
    )


def _is_image_attachment(attachment: dict) -> bool:
    file_type = str(attachment.get("type", "")).lower()
    mime_type = str(attachment.get("mime_type") or attachment.get("mimeType") or "").lower()
    return file_type == "image" or mime_type.startswith("image/")


def _attachment_url_from_key(key: object, base_url: str) -> str:
    clean_base_url = base_url.rstrip("/")
    quoted_key = quote(str(key).lstrip("/"), safe="/")
    return f"{clean_base_url}/api/upload/file/{quoted_key}"


def _upload_key_from_image_url(url: str) -> str | None:
    if url.startswith("data:"):
        return None

    parsed = urlsplit(url)
    path = unquote(parsed.path or url)
    marker = "/api/upload/file/"
    if marker not in path:
        return None

    key = path.split(marker, 1)[1].lstrip("/")
    return key or None


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def _is_private_url(url: str) -> bool:
    """Return True if *url* points to a private / loopback / link-local address.

    Blocks SSRF via httpx fallback in ``_download_image_url_as_data_url``.
    Non-http schemes are also rejected.
    """
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return True
    hostname = parsed.hostname
    if not hostname:
        return True
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


def _base64_encode_file(file) -> str:
    parts: list[str] = []
    while True:
        chunk = file.read(IMAGE_DATA_URL_ENCODE_CHUNK_BYTES)
        if not chunk:
            break
        parts.append(base64.b64encode(chunk).decode("ascii"))
    return "".join(parts)


def _read_binary_file(file: Any) -> bytes:
    return bytes(file.read())


def _base64_encode_bytes(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


async def _download_image_as_data_url(
    storage,
    key: object,
    mime_type: str,
) -> str | None:
    max_bytes = get_image_download_max_bytes()
    spooled = SpooledTemporaryFile(
        max_size=IMAGE_DATA_URL_SPOOL_MAX_MEMORY_BYTES,
        mode="w+b",
    )
    try:
        downloaded_size = await storage.download_to_file(str(key), spooled)
        if isinstance(downloaded_size, int) and downloaded_size > max_bytes:
            return None
        await run_blocking_io(spooled.seek, 0)
        content = await run_blocking_io(_read_binary_file, spooled)
        if len(content) > max_bytes:
            return None
    finally:
        await run_blocking_io(spooled.close)
    content, mime_type = await run_blocking_io(compress_image_bytes_if_needed, content, mime_type)
    encoded = await run_blocking_io(_base64_encode_bytes, content)
    return f"data:{mime_type};base64,{encoded}"


async def _download_image_url_as_data_url(
    url: str,
    mime_type: str,
) -> str | None:
    max_bytes = get_image_download_max_bytes()
    key = _upload_key_from_image_url(url)
    if key:
        from src.infra.storage.s3.service import get_or_init_storage

        storage = await get_or_init_storage()
        return await _download_image_as_data_url(
            storage,
            key,
            mime_type,
        )

    if _is_private_url(url):
        logger.warning("Refusing to inline private/internal image URL")
        return None

    try:
        import httpx
    except Exception:
        logger.warning("Cannot inline remote image URL without httpx")
        return None

    spooled = SpooledTemporaryFile(
        max_size=IMAGE_DATA_URL_SPOOL_MAX_MEMORY_BYTES,
        mode="w+b",
    )
    try:
        downloaded_size = 0
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if content_type.startswith("image/"):
                    mime_type = content_type
                async for chunk in response.aiter_bytes():
                    downloaded_size += len(chunk)
                    if downloaded_size > max_bytes:
                        return None
                    await run_blocking_io(spooled.write, chunk)
        await run_blocking_io(spooled.seek, 0)
        content = await run_blocking_io(_read_binary_file, spooled)
        if len(content) > max_bytes:
            return None
    finally:
        await run_blocking_io(spooled.close)
    content, mime_type = await run_blocking_io(compress_image_bytes_if_needed, content, mime_type)
    encoded = await run_blocking_io(_base64_encode_bytes, content)
    return f"data:{mime_type};base64,{encoded}"


async def inline_image_attachments_as_data_urls(
    attachments: list[dict] | None,
    *,
    base_url: str = "",
    force_data_url: bool = False,
) -> list[dict]:
    """Return image attachments with URLs preferred over in-memory data URLs."""
    if not attachments:
        return []

    inlined: list[dict] = []
    storage = None

    for attachment in attachments:
        if not _is_image_attachment(attachment):
            inlined.append(attachment)
            continue

        if attachment.get("data_url"):
            inlined.append(attachment)
            continue

        existing_url = attachment.get("url")
        if existing_url and not force_data_url:
            inlined.append(attachment)
            continue

        key = attachment.get("key")
        mime_type = attachment.get("mime_type") or attachment.get("mimeType") or "image/jpeg"

        if existing_url and force_data_url:
            size = attachment.get("size")
            if isinstance(size, int) and size > get_image_download_max_bytes():
                inlined.append(attachment)
                continue
            try:
                data_url = await _download_image_url_as_data_url(
                    str(existing_url),
                    mime_type,
                )
                if data_url is None:
                    inlined.append(attachment)
                    continue
            except Exception as e:
                logger.warning(
                    "Failed to inline image URL: error_type=%s",
                    type(e).__name__,
                )
                inlined.append(attachment)
                continue
            inlined.append(
                {
                    **attachment,
                    "data_url": data_url,
                    "original_url": existing_url,
                }
            )
            continue

        if not key:
            inlined.append(attachment)
            continue

        if base_url and not force_data_url:
            inlined.append(
                {
                    **attachment,
                    "url": _attachment_url_from_key(key, base_url),
                }
            )
            continue

        size = attachment.get("size")
        if isinstance(size, int) and size > get_image_download_max_bytes():
            inlined.append(attachment)
            continue

        try:
            if storage is None:
                from src.infra.storage.s3.service import get_or_init_storage

                storage = await get_or_init_storage()
            data_url = await _download_image_as_data_url(storage, key, mime_type)
            if data_url is None:
                inlined.append(attachment)
                continue
        except Exception as e:
            logger.warning(
                "Failed to inline image attachment: error_type=%s",
                type(e).__name__,
            )
            inlined.append(attachment)
            continue

        inlined.append(
            {
                **attachment,
                "data_url": data_url,
            }
        )

    return inlined


def _format_attachment_summary(text: str, attachments: list[dict]) -> str:
    enhanced_text = text
    if not attachments:
        return enhanced_text

    enhanced_text += "\n\n---\n**User Uploaded Attachments:**"

    for attachment in attachments:
        url = attachment.get("url") or attachment.get("original_url") or ""
        name = attachment.get("name", "未知文件")
        file_type = attachment.get("type", "document")
        mime_type = attachment.get("mime_type") or attachment.get("mimeType") or ""
        size = attachment.get("size", 0)

        if not url:
            continue

        size_str = ""
        if size:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

        enhanced_text += f"\n\n**[{name}]**"
        enhanced_text += f"\n- 类型: {file_type}"
        if mime_type:
            enhanced_text += f" ({mime_type})"
        if size_str:
            enhanced_text += f"\n- 大小: {size_str}"
        image_index = attachment.get("image_index")
        if image_index:
            enhanced_text += f"\n- Corresponding image: #{image_index}"
        enhanced_text += f"\n- 链接: {url}"

    return enhanced_text


def build_human_message(
    text: str,
    attachments: list[dict] | None,
    *,
    supports_vision: bool = False,
) -> HumanMessage:
    """
    构建 HumanMessage，将附件信息以文本形式附加到消息中

    Args:
        text: 用户输入的文本
        attachments: 附件列表，每个附件包含:
            - url: 文件访问链接
            - type: 文件类型 (image/video/audio/document)
            - name: 文件名
            - mime_type: MIME 类型 (可选)
            - size: 文件大小 (可选)

    Returns:
        HumanMessage: 包含文本和附件信息的消息
    """
    if not attachments:
        return HumanMessage(content=text)

    multimodal_images: list[dict] = []
    text_summary_attachments: list[dict] = []

    for attachment in attachments:
        url = attachment.get("url")
        data_url = attachment.get("data_url")
        image_url = data_url or url
        if supports_vision and _is_image_attachment(attachment) and image_url:
            image_index = len(multimodal_images) + 1
            multimodal_images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )
            if data_url and url:
                text_summary_attachments.append({**attachment, "image_index": image_index})
        elif url:
            text_summary_attachments.append(attachment)

    enhanced_text = _format_attachment_summary(text, text_summary_attachments)
    if not multimodal_images:
        return HumanMessage(content=enhanced_text)

    return HumanMessage(
        content=[
            {"type": "text", "text": enhanced_text},
            *multimodal_images,
        ]
    )


async def emit_token_usage(
    event_processor: AgentEventProcessor,
    presenter,
    start_time: float,
    *,
    model_id: str | None = None,
    model: str | None = None,
) -> None:
    """发送 token 使用统计事件"""
    import time

    duration = time.time() - start_time
    try:
        await event_processor.emit_token_usage(
            duration=duration,
            model_id=model_id,
            model=model,
        )
    except Exception as e:
        logger.warning(f"Failed to emit token:usage event: {e}")

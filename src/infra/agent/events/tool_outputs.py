"""Normalize LangGraph and MCP tool outputs for presenter events."""

import json
from typing import Any

from src.infra.agent.events.types import TOOL_ERROR_INDICATORS

MCP_MEDIA_TYPES = frozenset(("image", "file"))
MCP_SKIP_KEYS = frozenset(("id",))


def extract_tool_output(out: Any) -> Any:
    """Extract displayable content from LangGraph tool node output."""
    if out is None:
        return ""
    if isinstance(out, str):
        return out

    if not isinstance(out, (dict, list, str)):
        if isinstance(out, tuple) and len(out) >= 1:
            return extract_tool_output(out[0])
        update = getattr(out, "update", None)
        if isinstance(update, dict):
            messages = update.get("messages")
            if messages:
                return process_messages(messages)
            return update
        content = getattr(out, "content", None)
        if content is not None:
            return normalize_content(content)
        artifact = getattr(out, "artifact", None)
        if artifact is not None:
            return artifact
        return ""

    if isinstance(out, list):
        if out and not isinstance(out[0], (dict, str)):
            return process_messages(out)
        return normalize_content(out)

    if not isinstance(out, dict):
        return out

    update = out.get("update")
    if isinstance(update, dict):
        messages = update.get("messages")
        if messages:
            return process_messages(messages)
        return update

    if "content" in out:
        return normalize_content(out["content"])

    nested = out.get("output")
    if nested is not None:
        if isinstance(nested, dict):
            return normalize_content(nested.get("content", nested))
        return nested

    return out


def detect_tool_error(out: Any, raw: Any) -> tuple[bool, str | None]:
    """Detect tool errors from status fields first, then conservative content markers."""
    tool_status = get_tool_status(out)
    if tool_status == "error":
        return True, str(raw) if raw else "Tool execution failed"

    if isinstance(raw, dict) and (raw.get("error") or raw.get("status") == "error"):
        return True, raw.get("error") or raw.get("message") or str(raw)

    if isinstance(raw, str) and raw:
        first_line = raw.lstrip()[:200].lower()
        if any(first_line.startswith(marker) for marker in TOOL_ERROR_INDICATORS):
            return True, raw

    return False, None


def get_tool_status(out: Any) -> str | None:
    """Find ToolMessage.status through common LangGraph wrappers."""

    def check(obj: Any) -> str | None:
        status = getattr(obj, "status", None)
        if status and isinstance(status, str):
            return status
        return None

    if out is None:
        return None

    if not isinstance(out, (dict, list, str)):
        status = check(out)
        if status:
            return status
        update = getattr(out, "update", None)
        if isinstance(update, dict):
            return get_tool_status(update.get("messages"))
        return None

    if isinstance(out, list):
        for item in out:
            if isinstance(item, (dict, str)):
                continue
            status = check(item)
            if status:
                return status
        return None

    if isinstance(out, dict):
        update = out.get("update")
        if isinstance(update, dict):
            return get_tool_status(update.get("messages"))

    return None


def collect_blocks(content: list, text_parts: list[str], media_blocks: list[dict]) -> bool:
    """Collect text and media blocks from MCP-style content lists."""
    has_media = False

    for block in content:
        if isinstance(block, list):
            nested = normalize_content(block)
            if isinstance(nested, str):
                text_parts.append(nested)
            elif isinstance(nested, dict):
                if "text" in nested:
                    text_parts.append(nested["text"])
                if "blocks" in nested:
                    media_blocks.extend(nested["blocks"])
                    has_media = True
            continue

        if not isinstance(block, dict):
            text_parts.append(str(block) if block is not None else "")
            continue

        block_type = block.get("type", "")
        if block_type == "text":
            text = block.get("text")
            text_parts.append(str(text) if text is not None else "")
        elif block_type in MCP_MEDIA_TYPES:
            media_blocks.append(
                {key: value for key, value in block.items() if key not in MCP_SKIP_KEYS}
                if "id" in block
                else block
            )
            has_media = True
        elif "text" in block:
            text_parts.append(str(block["text"]))
        else:
            media_blocks.append(
                {key: value for key, value in block.items() if key not in MCP_SKIP_KEYS}
                if "id" in block
                else block
            )
            has_media = True

    return has_media


def normalize_content(content: Any) -> Any:
    """Normalize MCP content blocks into text or structured media payloads."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content
    if not isinstance(content, list):
        return str(content)

    text_parts: list[str] = []
    media_blocks: list[dict] = []
    collect_blocks(content, text_parts, media_blocks)

    if media_blocks:
        return {"text": "".join(text_parts), "blocks": media_blocks}

    text_result = "".join(text_parts)
    return text_result if text_result else content


def process_messages(messages: list) -> Any:
    """Extract and merge message content while preserving MCP media blocks."""
    text_parts: list[str] = []
    media_blocks: list[dict] = []
    has_media = False

    for message in messages:
        if isinstance(message, dict):
            content = message.get("content", "")
            artifact = message.get("artifact")
        else:
            content = getattr(message, "content", "")
            artifact = getattr(message, "artifact", None)

        # Prefer content (human-readable) over artifact (structured metadata)
        if isinstance(content, str) and content:
            text_parts.append(content)
            continue
        if isinstance(content, list):
            if collect_blocks(content, text_parts, media_blocks):
                has_media = True
            continue
        if artifact is not None:
            text_parts.append(json.dumps(artifact, ensure_ascii=False))
            continue

        # Fallback: stringify whatever content is
        if isinstance(content, dict):
            text_parts.append(json.dumps(content, ensure_ascii=False))
        elif content is not None:
            text_parts.append(str(content))

    text_result = "\n".join(text_parts)
    if has_media:
        return {"text": text_result, "blocks": media_blocks}
    return text_result

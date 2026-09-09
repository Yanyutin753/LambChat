"""Web fetch system tool: SSRF-guarded page reading for agents（对齐 web_search_tool）。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain.tools import tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.web_fetch_providers import execute_web_fetch

logger = get_logger(__name__)

DEFAULT_WEB_FETCH_MAX_CHARS = 32768
MAX_WEB_FETCH_CHARS = 262144


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


@tool
async def web_fetch(
    url: Annotated[str, "The http/https URL to read. Public pages only."],
    max_chars: Annotated[int, "Max characters of content to return."] = DEFAULT_WEB_FETCH_MAX_CHARS,
) -> str:
    """
    Read a web page and return its text as markdown. Use to dive into a web_search
    result URL. Returns JSON with success/url/title/content/truncated fields.
    """
    raw = (url or "").strip()
    if not raw:
        return await _json_dumps_result({"success": False, "error": "web_fetch_empty_url"})

    try:
        limit = max(256, min(int(max_chars), MAX_WEB_FETCH_CHARS))
        result = await execute_web_fetch(raw, limit)
    except Exception as e:
        logger.error("[WebFetch] execute failed: %s", e, exc_info=True)
        result = {"success": False, "error": f"web_fetch_failed: {e}"}
    return await _json_dumps_result(result)


def get_web_fetch_tool() -> BaseTool:
    """Factory for the internal registry (registered when ENABLE_WEB_FETCH)."""
    return web_fetch

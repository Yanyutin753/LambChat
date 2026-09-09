"""Web search system tool: multi-provider, multi-key rotating search for agents."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Optional

from langchain.tools import tool
from langchain_core.tools import BaseTool

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.web_search_providers import execute_web_search, normalize_time_range

logger = get_logger(__name__)

MAX_WEB_SEARCH_RESULTS = 10


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


@tool
async def web_search(
    query: Annotated[str, "The search query. Write it in the user's language for best relevance."],
    max_results: Annotated[int, "Number of results to return, 1-10."] = 5,
    time_range: Annotated[
        Optional[Literal["day", "week", "month", "year"]],
        "Restrict to recent results, e.g. 'day' for last 24h. Omit for any time.",
    ] = None,
) -> str:
    """
    Search the public web for current information (news, docs, prices, facts beyond
    training data). Returns JSON: results[] {title, url, snippet, score, favicon_url,
    published_date}, optional images[] {url, description} and a short answer.
    Cite result urls in your reply.
    """
    query = (query or "").strip()
    if not query:
        return await _json_dumps_result({"success": False, "error": "web_search_empty_query"})

    try:
        result = await execute_web_search(
            query=query,
            max_results=max(1, min(int(max_results), MAX_WEB_SEARCH_RESULTS)),
            time_range=normalize_time_range(time_range),
        )
    except Exception as e:
        logger.error("[WebSearch] execute failed: %s", e, exc_info=True)
        result = {"success": False, "error": f"web_search_failed: {e}"}
    return await _json_dumps_result(result)


def get_web_search_tool() -> BaseTool:
    """Factory for the internal registry (registered when ENABLE_WEB_SEARCH)."""
    return web_search

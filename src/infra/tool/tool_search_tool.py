"""
search_tools 工具 — LangChain BaseTool，供 LLM 搜索和加载延迟的 MCP 工具。

LLM 调用此工具时：
1. 使用关键词搜索引擎匹配延迟工具
2. 将匹配工具提升为"已发现"状态
3. 返回完整 schema 供 LLM 后续调用
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.tool_search import ToolSearchResult, search_tools_with_keywords

if TYPE_CHECKING:
    from src.infra.tool.deferred_manager import DeferredToolManager

logger = get_logger(__name__)

TOOL_SEARCH_SCHEMA_MAX_ARRAY_ITEMS = 200
TOOL_SEARCH_SCHEMA_MAX_STRING_CHARS = 2000
_CALLABLE_SCHEMA_KEYS = (
    "type",
    "properties",
    "required",
    "additionalProperties",
    "$defs",
    "oneOf",
    "anyOf",
    "allOf",
)


class ToolSearchInput(BaseModel):
    """search_tools 的输入 schema"""

    query: str = Field(
        ...,
        description=(
            "Query to find deferred tools by name or capability. "
            "Use exact names shown in the deferred tool inventories, for example "
            '"select:github:create_issue". '
            'Use keywords like "database query" for best-match search. '
            'Prefix a term with + to require it in the tool name (e.g., "+slack send").'
        ),
    )


class ToolSearchTool(BaseTool):
    """搜索并加载延迟的 MCP 或系统工具。

    当 LLM 需要一个不在当前工具列表中的工具时，调用此工具来搜索和加载。
    搜索成功后，匹配的工具会立即可用于后续调用。
    """

    name: str = "search_tools"
    description: str = (
        "Loads callable schemas for deferred MCP and system tools listed in the prompt. "
        "It does NOT search sandbox tools; use `execute` with `mcporter` for those. "
        "Search by capability, require a term with `+term`, or fetch exact names with "
        "`select:github:create_issue`. Use exact tool names as shown."
    )
    args_schema: type[BaseModel] = ToolSearchInput

    # 注入的依赖（非 Pydantic 字段）
    _manager: Optional["DeferredToolManager"] = None
    _search_limit: int = 25

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        manager: "DeferredToolManager",
        search_limit: int = 25,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._manager = manager
        self._search_limit = search_limit

    def _run(self, query: str) -> str:
        raise NotImplementedError("Use async _arun")

    async def _arun(
        self,
        query: str,
        config: Optional[RunnableConfig] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        if not self._manager:
            return "Error: search_tools is not configured properly."

        discovered = self._manager.get_discovered_tools()
        undiscovered = self._manager.get_undiscovered_tools()
        all_tools = discovered + undiscovered
        if not all_tools:
            return "No deferred tools are available for search."

        results, parts = await run_blocking_io(
            _search_and_format_tool_results,
            query,
            discovered,
            undiscovered,
            self._search_limit,
        )

        if not results:
            return (
                f"No tools found matching '{query}'. "
                f"Try different keywords or check the available tool list."
            )

        # 提升匹配的工具
        matched_names = [r.name for r in results]
        newly_discovered = self._manager.discover_tools(matched_names)
        already_available_count = len(results) - len(newly_discovered)

        header = (
            f"Found {len(results)} tool(s). Loaded {len(newly_discovered)} new; "
            f"{already_available_count} already available. Returned schemas are callable; "
            "call it directly next.\n\n"
        )
        return header + "\n\n".join(parts)


def _search_and_format_tool_results(
    query: str,
    discovered: list[BaseTool],
    undiscovered: list[BaseTool],
    search_limit: int,
) -> tuple[list[ToolSearchResult], list[str]]:
    # 优先返回未加载工具，避免较小的 result limit 被已可用工具占满。
    undiscovered_results = search_tools_with_keywords(
        query=query,
        tools=undiscovered,
        max_results=search_limit,
    )
    remaining_slots = max(search_limit - len(undiscovered_results), 0)
    discovered_results = (
        search_tools_with_keywords(
            query=query,
            tools=discovered,
            max_results=remaining_slots,
        )
        if remaining_slots > 0
        else []
    )
    results = undiscovered_results + discovered_results
    return results, [_format_tool_result(result) for result in results]


def _format_tool_result(result: ToolSearchResult) -> str:
    tool = result.tool
    schema: dict[str, Any] = {}
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        try:
            schema = args_schema.model_json_schema()
        except Exception:
            pass

    callable_schema = {
        key: _compact_schema_value(schema[key]) for key in _CALLABLE_SCHEMA_KEYS if key in schema
    }
    schema_str = json.dumps(callable_schema, ensure_ascii=False, separators=(",", ":"))

    return (
        f"## {result.name}\n"
        f"Description: {result.description[:300]}\n"
        f"Schema:\n```json\n{schema_str}\n```"
    )


def _compact_schema_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact_schema_value(child) for key, child in value.items()}
    if isinstance(value, list):
        if len(value) <= TOOL_SEARCH_SCHEMA_MAX_ARRAY_ITEMS:
            return [_compact_schema_value(child) for child in value]
        omitted = len(value) - TOOL_SEARCH_SCHEMA_MAX_ARRAY_ITEMS
        compacted = [
            _compact_schema_value(child) for child in value[:TOOL_SEARCH_SCHEMA_MAX_ARRAY_ITEMS]
        ]
        compacted.append(f"... schema truncated, {omitted} more item(s) omitted")
        return compacted
    if isinstance(value, str) and len(value) > TOOL_SEARCH_SCHEMA_MAX_STRING_CHARS:
        omitted = len(value) - TOOL_SEARCH_SCHEMA_MAX_STRING_CHARS
        return (
            value[:TOOL_SEARCH_SCHEMA_MAX_STRING_CHARS]
            + f"... schema truncated, {omitted} more character(s) omitted"
        )
    return value

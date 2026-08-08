"""Cached adapter from LangChain tools to shared discovery search."""

from __future__ import annotations

import weakref
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from src.infra.search import DiscoveryRecord, search_records

# Module-level cache keyed by object id with a weakref finalizer, so transient
# tool objects do not accumulate in long-lived worker processes.
_parse_cache: dict[int, tuple[weakref.ReferenceType[BaseTool], "_ParsedTool"]] = {}


@dataclass
class ToolSearchResult:
    """One public tool-search result."""

    name: str
    description: str
    score: float
    tool: BaseTool


@dataclass(frozen=True)
class _ParsedTool:
    """Reusable discovery metadata for one tool."""

    description: str
    record: DiscoveryRecord


def _parse_tool(tool: BaseTool) -> _ParsedTool:
    """Adapt a tool into a cached discovery record without retaining it."""
    tool_id = id(tool)
    cached = _parse_cache.get(tool_id)
    if cached is not None:
        cached_ref, cached_parsed = cached
        if cached_ref() is tool:
            return cached_parsed
        _parse_cache.pop(tool_id, None)

    description = getattr(tool, "description", "") or ""
    server = getattr(tool, "server", "") or ""
    parsed = _ParsedTool(
        description=description,
        record=DiscoveryRecord(
            name=tool.name,
            text=description,
            tags=(server,) if server else (),
        ),
    )
    try:

        def _on_finalize(_wref: weakref.ReferenceType[BaseTool], _tool_id: int = tool_id) -> None:
            _parse_cache.pop(_tool_id, None)

        tool_ref: weakref.ReferenceType[BaseTool] = weakref.ref(tool, _on_finalize)
    except TypeError:
        return parsed
    _parse_cache[tool_id] = (tool_ref, parsed)
    return parsed


def search_tools_with_keywords(
    query: str,
    tools: list[BaseTool],
    max_results: int = 10,
    min_score: float = 2.0,
) -> list[ToolSearchResult]:
    """Search tools with exact, normalized, pinyin, initials, and conservative typo matching."""
    if not query.strip() or not tools or max_results <= 0:
        return []

    parsed_by_name: dict[str, _ParsedTool] = {}
    tools_by_name: dict[str, BaseTool] = {}
    records: list[DiscoveryRecord] = []
    for tool in tools:
        parsed = _parse_tool(tool)
        parsed_by_name[tool.name] = parsed
        tools_by_name[tool.name] = tool
        records.append(parsed.record)

    matches = search_records(query, records, max_results=max_results)
    return [
        ToolSearchResult(
            name=match.name,
            description=parsed_by_name[match.name].description,
            score=match.score,
            tool=tools_by_name[match.name],
        )
        for match in matches
        if match.score >= min_score
    ]

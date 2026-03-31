"""
加权关键词搜索引擎 — 移植自 Claude Code 的 ToolSearchTool。

分层评分：
  名称精确匹配  10-12 分  (MCP 工具 +20%)
  名称部分匹配   5- 6 分
  hint(首行描述)  4 分
  描述全文匹配   2 分
  +term 必选词预过滤
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.infra.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = get_logger(__name__)

# Module-level cache: _ParsedTool keyed by id(tool), safe because tool objects
# are long-lived (created once per session and never mutated).
_parse_cache: dict[int, _ParsedTool] = {}


@dataclass
class ToolSearchResult:
    """搜索结果"""

    name: str
    description: str
    score: float
    tool: "BaseTool"


@dataclass
class _ParsedTool:
    """工具解析缓存"""

    name: str
    full: str
    parts: list[str]
    hint: str
    desc: str
    is_mcp: bool
    tool: "BaseTool"


def _parse_tool(tool: "BaseTool") -> _ParsedTool:
    """将 LangChain BaseTool 解析为搜索用结构（带模块级缓存）"""
    tid = id(tool)
    cached = _parse_cache.get(tid)
    if cached is not None:
        return cached
    name = tool.name
    desc = getattr(tool, "description", "") or ""
    hint = desc.split("\n")[0].strip()
    pt = _ParsedTool(
        name=name,
        full=name.lower(),
        parts=name.replace("_", " ").replace("-", " ").replace(":", " ").lower().split(),
        hint=hint.lower(),
        desc=desc.lower(),
        is_mcp=getattr(tool, "server", "") != "" or name.startswith("mcp"),
        tool=tool,
    )
    _parse_cache[tid] = pt
    return pt


def _compile_term_patterns(terms: list[str]) -> list[tuple[str, str, re.Pattern[str]]]:
    """编译搜索词为 (原始词, 小写词, 词边界正则) 列表"""
    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for term in terms:
        term_lower = term.lower()
        try:
            patterns.append(
                (term, term_lower, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
            )
        except re.error:
            # Fallback: plain substring
            patterns.append((term, term_lower, re.compile(re.escape(term), re.IGNORECASE)))
    return patterns


def search_tools_with_keywords(
    query: str,
    tools: list["BaseTool"],
    max_results: int = 10,
    min_score: float = 2.0,
) -> list[ToolSearchResult]:
    """
    加权关键词搜索，移植自 Claude Code 的 searchToolsWithKeywords()。

    Args:
        query: 搜索关键词，支持 +term 必选语法和 select:A,B 直接选择
        tools: 待搜索的工具列表
        max_results: 最大返回数量
        min_score: 最低分数阈值

    Returns:
        按分数降序排列的搜索结果
    """
    if not query.strip() or not tools:
        return []

    query_lower = query.strip().lower()

    # select:ToolA,ToolB 直接选择语法
    if query_lower.startswith("select:"):
        names_str = query_lower[len("select:") :]
        target_names = {n.strip() for n in names_str.split(",") if n.strip()}
        results: list[ToolSearchResult] = []
        for tool in tools:
            if tool.name.lower() in target_names:
                results.append(
                    ToolSearchResult(
                        name=tool.name,
                        description=getattr(tool, "description", "") or "",
                        score=100.0,
                        tool=tool,
                    )
                )
        return results[:max_results]

    # 解析搜索词，分离必选词（+term）
    raw_terms: list[str] = query.split()
    required_terms: list[str] = []
    search_terms: list[str] = []
    for term in raw_terms:
        if term.startswith("+"):
            required_terms.append(term[1:].lower())
            search_terms.append(term[1:])
        else:
            search_terms.append(term)

    if not search_terms:
        return []

    # 编译正则
    compiled = _compile_term_patterns(search_terms)
    required_compiled = _compile_term_patterns(required_terms)

    # 解析所有工具（缓存友好）
    parsed_tools = [_parse_tool(t) for t in tools]

    # 必选词预过滤
    candidates: list[_ParsedTool] = []
    for pt in parsed_tools:
        if not required_compiled:
            candidates.append(pt)
            continue
        all_match = True
        for _term, _tl, pattern in required_compiled:
            if (
                not pattern.search(pt.full)
                and not pattern.search(pt.hint)
                and not pattern.search(pt.desc)
            ):
                all_match = False
                break
        if all_match:
            candidates.append(pt)

    # 评分
    scored: list[ToolSearchResult] = []
    for pt in candidates:
        score = 0.0
        mcp_mult = 1.2 if pt.is_mcp else 1.0

        for term, term_lower, pattern in compiled:
            # 名称精确匹配（整个 part 等于 term）
            if term_lower in pt.parts:
                score += 12 if pt.is_mcp else 10
            elif any(term_lower in part for part in pt.parts):
                score += 6 if pt.is_mcp else 5

            # 全名回退（低权重）
            if score == 0 and term_lower in pt.full:
                score += 3

            # hint 匹配（词边界）
            if pattern.search(pt.hint):
                score += 4

            # 描述匹配（词边界）
            if pattern.search(pt.desc):
                score += 2

        score *= mcp_mult
        if score >= min_score:
            scored.append(
                ToolSearchResult(
                    name=pt.name,
                    description=getattr(pt.tool, "description", "") or "",
                    score=round(score, 1),
                    tool=pt.tool,
                )
            )

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:max_results]
